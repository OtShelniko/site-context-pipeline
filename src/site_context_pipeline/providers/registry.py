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
    SearchEvidenceProvider,
    SearchPerformanceProvider,
)
from .google_ads_keyword_planner import GoogleAdsKeywordPlannerProvider
from .google_search_console import GoogleSearchConsoleProvider
from .local_keyword_csv import LocalKeywordCsvProvider
from .local_search_console_csv import LocalSearchConsoleCsvProvider
from .local_search_evidence_csv import LocalSearchEvidenceCsvProvider

KEYWORD_PROVIDERS: dict[str, type[KeywordProvider]] = {
    LocalKeywordCsvProvider.provider_name: LocalKeywordCsvProvider,
    GoogleAdsKeywordPlannerProvider.provider_name: GoogleAdsKeywordPlannerProvider,
}

SEARCH_PERFORMANCE_PROVIDERS: dict[str, type[SearchPerformanceProvider]] = {
    LocalSearchConsoleCsvProvider.provider_name: LocalSearchConsoleCsvProvider,
    GoogleSearchConsoleProvider.provider_name: GoogleSearchConsoleProvider,
}

SEARCH_EVIDENCE_PROVIDERS: dict[str, type[SearchEvidenceProvider]] = {
    LocalSearchEvidenceCsvProvider.provider_name: LocalSearchEvidenceCsvProvider,
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
    LocalSearchEvidenceCsvProvider.provider_name: (
        "Read hand-curated SERP-evidence rows (query, rank, title, url, "
        "snippet, page_type) from a local CSV. Offline; the toolkit "
        "deliberately does not scrape SERPs in 0.x."
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


def get_search_evidence_provider(name: str) -> SearchEvidenceProvider:
    cls = SEARCH_EVIDENCE_PROVIDERS.get(name)
    if cls is None:
        raise ProviderConfigurationError(
            f"unknown search-evidence provider: {name!r}; "
            f"available: {sorted(SEARCH_EVIDENCE_PROVIDERS)}"
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
        "search_evidence": [
            {
                "name": name,
                "kind": "search_evidence",
                "live": _is_live(name),
                "description": _PROVIDER_DESCRIPTIONS.get(name, ""),
            }
            for name in sorted(SEARCH_EVIDENCE_PROVIDERS)
        ],
    }


def _is_live(name: str) -> bool:
    """Heuristic flag: ``True`` for adapters that actually do work in this
    release, ``False`` for stubs that return not_configured."""
    return name in {
        LocalKeywordCsvProvider.provider_name,
        LocalSearchConsoleCsvProvider.provider_name,
        LocalSearchEvidenceCsvProvider.provider_name,
    }
