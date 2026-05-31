"""Read Screaming Frog SEO Spider CSV exports.

Screaming Frog ships two kinds of CSV the toolkit cares about:

1. **Inventory exports** — usually called ``internal_html.csv``,
   ``internal_all.csv``, or just ``internal.csv``. One row per crawled
   URL, with columns like ``Address``, ``Status Code``, ``Title 1``,
   ``H1-1``, ``Word Count``, ``Inlinks``, ``Outlinks``.
2. **Link exports** — ``all_inlinks.csv`` / ``all_outlinks.csv``. One
   row per anchor with columns ``Source``, ``Destination``,
   ``Anchor Text``, plus a long tail of metadata.

This adapter normalises both into the row shapes the toolkit's builders
expect:

* ``read_inventory_csv(path)`` → rows with ``url``, ``title``, ``h1``,
  ``status_code``, ``word_count``, ``inlinks_count``, ``outlinks_count``,
  plus a ``raw`` dict of unconsumed columns.
* ``read_link_csv(path)`` → rows with ``source_url``, ``target_url``,
  ``anchor_text``, plus ``raw`` for everything else.

Older Screaming Frog versions used different column names (``Title``
instead of ``Title 1``, ``H1`` instead of ``H1-1``, ``From``/``To``
instead of ``Source``/``Destination``). The importer accepts both.
Header matching is case-insensitive; whitespace, ``_``, and ``-`` in
header names are treated as equivalent.

Stdlib only. Never makes a network call.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Column dictionaries. First match wins; aliases are listed in a stable
# order so the code is easy to audit.
# ---------------------------------------------------------------------------

_INVENTORY_COLUMNS: dict[str, tuple[str, ...]] = {
    "url": ("address", "url"),
    "title": ("title 1", "title"),
    "h1": ("h1-1", "h1"),
    "status_code": ("status code", "status"),
    "word_count": ("word count", "words"),
    "inlinks_count": ("inlinks", "unique inlinks"),
    "outlinks_count": ("outlinks", "unique outlinks"),
}

_LINK_COLUMNS: dict[str, tuple[str, ...]] = {
    "source_url": ("source", "from", "source url"),
    "target_url": ("destination", "to", "target", "target url"),
    "anchor_text": ("anchor text", "anchor", "alt text"),
}


class ScreamingFrogImportError(Exception):
    """Raised on malformed CSVs or unknown flavour."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_inventory_csv(path: str | Path) -> dict[str, Any]:
    """Read a Screaming Frog inventory CSV (``internal_*.csv``).

    Returns ``{"rows": [...], "sources": [path], "warnings": [...]}``.
    Each row is a dict with the canonical inventory keys plus a ``raw``
    dict for unconsumed columns.
    """
    target = Path(path)
    if not target.exists():
        raise ScreamingFrogImportError(f"screaming-frog inventory csv not found: {target}")

    headers, rows = _read_csv(target)
    if not _has_url_column(headers):
        raise ScreamingFrogImportError(
            f"{target}: no Address/URL column found; "
            "is this a Screaming Frog 'internal_*.csv' export?"
        )

    out: list[dict[str, Any]] = []
    skipped_no_url = 0
    for raw in rows:
        url = _first_present(raw, _INVENTORY_COLUMNS["url"])
        if not url:
            skipped_no_url += 1
            continue
        row: dict[str, Any] = {"url": str(url).strip()}
        for canonical, aliases in _INVENTORY_COLUMNS.items():
            if canonical == "url":
                continue
            value = _first_present(raw, aliases)
            row[canonical] = _string_or_none(value)
        row["raw"] = _strip_known(raw, _INVENTORY_COLUMNS)
        out.append(row)

    warnings: list[str] = []
    if skipped_no_url:
        warnings.append(f"skipped_rows_without_url:{skipped_no_url}")

    return {"rows": out, "sources": [str(target)], "warnings": warnings}


