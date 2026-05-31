"""Inventory builder: read URLs, normalise, classify, write JSON.

The classifier is intentionally simple and language-neutral. It reads two
optional config files from ``<client>/config/``:

* ``classifier.json`` — overrides the default URL-pattern rules. Two
  schemas are supported:

  - **Legacy (still works):** a flat list of
    ``{"page_type": "...", "pattern": "..."}`` dicts. First match wins.

  - **Extended:** the same dict can also carry ``priority`` (lower
    = earlier; ties broken by list order), ``exclude_patterns`` (a list
    of patterns that block the rule even when ``pattern`` matches), and
    ``allow_urls`` (an explicit list of URLs that *always* match this
    rule, regardless of ``pattern``).

* ``commercial_urls.json`` — explicit URL list to mark as ``landing``.

If neither file is present, a built-in rule set is used. The result
records which rule fired in ``classification_reason`` so the output is
auditable.

No site-specific or client-specific defaults are baked in.
"""

from __future__ import annotations

import csv
import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from .clients import ClientPaths, read_json, write_json
from .importers import (
    ScreamingFrogImportError,
    SitemapImportError,
    detect_screaming_frog_flavour,
    read_screaming_frog_inventory,
    read_sitemap,
)
from .schemas import InventoryItem, PageType

# All page types the classifier may emit. Used to validate config-supplied
# rules before they reach ``classify_url``.
_VALID_PAGE_TYPES: frozenset[str] = frozenset(
    {"home", "service", "blog", "category", "landing", "other"}
)


@dataclass(frozen=True)
class ClassifierRule:
    """One configurable URL-classification rule.

    ``priority`` is sorted ascending — the lowest number wins. Ties
    are broken by the rule's original position in the config (so
    re-ordering the JSON file is meaningful even when priorities are
    equal). The defaults match the order of the built-in rule set.
    """

    page_type: PageType
    pattern: str
    priority: int = 100
    exclude_patterns: tuple[str, ...] = ()
    allow_urls: frozenset[str] = field(default_factory=frozenset)


# Default rule set. Each rule is a (page_type, pattern) pair; we wrap
# them into ``ClassifierRule`` instances at load time so the built-in
# and the user-supplied paths share one execution path.
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

    classifier_rules, classifier_source, classifier_warnings = _load_classifier_rules(paths)
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
    warnings.extend(classifier_warnings)

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
    rules: list[ClassifierRule] | list[tuple[PageType, str]],
) -> tuple[PageType, str]:
    """Return ``(page_type, classification_reason)`` for one URL.

    The order of checks is fixed so the result is stable:

    1. Explicit commercial URL list (highest authority).
    2. Home page check (path is ``/`` or empty).
    3. Per-rule ``allow_urls`` — if the URL is on any rule's allow list,
       that rule wins regardless of pattern.
    4. URL-pattern rules from config (or built-in defaults), evaluated
       in priority order. Each rule's ``exclude_patterns`` can block
       the match.
    5. Fallback to ``other``.

    The function accepts both the new ``ClassifierRule`` objects and
    legacy ``(page_type, pattern)`` tuples so callers that already use
    the simple form keep working.
    """
    if url in commercial_urls:
        return "landing", "matched_commercial_url_list"

    parsed = urlparse(url)
    path = parsed.path or "/"
    if path in {"/", ""}:
        return "home", "matched_home_path"

    normalised_rules = [_coerce_rule(rule) for rule in rules]

    # 3. allow_urls take precedence over patterns; the first allow-match
    # in priority order wins so users can layer override rules.
    for rule in sorted(normalised_rules, key=lambda r: r.priority):
        if url in rule.allow_urls:
            return rule.page_type, f"matched_allow_url:{rule.page_type}"

    # 4. pattern rules with optional negation.
    lowered = path.lower()
    for rule in sorted(normalised_rules, key=lambda r: r.priority):
        if not _match_path_pattern(lowered, rule.pattern):
            continue
        if any(_match_path_pattern(lowered, ex) for ex in rule.exclude_patterns):
            continue
        return rule.page_type, f"matched_pattern:{rule.pattern}"

    return "other", "fallback_other"


def _coerce_rule(
    rule: ClassifierRule | tuple[PageType, str],
) -> ClassifierRule:
    """Accept legacy 2-tuples so old callers keep working."""
    if isinstance(rule, ClassifierRule):
        return rule
    page_type, pattern = rule
    return ClassifierRule(page_type=page_type, pattern=pattern)


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
      ``.xml`` → sitemap. For ``.csv`` we also peek at the header row;
      Screaming Frog inventory exports (``Address``, ``Title 1``, ``H1-1``)
      get routed to the SF reader so users do not have to know the format
      name.
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
            # Header-based sniff for Screaming Frog inventory CSVs.
            if detect_screaming_frog_flavour(source_path) == "inventory":
                chosen = "screaming-frog"
            else:
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
    if chosen == "screaming-frog":
        return _read_screaming_frog_inventory_source(source_path)
    return [], "unknown", [f"unsupported_source_format:{chosen}"]


