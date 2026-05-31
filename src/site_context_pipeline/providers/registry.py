"""Provider registry.

The registry is intentionally a plain mapping of strings to provider
classes. It is initialised at import time so the CLI can list available
providers without instantiating any of them. Adding a new provider is a
two-line change here plus the adapter module.
"""

from __future__ import annotations

from typing import Any

from .base import (
    KeywordProvider,
    ProviderConfigurationError,
    SearchPerformanceProvider,
)
from .google_ads_keyword_planner import GoogleAdsKeywordPlannerProvider
from .google_search_console import GoogleSearchConsoleProvider
from .local_keyword_csv import LocalKeywordCsvProvider
from .local_search_console_csv import LocalSearchConsoleCsvProvider

KEYWORD_PROVIDERS: dict[str, type[KeywordProvider]] = {
    LocalKeywordCsvProvider.provider_name: LocalKeywordCsvProvider,
    GoogleAdsKeywordPlannerProvider.provider_name: GoogleAdsKeywordPlannerProvider,
}

SEARCH_PERFORMANCE_PROVIDERS: dict[str, type[SearchPerformanceProvider]] = {
    LocalSearchConsoleCsvProvider.provider_name: LocalSearchConsoleCsvProvider,
    GoogleSearchConsoleProvider.provider_name: GoogleSearchConsoleProvider,
}


_PROVIDER_DESCRIPTIONS: dict[str, str] = {
    LocalKeywordCsvProvider.provider_name: (
        "Read keyword metrics from a local CSV (Google Ads export, "
        "Ahrefs/Semrush export, hand-curated research). Offline."
    ),
    GoogleAdsKeywordPlannerProvider.provider_name: (
        "Stub for live Google Ads Keyword Planner access. Returns "
        "not_configured in this release; export CSV and use local-csv."
    ),
    LocalSearchConsoleCsvProvider.provider_name: (
        "Read search-performance data from a local Google Search Console "
        "Performance CSV export. Offline."
    ),
    GoogleSearchConsoleProvider.provider_name: (
        "Stub for live Google Search Console access. Returns "
        "not_configured in this release; export CSV and use local-gsc-csv."
    ),
}


def get_keyword_provider(name: str) -> KeywordProvider:
    cls = KEYWORD_PROVIDERS.get(name)
    if cls is None:
        raise ProviderConfigurationError(
            f"unknown keyword provider: {name!r}; "
            f"available: {sorted(KEYWORD_PROVIDERS)}"
        )
    return cls()


def get_search_performance_provider(name: str) -> SearchPerformanceProvider:
    cls = SEARCH_PERFORMANCE_PROVIDERS.get(name)
    if cls is None:
        raise ProviderConfigurationError(
            f"unknown search-performance provider: {name!r}; "
            f"available: {sorted(SEARCH_PERFORMANCE_PROVIDERS)}"
        )
    return cls()


def available_providers() -> dict[str, Any]:
    """Return a JSON-serialisable summary for the ``list-providers`` CLI."""
    return {
        "keyword": [
            {
                "name": name,
                "kind": "keyword",
                "live": _is_live(name),
                "description": _PROVIDER_DESCRIPTIONS.get(name, ""),
            }
            for name in sorted(KEYWORD_PROVIDERS)
        ],
        "search_performance": [
            {
                "name": name,
                "kind": "search_performance",
                "live": _is_live(name),
                "description": _PROVIDER_DESCRIPTIONS.get(name, ""),
            }
            for name in sorted(SEARCH_PERFORMANCE_PROVIDERS)
        ],
    }


def _is_live(name: str) -> bool:
    """Heuristic flag: ``True`` for adapters that actually do work in this
    release, ``False`` for stubs that return not_configured."""
    return name in {
        LocalKeywordCsvProvider.provider_name,
        LocalSearchConsoleCsvProvider.provider_name,
    }
