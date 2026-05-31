"""Inventory builder: read URLs, normalise, classify, write JSON.

The classifier is intentionally simple and language-neutral. It reads two
optional config files from ``<client>/config/``:

* ``classifier.json`` — overrides the default URL-pattern rules.
* ``commercial_urls.json`` — explicit URL list to mark as ``landing``.

If neither file is present, a built-in rule set is used. Rules are evaluated
in priority order; the first match wins. The result records which rule fired
in ``classification_reason`` so the output is auditable.

No site-specific or client-specific defaults are baked in.
"""

from __future__ import annotations

import csv
import fnmatch
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from .clients import ClientPaths, read_json, write_json
from .importers import SitemapImportError, read_sitemap
from .schemas import InventoryItem, PageType

# Default rule set. Each rule is a (page_type, marker) pair. The marker is
# matched against the URL path with ``fnmatch`` semantics (so ``*`` works).
# Order matters: the first matching rule wins.
_DEFAULT_PATTERN_RULES: list[tuple[PageType, str]] = [
    ("blog", "*/blog/*"),
    ("blog", "*/news/*"),
    ("blog", "*/articles/*"),
    ("blog", "*/guides/*"),
    ("service", "*/services/*"),
    ("service", "*/service/*"),
    ("category", "*/category/*"),
    ("category", "*/categories/*"),
    ("category", "*/catalog/*"),
    ("category", "*/collections/*"),
    ("landing", "*/landing/*"),
    ("landing", "*/pricing*"),
    ("landing", "*/cart*"),
    ("landing", "*/checkout*"),
    ("landing", "*/buy*"),
]

# Columns we recognise in the input CSV. Names are matched case-insensitively
# against any of the synonyms; the first match wins.
_CSV_COLUMNS: dict[str, list[str]] = {
    "url": ["url", "address"],
    "title": ["title", "title 1"],
    "h1": ["h1", "h1-1"],
    "status_code": ["status_code", "status code", "status"],
    "word_count": ["word_count", "word count", "words"],
    "inlinks_count": ["inlinks_count", "inlinks count", "inlinks"],
    "outlinks_count": ["outlinks_count", "outlinks count", "outlinks"],
}


def build_inventory(
    paths: ClientPaths,
    *,
    write: bool,
    source: str | Path | None = None,
    source_format: str | None = None,
) -> dict[str, Any]:
    """Build ``data/content_inventory.json`` from a CSV / JSON / sitemap input.

    The ``source`` argument may be:

    * an explicit path to a ``.csv``, ``.json``, or sitemap ``.xml`` file, or
    * ``None``, in which case ``<client>/input/urls.csv`` is read.

    ``source_format`` forces a particular reader. Accepted values:

    * ``None`` or ``"auto"`` — pick by file extension (``.csv`` / ``.json`` /
      ``.xml``);
    * ``"csv"``, ``"json"`` — read the existing flat formats;
    * ``"sitemap"`` — read a ``sitemap.xml`` (or sitemap-index) using the
      offline importer in ``site_context_pipeline.importers.sitemap_xml``.
      Sitemap rows carry only a URL plus optional metadata; title, H1, and
      counts stay ``None``.
    """
    source_path = _resolve_source(source, paths)
    rows, detected_format, parse_warnings = _read_source(source_path, source_format)

    classifier_rules, classifier_source = _load_classifier_rules(paths)
    commercial_urls = _load_commercial_urls(paths)

    items: list[InventoryItem] = []
    seen_urls: set[str] = set()
    skipped: list[str] = []

    for raw_row in rows:
        url = _coerce_url(raw_row.get("url"))
        if not url:
            skipped.append("missing_url")
            continue
        normalised = normalise_url(url)
        if normalised in seen_urls:
            skipped.append(f"duplicate:{normalised}")
            continue
        seen_urls.add(normalised)

        page_type, reason = classify_url(
            normalised,
            commercial_urls=commercial_urls,
            rules=classifier_rules,
        )
        items.append(
            InventoryItem(
                url=normalised,
                path=urlparse(normalised).path or "/",
                page_type=page_type,
                classification_reason=reason,
                title=_string_or_none(raw_row.get("title")),
                h1=_string_or_none(raw_row.get("h1")),
                status_code=_int_or_none(raw_row.get("status_code")),
                word_count=_int_or_none(raw_row.get("word_count")),
                inlinks_count=_int_or_none(raw_row.get("inlinks_count")),
                outlinks_count=_int_or_none(raw_row.get("outlinks_count")),
                source=detected_format,
            )
        )

    serialised = sorted(
        (_inventory_item_to_dict(item) for item in items), key=lambda d: d["url"]
    )
    counts: dict[str, int] = {}
    for item in serialised:
        counts[item["page_type"]] = counts.get(item["page_type"], 0) + 1

    inventory_path = paths.data / "content_inventory.json"
    warnings = list(parse_warnings)
    if skipped:
        warnings.append(f"skipped_rows:{len(skipped)}")
    if classifier_source:
        warnings.append(f"classifier_source:{classifier_source}")

    result: dict[str, Any] = {
        "planned_writes": [str(inventory_path)],
        "source_path": str(source_path) if source_path else None,
        "source_format": detected_format,
        "items_count": len(serialised),
        "page_type_counts": dict(sorted(counts.items())),
        "warnings": warnings,
        "items": serialised,
    }
    if write:
        write_json(inventory_path, serialised)
        result["written_files"] = [str(inventory_path)]
    return result


