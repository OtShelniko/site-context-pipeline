"""Provider registry, local CSV importers, and Google adapter stubs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from site_context_pipeline.providers import (
    ProviderConfigurationError,
    available_providers,
    get_keyword_provider,
    get_search_performance_provider,
)
from site_context_pipeline.providers.google_ads_keyword_planner import (
    GoogleAdsKeywordPlannerProvider,
)
from site_context_pipeline.providers.google_search_console import (
    GoogleSearchConsoleProvider,
)
from site_context_pipeline.providers.local_keyword_csv import LocalKeywordCsvProvider
from site_context_pipeline.providers.local_search_console_csv import (
    LocalSearchConsoleCsvProvider,
)


def test_registry_lists_local_providers() -> None:
    listing = available_providers()
    keyword_names = {entry["name"] for entry in listing["keyword"]}
    perf_names = {entry["name"] for entry in listing["search_performance"]}
    assert "local-csv" in keyword_names
    assert "google-ads" in keyword_names
    assert "local-gsc-csv" in perf_names
    assert "google-search-console" in perf_names

    live_keyword = {entry["name"] for entry in listing["keyword"] if entry["live"]}
    assert "local-csv" in live_keyword
    # google-ads is now an opt-in live adapter (works with the
    # [google-ads] extra + credentials), so it is flagged live.
    assert "google-ads" in live_keyword
    # google-search-console is still a stub.
    live_perf = {entry["name"] for entry in listing["search_performance"] if entry["live"]}
    assert "google-search-console" not in live_perf


def test_unknown_provider_raises_configuration_error() -> None:
    with pytest.raises(ProviderConfigurationError):
        get_keyword_provider("does-not-exist")
    with pytest.raises(ProviderConfigurationError):
        get_search_performance_provider("does-not-exist")


def test_local_keyword_csv_imports_demo_data(demo_keyword_csv: Path) -> None:
    provider = LocalKeywordCsvProvider()
    result = provider.run(source=str(demo_keyword_csv))
    assert result.ok is True
    assert result.provider == "local-csv"
    assert result.metadata["items_count"] == 6
    items = result.items
    by_query = {item["query"]: item for item in items}
    assert by_query["local delivery service"]["avg_monthly_searches"] == 3600
    assert by_query["local delivery service"]["competition"] == "HIGH"
    assert by_query["local delivery service"]["source"] == "local-csv"
    assert by_query["local delivery service"]["geo"] == "US"


def test_local_keyword_csv_handles_aliases_and_thousand_separators(tmp_path: Path) -> None:
    csv_path = tmp_path / "keywords.csv"
    csv_path.write_text(
        "Keyword,Search Volume,Competition,Country,Language\n"
        '"sample query","1,234",MEDIUM,DE,de\n'
        "another query,250.0,LOW,DE,de\n",
        encoding="utf-8",
    )
    provider = LocalKeywordCsvProvider()
    result = provider.run(source=str(csv_path))
    assert result.ok is True
    items = {item["query"]: item for item in result.items}
    assert items["sample query"]["avg_monthly_searches"] == 1234
    assert items["sample query"]["competition"] == "MEDIUM"
    assert items["sample query"]["geo"] == "DE"
    assert items["another query"]["avg_monthly_searches"] == 250


def test_local_keyword_csv_missing_source_raises() -> None:
    provider = LocalKeywordCsvProvider()
    with pytest.raises(ProviderConfigurationError):
        provider.run(source=None)


def test_local_keyword_csv_unknown_path_raises(tmp_path: Path) -> None:
    provider = LocalKeywordCsvProvider()
    with pytest.raises(ProviderConfigurationError):
        provider.run(source=str(tmp_path / "missing.csv"))


def test_local_keyword_csv_skips_rows_without_query(tmp_path: Path) -> None:
    csv_path = tmp_path / "keywords.csv"
    csv_path.write_text(
        "query,avg_monthly_searches\nfoo,100\n,200\n",
        encoding="utf-8",
    )
    provider = LocalKeywordCsvProvider()
    result = provider.run(source=str(csv_path))
    assert result.metadata["items_count"] == 1
    assert any("skipped_rows_without_query:1" in w for w in result.warnings)


def test_local_search_console_csv_imports_demo(demo_search_console_csv: Path) -> None:
    provider = LocalSearchConsoleCsvProvider()
    result = provider.run(source=str(demo_search_console_csv))
    assert result.ok is True
    assert result.provider == "local-gsc-csv"
    assert result.metadata["items_count"] == 6
    by_query = {item["query"]: item for item in result.items}

    pricing = by_query["business delivery pricing"]
    # CTR "5.41%" should normalise to 0.0541 (rounded to 6 decimals).
    assert pricing["ctr"] == pytest.approx(0.0541)
    assert pricing["impressions"] == 610
    assert pricing["clicks"] == 33
    assert pricing["source_url"] == "https://example.com/pricing/"
    assert pricing["geo"] == "USA"
    assert pricing["raw"].get("device") == "DESKTOP"


def test_local_search_console_csv_handles_decimal_comma(tmp_path: Path) -> None:
    csv_path = tmp_path / "gsc.csv"
    csv_path.write_text(
        "query,page,clicks,impressions,ctr,position\n"
        '"foo bar","https://example.com/foo/",10,250,"4,0%","12,5"\n',
        encoding="utf-8",
    )
    provider = LocalSearchConsoleCsvProvider()
    result = provider.run(source=str(csv_path))
    item = result.items[0]
    assert item["ctr"] == pytest.approx(0.04)
    assert item["position"] == pytest.approx(12.5)


def test_invalid_csv_returns_structured_error_via_provider(tmp_path: Path) -> None:
    """A missing CSV must surface as a ProviderConfigurationError, which the
    CLI converts into a ``ok=False`` JSON payload (covered in test_cli)."""
    provider = LocalKeywordCsvProvider()
    with pytest.raises(ProviderConfigurationError):
        provider.run(source=str(tmp_path / "no-such-file.csv"))


def test_google_ads_stub_returns_not_configured() -> None:
    result = GoogleAdsKeywordPlannerProvider().run(provider_config={})
    assert result.ok is False
    assert result.provider == "google-ads"
    assert result.errors == ["not_configured"]
    assert result.items == []
    assert result.metadata["blocked_reason"] == "not_configured"


def test_google_search_console_stub_returns_not_configured() -> None:
    result = GoogleSearchConsoleProvider().run(provider_config={})
    assert result.ok is False
    assert result.provider == "google-search-console"
    assert result.errors == ["not_configured"]
    assert result.items == []


def test_provider_result_serialises_to_json() -> None:
    """The CLI relies on every provider result being JSON-safe."""
    result = GoogleAdsKeywordPlannerProvider().run(provider_config={})
    encoded = json.dumps(result.to_dict())
    decoded = json.loads(encoded)
    assert decoded["provider"] == "google-ads"
    assert decoded["ok"] is False
