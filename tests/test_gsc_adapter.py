"""Tests for the Google Search Console adapter.

The live API call (`_query`) is the only part needing the SDK and a
network; everything that shapes inputs and outputs is a pure function
tested here. Live mode is exercised by stubbing the two seams
(`_load_service`, `_query`) with fakes — no SDK, no network, no creds.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from site_context_pipeline.providers.base import ProviderConfigurationError
from site_context_pipeline.providers.google_search_console import (
    GoogleSearchConsoleProvider,
    map_row_to_metric,
    resolve_dimensions,
    resolve_row_limit,
    validate_config,
)

_FULL_CONFIG = {
    "site_url": "sc-domain:example.com",
    "credentials_path": "creds.json",
    "start_date": "2026-04-01",
    "end_date": "2026-04-30",
}


# ---------------------------------------------------------------------------
# not_configured / missing_dependency / malformed paths
# ---------------------------------------------------------------------------


def test_no_config_returns_not_configured() -> None:
    result = GoogleSearchConsoleProvider().run(provider_config=None)
    assert result.ok is False
    assert result.errors == ["not_configured"]
    assert result.items == []


def test_empty_config_returns_not_configured() -> None:
    result = GoogleSearchConsoleProvider().run(provider_config={})
    assert result.ok is False
    assert result.errors == ["not_configured"]


def test_partial_config_raises() -> None:
    with pytest.raises(ProviderConfigurationError) as exc:
        GoogleSearchConsoleProvider().run(
            provider_config={"site_url": "sc-domain:example.com"}
        )
    assert "credentials_path" in str(exc.value)
    assert "start_date" in str(exc.value)


def test_invalid_dimensions_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ProviderConfigurationError):
        GoogleSearchConsoleProvider().run(
            provider_config={**_FULL_CONFIG, "dimensions": ["page"]}  # no query
        )
    with pytest.raises(ProviderConfigurationError):
        GoogleSearchConsoleProvider().run(
            provider_config={**_FULL_CONFIG, "dimensions": ["query", "bogus"]}
        )


def test_missing_sdk_returns_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    from site_context_pipeline.providers import google_search_console as mod

    def _boom(self: Any, cfg: dict[str, Any]) -> Any:
        raise mod._MissingDependencyError

    monkeypatch.setattr(mod.GoogleSearchConsoleProvider, "_load_service", _boom)
    result = GoogleSearchConsoleProvider().run(provider_config=_FULL_CONFIG)
    assert result.ok is False
    assert result.errors == ["missing_dependency"]
    assert result.metadata["blocked_reason"] == "missing_dependency"


# ---------------------------------------------------------------------------
# Live mode with stubbed seams — full happy path, no network.
# ---------------------------------------------------------------------------


def test_live_mode_maps_rows_to_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    from site_context_pipeline.providers import google_search_console as mod

    fake_rows = [
        {
            "keys": ["task automation", "https://example.com/guide/"],
            "clicks": 88,
            "impressions": 3400,
            "ctr": 0.0259,
            "position": 9.1,
        },
        {
            "keys": ["", "https://example.com/x/"],  # blank query → dropped
            "clicks": 1,
            "impressions": 5,
        },
    ]
    monkeypatch.setattr(
        mod.GoogleSearchConsoleProvider, "_load_service", lambda self, cfg: object()
    )
    monkeypatch.setattr(
        mod.GoogleSearchConsoleProvider,
        "_query",
        lambda self, service, cfg, dims, limit: fake_rows,
    )

    result = GoogleSearchConsoleProvider().run(provider_config=_FULL_CONFIG)
    assert result.ok is True
    assert result.provider == "google-search-console"
    assert len(result.items) == 1

    row = result.items[0]
    assert row["query"] == "task automation"
    assert row["source"] == "google-search-console"
    assert row["source_url"] == "https://example.com/guide/"
    assert row["clicks"] == 88
    assert row["impressions"] == 3400
    assert row["ctr"] == pytest.approx(0.0259)
    assert row["position"] == pytest.approx(9.1)

    assert result.metadata["site_url"] == "sc-domain:example.com"
    assert result.metadata["dimensions"] == ["query", "page"]
    assert result.metadata["row_limit"] == 1000


def test_live_mode_preserves_extra_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    from site_context_pipeline.providers import google_search_console as mod

    fake_rows = [
        {
            "keys": ["q", "https://example.com/", "MOBILE", "2026-04-10"],
            "clicks": 3,
            "impressions": 40,
        }
    ]
    monkeypatch.setattr(
        mod.GoogleSearchConsoleProvider, "_load_service", lambda self, cfg: object()
    )
    monkeypatch.setattr(
        mod.GoogleSearchConsoleProvider,
        "_query",
        lambda self, service, cfg, dims, limit: fake_rows,
    )
    config = {**_FULL_CONFIG, "dimensions": ["query", "page", "device", "date"]}
    result = GoogleSearchConsoleProvider().run(provider_config=config)
    row = result.items[0]
    assert row["raw"]["device"] == "MOBILE"
    assert row["raw"]["date"] == "2026-04-10"


def test_live_result_is_json_serialisable(monkeypatch: pytest.MonkeyPatch) -> None:
    from site_context_pipeline.providers import google_search_console as mod

    monkeypatch.setattr(
        mod.GoogleSearchConsoleProvider, "_load_service", lambda self, cfg: object()
    )
    monkeypatch.setattr(
        mod.GoogleSearchConsoleProvider,
        "_query",
        lambda self, service, cfg, dims, limit: [
            {"keys": ["q"], "clicks": 1, "impressions": 2, "ctr": 0.5, "position": 1.0}
        ],
    )
    config = {**_FULL_CONFIG, "dimensions": ["query"]}
    result = GoogleSearchConsoleProvider().run(provider_config=config)
    json.dumps(result.to_dict())  # must not raise


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_validate_config() -> None:
    assert validate_config({}) == [
        "site_url",
        "credentials_path",
        "start_date",
        "end_date",
    ]
    assert validate_config(_FULL_CONFIG) == []
    assert validate_config({**_FULL_CONFIG, "start_date": "  "}) == ["start_date"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ("query", "page")),
        ([], ("query", "page")),
        ("query", ("query",)),
        (["query", "page", "country"], ("query", "page", "country")),
        (["page"], None),               # missing query
        (["query", "bogus"], None),     # unknown dimension
        (42, None),                     # wrong type
    ],
)
def test_resolve_dimensions(value: object, expected: object) -> None:
    assert resolve_dimensions(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 1000),
        ("", 1000),
        (0, 1000),
        (-5, 1000),
        ("bad", 1000),
        (500, 500),
        (999999, 25000),  # clamped to the API cap
    ],
)
def test_resolve_row_limit(value: object, expected: int) -> None:
    assert resolve_row_limit(value) == expected


def test_map_row_drops_blank_query() -> None:
    row = {"keys": ["", "https://x/"], "clicks": 1}
    assert map_row_to_metric(row, ("query", "page")) is None


def test_map_row_non_dict_is_none() -> None:
    assert map_row_to_metric("nope", ("query",)) is None


def test_map_row_handles_missing_metrics() -> None:
    row = {"keys": ["just a query"]}
    metric = map_row_to_metric(row, ("query",))
    assert metric is not None
    assert metric.query == "just a query"
    assert metric.clicks is None
    assert metric.impressions is None
    assert metric.ctr is None
    assert metric.position is None