def normalise_url(url: str) -> str:
    """Lower-case scheme/host, strip fragment, drop default ports.

    The toolkit treats two URLs as the same page if their normalised forms
    match. We do *not* strip query parameters here because some sites use
    them for canonical content (e.g. ``?lang=ru``).
    """
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = parsed.path or "/"
    # Collapse repeated slashes, but keep a leading slash.
    while "//" in path:
        path = path.replace("//", "/")
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def classify_url(
    url: str,
    *,
    commercial_urls: set[str],
    rules: list[tuple[PageType, str]],
) -> tuple[PageType, str]:
    """Return ``(page_type, classification_reason)`` for one URL.

    The order of checks is fixed so the result is stable:

    1. Explicit commercial URL list (highest authority).
    2. Home page check (path is ``/`` or empty).
    3. URL-pattern rules from config (or built-in defaults).
    4. Fallback to ``other``.
    """
    if url in commercial_urls:
        return "landing", "matched_commercial_url_list"

    parsed = urlparse(url)
    path = parsed.path or "/"
    if path in {"/", ""}:
        return "home", "matched_home_path"

    lowered = path.lower()
    for page_type, pattern in rules:
        if _match_path_pattern(lowered, pattern):
            return page_type, f"matched_pattern:{pattern}"

    return "other", "fallback_other"


def _match_path_pattern(path: str, pattern: str) -> bool:
    pattern = pattern.lower()
    if "*" in pattern:
        return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(
            path.rstrip("/"), pattern.rstrip("/")
        )
    return pattern in path


def _resolve_source(source: str | Path | None, paths: ClientPaths) -> Path | None:
    if source is None:
        candidate = paths.input / "urls.csv"
        return candidate if candidate.exists() else None
    return Path(source)


