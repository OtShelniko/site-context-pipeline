"""Local CSV provider for search-performance data.

Built around Google Search Console's ``Performance`` export shape — the
de-facto standard for per-query performance data — but tolerant of any
CSV that uses similar column names. This adapter never calls Google.

Recognised columns (case-insensitive):

Required:
    query | top queries | search_term

Optional:
    page | landing_page | url
    clicks
    impressions
    ctr                 (12.3%, 0.123, 12,3 %)
    position | average position | average_position
    country | geo | location
    device
    date

Behaviour notes:

* If both ``query`` and ``page`` are present the row is preserved as-is —
  one keyword can map to many pages and vice versa. The context-pack
  builder aggregates per page itself; this provider stays a thin shim.
* CTR percentages are normalised to fractions in [0..1].
* Empty cells become ``None``, never zero.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ..schemas import KeywordMetric, ProviderResult
from .base import (
    ProviderConfigurationError,
    SearchPerformanceProvider,
    items_as_dicts,
)
from .local_keyword_csv import (
    _first_float,
    _first_int,
    _first_present,
    _first_ratio,
    _first_string,
    _normalise_header,
)

_QUERY_COLUMNS = ("query", "top queries", "top_queries", "search_term", "search term")
_PAGE_COLUMNS = ("page", "landing_page", "url", "address")


class LocalSearchConsoleCsvProvider(SearchPerformanceProvider):
    """Importer for Google Search Console-style CSV exports."""

    provider_name = "local-gsc-csv"

    def run(
        self,
        *,
        source: str | None = None,
        provider_config: dict[str, Any] | None = None,
    ) -> ProviderResult:
        if not source:
            raise ProviderConfigurationError(
                "local-gsc-csv provider requires --source PATH"
            )
        path = Path(source)
        if not path.exists():
            raise ProviderConfigurationError(f"search-performance csv not found: {path}")

        rows, parse_warnings = _read_rows(path)
        items: list[KeywordMetric] = []
        skipped_no_query = 0
        for row in rows:
            query = _first_present(row, _QUERY_COLUMNS)
            if not query:
                skipped_no_query += 1
                continue
            metric = KeywordMetric(
                query=str(query).strip(),
                source=self.provider_name,
                locale=_first_string(row, ("locale",)),
                geo=_first_string(row, ("country", "geo", "location")),
                language=_first_string(row, ("language", "lang")),
                avg_monthly_searches=None,
                impressions=_first_int(row, ("impressions",)),
                clicks=_first_int(row, ("clicks",)),
                ctr=_first_ratio(row, ("ctr", "click_through_rate")),
                position=_first_float(row, ("position", "average_position", "average position")),
                competition=None,
                source_url=_first_string(row, _PAGE_COLUMNS),
                raw=_extra_columns(row),
            )
            items.append(metric)

        warnings = list(parse_warnings)
        if skipped_no_query:
            warnings.append(f"skipped_rows_without_query:{skipped_no_query}")
        return ProviderResult(
            ok=True,
            provider=self.provider_name,
            dry_run=True,
            items=items_as_dicts(items),
            warnings=warnings,
            errors=[],
            metadata={
                "source_path": str(path),
                "row_count": len(rows),
                "items_count": len(items),
            },
        )


# ---------------------------------------------------------------------------


def _read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    warnings: list[str] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            rows = [{(k or "").strip(): (v if v is None else str(v)) for k, v in r.items()} for r in reader]
    except UnicodeDecodeError:
        warnings.append("csv_decoded_with_cp1251_fallback")
        with path.open("r", encoding="cp1251", newline="") as file:
            reader = csv.DictReader(file)
            rows = [{(k or "").strip(): (v if v is None else str(v)) for k, v in r.items()} for r in reader]
    return rows, warnings


_KNOWN_COLS = {
    *_QUERY_COLUMNS,
    *_PAGE_COLUMNS,
    "clicks",
    "impressions",
    "ctr",
    "click_through_rate",
    "position",
    "average_position",
    "average position",
    "country",
    "geo",
    "location",
    "device",
    "date",
    "locale",
    "language",
    "lang",
}


def _extra_columns(row: dict[str, str]) -> dict[str, Any]:
    extras: dict[str, Any] = {}
    known = {_normalise_header(name) for name in _KNOWN_COLS}
    for key, value in row.items():
        if not isinstance(key, str):
            continue
        normalised = _normalise_header(key)
        if normalised in known:
            # device/date are useful for downstream filtering, keep them
            if normalised in ("device", "date") and value not in (None, ""):
                extras[normalised] = value
            continue
        if value not in (None, ""):
            extras[key] = value
    return extras