def _read_screaming_frog_inventory_source(
    source_path: Path,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Adapt Screaming Frog inventory rows to ``build_inventory``'s shape."""
    try:
        sf = read_screaming_frog_inventory(source_path)
    except ScreamingFrogImportError as error:
        return [], "screaming-frog", [f"screaming_frog_import_error:{error}"]
    return list(sf.get("rows") or []), "screaming-frog", list(sf.get("warnings") or [])


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
) -> tuple[list[ClassifierRule], str | None, list[str]]:
    """Read user-supplied rules or fall back to built-in defaults.

    Returns ``(rules, source, warnings)`` where:
      * ``rules`` is the parsed rule list (built-in defaults if the file
        is absent / unreadable / empty);
      * ``source`` is a short marker for diagnostics
        (``"classifier_json_invalid"``, the file path, ``None``, etc.);
      * ``warnings`` lists structural problems we surfaced (an unknown
        ``page_type``, a non-string pattern, etc.) so the inventory
        builder can include them in the artifact.
    """
    config_path = paths.config / "classifier.json"
    if not config_path.exists():
        return _default_rules(), None, []
    try:
        raw = read_json(config_path, None)
    except (OSError, json.JSONDecodeError):
        return _default_rules(), "classifier_json_invalid", ["classifier_json_invalid"]
    if not isinstance(raw, dict):
        return _default_rules(), "classifier_json_invalid", ["classifier_json_invalid"]
    rules_raw = raw.get("rules") or []

    rules: list[ClassifierRule] = []
    warnings: list[str] = []
    for index, entry in enumerate(rules_raw):
        if not isinstance(entry, dict):
            warnings.append(f"classifier_rule_not_object:index={index}")
            continue
        page_type = entry.get("page_type")
        pattern = entry.get("pattern")
        if not page_type or not pattern:
            warnings.append(f"classifier_rule_missing_fields:index={index}")
            continue
        if page_type not in _VALID_PAGE_TYPES:
            warnings.append(
                f"classifier_rule_invalid_page_type:index={index},value={page_type}"
            )
            continue
        priority = entry.get("priority", 100)
        try:
            priority_int = int(priority)
        except (TypeError, ValueError):
            warnings.append(f"classifier_rule_invalid_priority:index={index}")
            priority_int = 100
        # Tie-breaker: append the index as a fractional component so the
        # original list order is preserved when priorities collide.
        # ``priority`` stays an int on the dataclass; we sort with the
        # tuple ``(priority, index)`` outside, but only for legacy
        # callers — here we encode the index into the priority itself.
        priority_with_index = priority_int * 1000 + index

        exclude_raw = entry.get("exclude_patterns") or []
        exclude_patterns: tuple[str, ...]
        if isinstance(exclude_raw, list):
            exclude_patterns = tuple(
                str(p) for p in exclude_raw if isinstance(p, str) and p.strip()
            )
        else:
            warnings.append(f"classifier_rule_invalid_exclude_patterns:index={index}")
            exclude_patterns = ()

        allow_raw = entry.get("allow_urls") or []
        if isinstance(allow_raw, list):
            allow_urls = frozenset(
                str(u).strip() for u in allow_raw if isinstance(u, str) and u.strip()
            )
        else:
            warnings.append(f"classifier_rule_invalid_allow_urls:index={index}")
            allow_urls = frozenset()

        rules.append(
            ClassifierRule(
                page_type=page_type,
                pattern=str(pattern),
                priority=priority_with_index,
                exclude_patterns=exclude_patterns,
                allow_urls=allow_urls,
            )
        )

    if not rules:
        warnings.append("classifier_json_empty_using_defaults")
        return _default_rules(), "classifier_json_empty_using_defaults", warnings

    return rules, str(config_path), warnings


def _default_rules() -> list[ClassifierRule]:
    """Materialise the built-in patterns as ``ClassifierRule`` objects.

    The priority here is the index in ``_DEFAULT_PATTERN_RULES`` so the
    legacy first-match-wins ordering is preserved.
    """
    return [
        ClassifierRule(
            page_type=page_type,
            pattern=pattern,
            priority=index,
        )
        for index, (page_type, pattern) in enumerate(_DEFAULT_PATTERN_RULES)
    ]


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