def _read_source(
    source_path: Path | None, source_format: str | None
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Pick the right reader.

    The selection rule:

    * ``source_format`` (when set to something other than ``"auto"``) wins.
    * Otherwise the file extension is used: ``.csv`` → CSV, ``.json`` → JSON,
      ``.xml`` → sitemap.
    * If neither yields a known format, return a clear warning so the caller
      can surface it.
    """
    if source_path is None:
        return [], "missing", ["no_source_provided_and_default_urls_csv_not_found"]
    if not source_path.exists():
        return [], "missing", [f"source_not_found:{source_path}"]

    chosen = (source_format or "auto").lower()
    if chosen == "auto":
        suffix = source_path.suffix.lower()
        if suffix == ".csv":
            chosen = "csv"
        elif suffix == ".json":
            chosen = "json"
        elif suffix == ".xml":
            chosen = "sitemap"
        else:
            return [], "unknown", [f"unsupported_source_extension:{suffix}"]

    if chosen == "csv":
        return _read_csv(source_path), "csv", []
    if chosen == "json":
        return _read_json_list(source_path), "json", []
    if chosen == "sitemap":
        return _read_sitemap_source(source_path)
    return [], "unknown", [f"unsupported_source_format:{chosen}"]


def _read_sitemap_source(
    source_path: Path,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Adapt sitemap rows to the inventory's expected dict shape.

    A sitemap exposes only the URL plus optional metadata (lastmod /
    changefreq / priority). All other inventory fields stay ``None`` —
    a later step (e.g. a Screaming Frog import or a manual edit) can fill
    them in.
    """
    try:
        sitemap = read_sitemap(source_path)
    except SitemapImportError as error:
        return [], "sitemap", [f"sitemap_import_error:{error}"]
    rows: list[dict[str, Any]] = []
    for entry in sitemap.get("rows") or []:
        rows.append(
            {
                "url": entry.get("url"),
                "title": None,
                "h1": None,
                "status_code": None,
                "word_count": None,
                "inlinks_count": None,
                "outlinks_count": None,
            }
        )
    warnings = [f"sitemap:{w}" for w in sitemap.get("warnings") or []]
    return rows, "sitemap", warnings


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = []
        for raw in reader:
            normalised = {}
            for canonical, synonyms in _CSV_COLUMNS.items():
                value = _first_present(raw, synonyms)
                normalised[canonical] = value
            rows.append(normalised)
        return rows


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        loaded = json.load(file)
    if not isinstance(loaded, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in loaded:
        if not isinstance(entry, dict):
            continue
        out.append(
            {
                "url": entry.get("url"),
                "title": entry.get("title"),
                "h1": entry.get("h1"),
                "status_code": entry.get("status_code"),
                "word_count": entry.get("word_count"),
                "inlinks_count": entry.get("inlinks_count"),
                "outlinks_count": entry.get("outlinks_count"),
            }
        )
    return out


def _first_present(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
        # Also try a case-insensitive header match
        for key in row.keys():
            if isinstance(key, str) and key.lower() == name.lower() and row[key] not in (None, ""):
                return row[key]
    return None


def _load_classifier_rules(
    paths: ClientPaths,
) -> tuple[list[tuple[PageType, str]], str | None]:
    """Read user-supplied rules or fall back to built-in defaults."""
    config_path = paths.config / "classifier.json"
    if not config_path.exists():
        return list(_DEFAULT_PATTERN_RULES), None
    raw = read_json(config_path, None)
    if not isinstance(raw, dict):
        return list(_DEFAULT_PATTERN_RULES), "classifier_json_invalid"
    rules_raw = raw.get("rules") or []
    rules: list[tuple[PageType, str]] = []
    for entry in rules_raw:
        if not isinstance(entry, dict):
            continue
        page_type = entry.get("page_type")
        pattern = entry.get("pattern")
        if not page_type or not pattern:
            continue
        if page_type not in {"home", "service", "blog", "category", "landing", "other"}:
            continue
        rules.append((page_type, str(pattern)))
    if not rules:
        return list(_DEFAULT_PATTERN_RULES), "classifier_json_empty_using_defaults"
    return rules, str(config_path)


def _load_commercial_urls(paths: ClientPaths) -> set[str]:
    config_path = paths.config / "commercial_urls.json"
    if not config_path.exists():
        return set()
    raw = read_json(config_path, [])
    if not isinstance(raw, list):
        return set()
    return {normalise_url(str(url)) for url in raw if isinstance(url, str) and url.strip()}


def _coerce_url(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if not text.startswith(("http://", "https://")):
        return None
    return text


def _string_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _inventory_item_to_dict(item: InventoryItem) -> dict[str, Any]:
    return {
        "url": item.url,
        "path": item.path,
        "page_type": item.page_type,
        "classification_reason": item.classification_reason,
        "title": item.title,
        "h1": item.h1,
        "status_code": item.status_code,
        "word_count": item.word_count,
        "inlinks_count": item.inlinks_count,
        "outlinks_count": item.outlinks_count,
        "source": item.source,
    }