def read_link_csv(path: str | Path) -> dict[str, Any]:
    """Read a Screaming Frog link CSV (``all_inlinks.csv``,
    ``all_outlinks.csv``).

    Returns ``{"rows": [...], "sources": [path], "warnings": [...]}``.
    Each row is a dict with ``source_url``, ``target_url``,
    ``anchor_text``, plus a ``raw`` dict for unconsumed columns.
    """
    target = Path(path)
    if not target.exists():
        raise ScreamingFrogImportError(f"screaming-frog link csv not found: {target}")

    headers, rows = _read_csv(target)
    if not _has_link_columns(headers):
        raise ScreamingFrogImportError(
            f"{target}: no Source/Destination columns found; "
            "is this a Screaming Frog 'all_inlinks.csv' export?"
        )

    out: list[dict[str, Any]] = []
    skipped = 0
    for raw in rows:
        source = _first_present(raw, _LINK_COLUMNS["source_url"])
        target_url = _first_present(raw, _LINK_COLUMNS["target_url"])
        if not source or not target_url:
            skipped += 1
            continue
        out.append(
            {
                "source_url": str(source).strip(),
                "target_url": str(target_url).strip(),
                "anchor_text": _string_or_none(
                    _first_present(raw, _LINK_COLUMNS["anchor_text"])
                ),
                "raw": _strip_known(raw, _LINK_COLUMNS),
            }
        )

    warnings: list[str] = []
    if skipped:
        warnings.append(f"skipped_rows_without_endpoints:{skipped}")

    return {"rows": out, "sources": [str(target)], "warnings": warnings}


def detect_flavour(path: str | Path) -> str:
    """Return ``"inventory"``, ``"links"``, or ``"unknown"``.

    Used by ``--format auto`` to pick the right Screaming Frog reader
    without forcing the user to know which file they have. The check is
    purely header-based and never reads more than one row.
    """
    target = Path(path)
    if not target.exists():
        return "unknown"
    try:
        headers, _ = _peek_headers(target)
    except (OSError, csv.Error):
        return "unknown"
    if _has_link_columns(headers):
        return "links"
    if _has_url_column(headers):
        return "inventory"
    return "unknown"


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read the CSV with a UTF-8-with-BOM tolerant decoder."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            headers = list(reader.fieldnames or [])
            rows = [
                {(k or "").strip(): (v if v is None else str(v)) for k, v in row.items()}
                for row in reader
            ]
        return headers, rows
    except UnicodeDecodeError as error:
        raise ScreamingFrogImportError(
            f"{path}: cannot decode as UTF-8: {error}"
        ) from error
    except csv.Error as error:
        raise ScreamingFrogImportError(f"{path}: csv parse error: {error}") from error


def _peek_headers(path: Path) -> tuple[list[str], None]:
    """Return just the header row, without consuming the rest of the CSV."""
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        headers = next(reader, [])
    return [str(h).strip() for h in headers], None


def _normalise_header(value: str) -> str:
    """``"Status Code"`` and ``"status_code"`` both become ``"statuscode"``."""
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _first_present(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    """Look up ``row`` by any of ``aliases``, ignoring case and treating
    spaces / underscores / dashes as equivalent."""
    normalised = {_normalise_header(k): v for k, v in row.items() if isinstance(k, str)}
    for alias in aliases:
        value = normalised.get(_normalise_header(alias))
        if value not in (None, ""):
            return value
    return None


def _has_url_column(headers: list[str]) -> bool:
    keys = {_normalise_header(h) for h in headers}
    return any(_normalise_header(alias) in keys for alias in _INVENTORY_COLUMNS["url"])


def _has_link_columns(headers: list[str]) -> bool:
    keys = {_normalise_header(h) for h in headers}
    has_source = any(_normalise_header(a) in keys for a in _LINK_COLUMNS["source_url"])
    has_target = any(_normalise_header(a) in keys for a in _LINK_COLUMNS["target_url"])
    return has_source and has_target


def _strip_known(
    row: dict[str, str], known_columns: dict[str, tuple[str, ...]]
) -> dict[str, Any]:
    """Return the columns we did NOT consume so provenance is preserved.

    Empty string values are dropped to keep the ``raw`` dict tidy. Any
    column that *we* mapped onto a canonical key is excluded.
    """
    consumed: set[str] = set()
    for aliases in known_columns.values():
        for alias in aliases:
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


def _string_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None
