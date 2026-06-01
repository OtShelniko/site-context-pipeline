"""Tests for the Google Ads Keyword Planner adapter.

The live API call (`_generate_ideas`) is the only part that needs the
SDK and a network; everything that shapes inputs and outputs is a pure
function tested here directly. Live mode is exercised by stubbing the
two seams (`_load_client`, `_generate_ideas`) with fakes — no SDK, no
network, no credentials.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from site_context_pipeline.providers.base import ProviderConfigurationError
from site_context_pipeline.providers.google_ads_keyword_planner import (
    GoogleAdsKeywordPlannerProvider,
    _coerce_seeds,
    _competition_label,
    _redact,
    map_idea_to_metric,
    validate_config,
)

_FULL_CONFIG = {
    "customer_id": "1234567890",
    "developer_token": "dev-token",
    "client_id": "client-id",
    "client_secret": "client-secret",
    "refresh_token": "refresh-token",
    "seeds": ["espresso machine", "burr grinder"],
}


# ---------------------------------------------------------------------------
# Fakes that mimic the proto-plus shapes map_idea_to_metric reads.
# ---------------------------------------------------------------------------


class _FakeMetrics:
    def __init__(self, avg: int | None, competition: int | None, low: int | None = None):
        self.avg_monthly_searches = avg
        self.competition = competition
        self.low_top_of_page_bid_micros = low
        self.high_top_of_page_bid_micros = None


class _FakeIdea:
    def __init__(self, text: str, metrics: _FakeMetrics | None):
        self.text = text
        self.keyword_idea_metrics = metrics


# ---------------------------------------------------------------------------
# not_configured / missing_dependency paths (no SDK, no network)
# ---------------------------------------------------------------------------


def test_no_config_returns_not_configured() -> None:
    result = GoogleAdsKeywordPlannerProvider().run(provider_config=None)
    assert result.ok is False
    assert result.errors == ["not_configured"]
    assert result.items == []


def test_empty_config_returns_not_configured() -> None:
    result = GoogleAdsKeywordPlannerProvider().run(provider_config={})
    assert result.ok is False
    assert result.errors == ["not_configured"]


def test_partial_config_raises_configuration_error() -> None:
    with pytest.raises(ProviderConfigurationError) as exc:
        GoogleAdsKeywordPlannerProvider().run(
            provider_config={"customer_id": "123", "developer_token": "x"}
        )
    # The error names the missing keys.
    assert "client_id" in str(exc.value)
    assert "refresh_token" in str(exc.value)


def test_missing_sdk_returns_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    from site_context_pipeline.providers import google_ads_keyword_planner as mod

    def _boom(self: Any, cfg: dict[str, Any]) -> Any:
        raise mod._MissingDependencyError

    monkeypatch.setattr(mod.GoogleAdsKeywordPlannerProvider, "_load_client", _boom)
    result = GoogleAdsKeywordPlannerProvider().run(provider_config=_FULL_CONFIG)
    assert result.ok is False
    assert result.errors == ["missing_dependency"]
    assert result.metadata["blocked_reason"] == "missing_dependency"


def test_full_config_but_no_seeds_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from site_context_pipeline.providers import google_ads_keyword_planner as mod

    monkeypatch.setattr(
        mod.GoogleAdsKeywordPlannerProvider, "_load_client", lambda self, cfg: object()
    )
    config = {**_FULL_CONFIG, "seeds": []}
    with pytest.raises(ProviderConfigurationError):
        GoogleAdsKeywordPlannerProvider().run(provider_config=config)


# ---------------------------------------------------------------------------
# Live mode with stubbed seams — full happy path, no network.
# ---------------------------------------------------------------------------


def test_live_mode_maps_ideas_to_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    from site_context_pipeline.providers import google_ads_keyword_planner as mod

    fake_rows = [
        _FakeIdea("espresso machine", _FakeMetrics(8200, 4, low=250000)),
        _FakeIdea("burr grinder", _FakeMetrics(4400, 3)),
        _FakeIdea("", _FakeMetrics(10, 2)),  # blank text → dropped
    ]
    monkeypatch.setattr(
        mod.GoogleAdsKeywordPlannerProvider,
        "_load_client",
        lambda self, cfg: object(),
    )
    monkeypatch.setattr(
        mod.GoogleAdsKeywordPlannerProvider,
        "_generate_ideas",
        lambda self, client, cfg, seeds: fake_rows,
    )

    result = GoogleAdsKeywordPlannerProvider().run(provider_config=_FULL_CONFIG)
    assert result.ok is True
    assert result.provider == "google-ads"
    assert len(result.items) == 2  # blank-text idea dropped

    first = result.items[0]
    assert first["query"] == "espresso machine"
    assert first["source"] == "google-ads"
    assert first["avg_monthly_searches"] == 8200
    assert first["competition"] == "HIGH"
    assert first["raw"]["low_top_of_page_bid_micros"] == 250000

    second = result.items[1]
    assert second["competition"] == "MEDIUM"
    assert second["avg_monthly_searches"] == 4400

    # Customer id is redacted in metadata; no secrets leak.
    assert result.metadata["customer_id"] == "******7890"
    assert result.metadata["seeds_count"] == 2
    assert "developer_token" not in json.dumps(result.metadata)


def test_live_result_is_json_serialisable(monkeypatch: pytest.MonkeyPatch) -> None:
    from site_context_pipeline.providers import google_ads_keyword_planner as mod

    monkeypatch.setattr(
        mod.GoogleAdsKeywordPlannerProvider, "_load_client", lambda self, cfg: object()
    )
    monkeypatch.setattr(
        mod.GoogleAdsKeywordPlannerProvider,
        "_generate_ideas",
        lambda self, client, cfg, seeds: [_FakeIdea("x", _FakeMetrics(1, 2))],
    )
    result = GoogleAdsKeywordPlannerProvider().run(provider_config=_FULL_CONFIG)
    json.dumps(result.to_dict())  # must not raise


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_validate_config_lists_missing_keys() -> None:
    assert validate_config({}) == list(
        ("customer_id", "developer_token", "client_id", "client_secret", "refresh_token")
    )
    assert validate_config(_FULL_CONFIG) == []
    assert validate_config({**_FULL_CONFIG, "client_id": "  "}) == ["client_id"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, []),
        ("", []),
        ("one", ["one"]),
        ("  spaced  ", ["spaced"]),
        (["a", " b ", "", None], ["a", "b"]),
        (("x", "y"), ["x", "y"]),
        (42, []),
    ],
)
def test_coerce_seeds(value: object, expected: list[str]) -> None:
    assert _coerce_seeds(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("12", "**"),
        ("1234", "****"),
        ("12345", "*2345"),
        ("1234567890", "******7890"),
    ],
)
def test_redact(value: object, expected: object) -> None:
    assert _redact(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (0, None),  # UNSPECIFIED
        (1, None),  # UNKNOWN
        (2, "LOW"),
        (3, "MEDIUM"),
        (4, "HIGH"),
        ("HIGH", "HIGH"),
        (99, None),
    ],
)
def test_competition_label(value: object, expected: object) -> None:
    assert _competition_label(value) == expected


def test_competition_label_accepts_enum_like_object() -> None:
    class _Enum:
        value = 4

    assert _competition_label(_Enum()) == "HIGH"


def test_map_idea_drops_blank_text() -> None:
    assert map_idea_to_metric(_FakeIdea("   ", _FakeMetrics(5, 2))) is None


def test_map_idea_handles_missing_metrics() -> None:
    metric = map_idea_to_metric(_FakeIdea("query only", None))
    assert metric is not None
    assert metric.query == "query only"
    assert metric.avg_monthly_searches is None
    assert metric.competition is None
    assert metric.raw == {}
