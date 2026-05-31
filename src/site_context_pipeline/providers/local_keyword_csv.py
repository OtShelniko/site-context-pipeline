"""Local CSV keyword provider.

The minimum-viable adapter: read a CSV from disk, normalise the columns,
emit ``KeywordMetric`` rows. The CSV can come from any tool that exports
keyword data (Google Ads Keyword Planner, Ahrefs, Semrush, hand-edited
research notes). The toolkit only cares about the shape, not the source.

Recognised column names (case-insensitive, several aliases each):

Required (one of):
    query | keyword | search_term

Optional:
    avg_monthly_searches | search_volume | volume | monthly_searches
    impressions
    clicks
    ctr
    position | rank | average_position
    competition | competition_value | difficulty
    locale
    geo | country | location
    language
    source_url | landing_page | url

Unknown columns are preserved in ``raw`` so no information is lost.

Numeric values are cleaned up gracefully: ``"1,234"`` → ``1234``,
``"12.3%"`` → ``0.123``, blanks → ``None``.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ..schemas import KeywordMetric, ProviderResult
from .base import KeywordProvider, ProviderConfigurationError, items_as_dicts

_QUERY_COLUMNS = ("query", "keyword", "search_term", "search term")
_INT_FIELDS: dict[str, tuple[str, ...]] = {
    "avg_monthly_searches": (
        "avg_monthly_searches",
        "average_monthly_searches",
        "search_volume",
        "search volume",
        "monthly_searches",
        "monthly searches",
        "volume",
        "searches",
    ),
    "impressions": ("impressions",),
    "clicks": ("clicks",),
}
_FLOAT_FIELDS: dict[str, tuple[str, ...]] = {
    "ctr": ("ctr", "click_through_rate", "click through rate"),
    "position": (
        "position",
        "average_position",
        "avg_position",
        "average position",
        "avg position",
        "rank",
    ),
}
_STRING_FIELDS: dict[str, tuple[str, ...]] = {
    "competition": ("competition", "competition_value", "difficulty"),
    "locale": ("locale",),
    "geo": ("geo", "country", "location"),
    "language": ("language", "lang"),
    "source_url": ("source_url", "landing_page", "landing page", "url"),
}


class LocalKeywordCsvProvider(KeywordProvider):
    """Importer for local keyword CSV exports."""

    provider_name = "local-csv"

    def run(
        self,
        *,
        source: str | None = None,
        provider_config: dict[str, Any] | None = None,
    ) -> ProviderResult:
        if not source:
            raise ProviderConfigurationError("local-csv provider requires --source PATH")
        path = Path(source)
        if not path.exists():
            raise ProviderConfigurationError(f"keyword csv not found: {path}")

        rows, parse_warnings = _read_rows(path)
        items: list[KeywordMetric] = []
        skipped = 0
        for row in rows:
            query = _first_present(row, _QUERY_COLUMNS)
            if not query:
                skipped += 1
                continue
            metric = KeywordMetric(
                query=str(query).strip(),
                source=self.provider_name,
                locale=_first_string(row, _STRING_FIELDS["locale"]),
                geo=_first_string(row, _STRING_FIELDS["geo"]),
                language=_first_string(row, _STRING_FIELDS["language"]),
                avg_monthly_searches=_first_int(row, _INT_FIELDS["avg_monthly_searches"]),
                impressions=_first_int(row, _INT_FIELDS["impressions"]),
                clicks=_first_int(row, _INT_FIELDS["clicks"]),
                ctr=_first_ratio(row, _FLOAT_FIELDS["ctr"]),
                position=_first_float(row, _FLOAT_FIELDS["position"]),
                competition=_first_string(row, _STRING_FIELDS["competition"]),
                source_url=_first_string(row, _STRING_FIELDS["source_url"]),
                raw=_strip_known(row),
            )
            items.append(metric)

        warnings = list(parse_warnings)
        if skipped:
            warnings.append(f"skipped_rows_without_query:{skipped}")
        return ProviderResult(
            ok=True,
            provider=self.provider_name,
            dry_run=True,  # the CLI flips this when --write is set
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
# CSV helpers (kept module-private; no public API surface)
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


def _first_present(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    """Look up ``row`` by any of ``names``, ignoring case and treating
    ``_``/``-``/space as equivalent so ``Search Volume``,
    ``search_volume``, and ``search-volume`` all match the same alias."""
    normalised_row = {_normalise_header(k): v for k, v in row.items() if isinstance(k, str)}
    for name in names:
        value = normalised_row.get(_normalise_header(name))
        if value not in (None, ""):
            return value
    return None


def _normalise_header(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _first_string(row: dict[str, Any], names: tuple[str, ...]) -> str | None:
    value = _first_present(row, names)
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _first_int(row: dict[str, Any], names: tuple[str, ...]) -> int | None:
    value = _first_present(row, names)
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _first_float(row: dict[str, Any], names: tuple[str, ...]) -> float | None:
    value = _first_present(row, names)
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", ".").replace(" ", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _first_ratio(row: dict[str, Any], names: tuple[str, ...]) -> float | None:
    """Parse a CTR-like value. Accepts ``0.123``, ``12.3%``, ``12,3 %``."""
    value = _first_present(row, names)
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", ".")
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1].strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if is_percent:
        return round(number / 100.0, 6)
    if number > 1.0:
        # Heuristic: a bare "12.3" without a percent sign is almost
        # certainly a percentage — Google Search Console exports CTR this
        # way when the locale uses commas as decimal separators.
        return round(number / 100.0, 6)
    return number


def _strip_known(row: dict[str, str]) -> dict[str, Any]:
    """Return columns we did NOT consume so the provenance is preserved."""
    known: set[str] = set()
    for group in (_QUERY_COLUMNS,):
        known.update(_normalise_header(name) for name in group)
    for group in (*_INT_FIELDS.values(), *_FLOAT_FIELDS.values(), *_STRING_FIELDS.values()):
        known.update(_normalise_header(name) for name in group)
    leftovers: dict[str, Any] = {}
    for key, value in row.items():
        if not isinstance(key, str):
            continue
        if _normalise_header(key) in known:
            continue
        if value not in (None, ""):
            leftovers[key] = value
    return leftovers
