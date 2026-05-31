"""Local CSV provider for hand-curated search-evidence rows.

The toolkit deliberately does not scrape a SERP. When you want to feed
"this is what competitors look like for query X" into the context
pack, you either export from a SERP API into a CSV or curate one by
hand. Either way, the CSV shape this provider expects is:

    query, rank, title, url, snippet, page_type

Recognised header aliases (case-insensitive; ``_``/``-``/space treated
as equivalent so ``Page Type`` ≡ ``page_type`` ≡ ``page-type``):

| Canonical    | Aliases |
|--------------|---------|
| ``query``    | ``keyword``, ``search_term`` |
| ``rank``     | ``position``, ``serp_position``, ``rank_position`` |
| ``title``    | (just ``title``) |
| ``url``      | ``link``, ``page``, ``landing_page`` |
| ``snippet``  | ``snippet_text``, ``description``, ``meta_description`` |
| ``page_type``| ``type``, ``result_type`` |

Unknown columns are preserved in each row's ``raw`` dict so the
provenance is intact and downstream consumers can read the extra
fields if they want to.

Stdlib only. Never makes a network call.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ..schemas import ProviderResult, SearchEvidence
from .base import (
    ProviderConfigurationError,
    SearchEvidenceProvider,
    items_as_dicts,
)

_QUERY_COLUMNS = ("query", "keyword", "search_term", "search term")
_RANK_COLUMNS = ("rank", "position", "serp_position", "rank_position")
_TITLE_COLUMNS = ("title",)
_URL_COLUMNS = ("url", "link", "page", "landing_page", "landing page")
_SNIPPET_COLUMNS = ("snippet", "snippet_text", "description", "meta_description", "meta description")
_PAGE_TYPE_COLUMNS = ("page_type", "page type", "type", "result_type", "result type")


class LocalSearchEvidenceCsvProvider(SearchEvidenceProvider):
    """Importer for local search-evidence CSV files."""

    provider_name = "local-serp-csv"

    def run(
        self,
        *,
        source: str | None = None,
        provider_config: dict[str, Any] | None = None,
    ) -> ProviderResult:
        if not source:
            raise ProviderConfigurationError(
                "local-serp-csv provider requires --source PATH"
            )
        path = Path(source)
        if not path.exists():
            raise ProviderConfigurationError(
                f"search-evidence csv not found: {path}"
            )

        rows, parse_warnings = _read_rows(path)
        if rows and not _has_query_column(rows[0]):
            raise ProviderConfigurationError(
                f"{path}: no `query` column found; expected one of "
                f"{', '.join(_QUERY_COLUMNS)}"
            )

        items: list[SearchEvidence] = []
        skipped_no_query = 0
        seen_queries: set[str] = set()
        for raw in rows:
            query = _first_string(raw, _QUERY_COLUMNS)
            if not query:
                skipped_no_query += 1
                continue
            seen_queries.add(query.lower())
            items.append(
                SearchEvidence(
                    query=query,
                    source=self.provider_name,
                    title=_first_string(raw, _TITLE_COLUMNS),
                    url=_first_string(raw, _URL_COLUMNS),
                    snippet=_first_string(raw, _SNIPPET_COLUMNS),
                    rank=_first_int(raw, _RANK_COLUMNS),
                    page_type=_first_string(raw, _PAGE_TYPE_COLUMNS),
                    raw=_strip_known(raw),
                )
            )

        warnings = list(parse_warnings)
        if skipped_no_query:
            warnings.append(f"skipped_rows_without_query:{skipped_no_query}")

        return ProviderResult(
            ok=True,
            provider=self.provider_name,
            dry_run=True,  # CLI flips this when --write is set
            items=items_as_dicts(items),
            warnings=warnings,
            errors=[],
            metadata={
                "source_path": str(path),
                "row_count": len(rows),
                "items_count": len(items),
                "distinct_queries": len(seen_queries),
            },
        )


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------


def _read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    warnings: list[str] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            rows = [_clean_row(row) for row in reader]
    except UnicodeDecodeError:
        warnings.append("csv_decoded_with_cp1251_fallback")
        with path.open("r", encoding="cp1251", newline="") as file:
            reader = csv.DictReader(file)
            rows = [_clean_row(row) for row in reader]
    return rows, warnings


def _clean_row(row: dict[str | Any, str | None]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in row.items():
        if not isinstance(key, str):
            continue
        stripped_key = key.strip()
        if not stripped_key:
            continue
        cleaned[stripped_key] = "" if value is None else str(value)
    return cleaned


def _normalise_header(value: str) -> str:
    """Match `Page Type`, `page_type`, `page-type`, `pagetype` as one."""
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _first_present(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    normalised = {_normalise_header(k): v for k, v in row.items() if isinstance(k, str)}
    for alias in aliases:
        value = normalised.get(_normalise_header(alias))
        if value not in (None, ""):
            return value
    return None


def _first_string(row: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    value = _first_present(row, aliases)
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _first_int(row: dict[str, Any], aliases: tuple[str, ...]) -> int | None:
    value = _first_present(row, aliases)
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _has_query_column(row: dict[str, Any]) -> bool:
    keys = {_normalise_header(k) for k in row.keys() if isinstance(k, str)}
    return any(_normalise_header(alias) in keys for alias in _QUERY_COLUMNS)


_KNOWN_COLUMNS: tuple[tuple[str, ...], ...] = (
    _QUERY_COLUMNS,
    _RANK_COLUMNS,
    _TITLE_COLUMNS,
    _URL_COLUMNS,
    _SNIPPET_COLUMNS,
    _PAGE_TYPE_COLUMNS,
)


def _strip_known(row: dict[str, str]) -> dict[str, Any]:
    consumed: set[str] = set()
    for group in _KNOWN_COLUMNS:
        for alias in group:
            consumed.add(_normalise_header(alias))
    leftovers: dict[str, Any] = {}
    for key, value in row.items():
        if not isinstance(key, str):
            continue
        if _normalise_header(key) in consumed:
            continue
        if value in (None, ""):
            continue
        leftovers[key.strip().lower()] = value
    return leftovers
