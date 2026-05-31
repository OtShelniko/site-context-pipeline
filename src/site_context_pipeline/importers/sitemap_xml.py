"""Read a local sitemap.xml (or sitemap-index) into the row shape that
``build_inventory`` accepts as JSON input.

The importer is intentionally tiny:

* pure stdlib (``xml.etree.ElementTree``);
* offline — child sitemaps referenced by absolute ``http://`` / ``https://``
  URLs inside a sitemap-index are *reported* in ``warnings``, not fetched;
* tolerant of the missing namespace many CMSes emit;
* preserves optional metadata (``lastmod``, ``changefreq``, ``priority``)
  inside each row's ``raw`` dict.

Result shape::

    {
        "rows": [
            {"url": "https://example.com/", "raw": {"lastmod": "..."}},
            ...
        ],
        "sources": ["/abs/path/sitemap.xml", "/abs/path/sitemap_a.xml"],
        "warnings": ["empty_sitemap", "skipped_remote_child_sitemap:https://..."],
    }
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

# Sitemaps.org schema. We accept both the namespaced form and the unqualified
# form some CMSes emit by accident.
_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_NS_MAP = {"sm": _SITEMAP_NS}

# Optional per-URL metadata we surface into ``raw``.
_METADATA_KEYS = ("lastmod", "changefreq", "priority")


class SitemapImportError(Exception):
    """Raised on malformed XML, missing files, or roots that are not a
    sitemap or sitemap-index."""


def read_sitemap(path: str | Path) -> dict[str, Any]:
    """Read one sitemap (or sitemap-index) at ``path``. Returns a dict with
    ``rows``, ``sources``, ``warnings``."""
    main_path = Path(path)
    if not main_path.exists():
        raise SitemapImportError(f"sitemap not found: {main_path}")

    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    warnings: list[str] = []
    seen_urls: set[str] = set()
    visited: set[Path] = set()

    _process_file(
        main_path,
        rows=rows,
        sources=sources,
        warnings=warnings,
        seen_urls=seen_urls,
        visited=visited,
    )

    if not rows:
        warnings.append("empty_sitemap")

    return {"rows": rows, "sources": sources, "warnings": warnings}


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _process_file(
    path: Path,
    *,
    rows: list[dict[str, Any]],
    sources: list[str],
    warnings: list[str],
    seen_urls: set[str],
    visited: set[Path],
) -> None:
    """Parse one sitemap or sitemap-index file. Recurses through local
    child sitemaps but never fetches remote ones."""
    resolved = path.resolve()
    if resolved in visited:
        warnings.append(f"already_visited:{resolved}")
        return
    visited.add(resolved)
    sources.append(str(resolved))

    try:
        tree = ET.parse(resolved)
    except ET.ParseError as error:
        raise SitemapImportError(
            f"sitemap parse error in {resolved}: {error}"
        ) from error

    root = tree.getroot()
    local_name = _strip_ns(root.tag)

    if local_name == "urlset":
        _collect_urls(root, rows=rows, seen_urls=seen_urls)
    elif local_name == "sitemapindex":
        _follow_index(
            root,
            base=resolved,
            rows=rows,
            sources=sources,
            warnings=warnings,
            seen_urls=seen_urls,
            visited=visited,
        )
    else:
        raise SitemapImportError(
            f"{resolved}: root element is <{local_name}>; "
            "expected <urlset> or <sitemapindex>"
        )


def _collect_urls(
    root: ET.Element,
    *,
    rows: list[dict[str, Any]],
    seen_urls: set[str],
) -> None:
    """Append one row per ``<url><loc>`` entry, deduping against
    ``seen_urls`` so a sitemap-index that lists overlapping children does
    not produce duplicates."""
    for url_node in _find_children(root, "url"):
        loc = _text(url_node, "loc")
        if not loc:
            continue
        if loc in seen_urls:
            continue
        seen_urls.add(loc)
        raw: dict[str, Any] = {}
        for key in _METADATA_KEYS:
            value = _text(url_node, key)
            if value:
                raw[key] = value
        rows.append({"url": loc, "raw": raw})


def _follow_index(
    root: ET.Element,
    *,
    base: Path,
    rows: list[dict[str, Any]],
    sources: list[str],
    warnings: list[str],
    seen_urls: set[str],
    visited: set[Path],
) -> None:
    """Walk a ``<sitemapindex>``. Resolve each ``<loc>`` against the index
    file's directory; remote URLs are reported but not fetched."""
    base_dir = base.parent
    for sitemap_node in _find_children(root, "sitemap"):
        loc = _text(sitemap_node, "loc")
        if not loc:
            continue
        if loc.startswith(("http://", "https://")):
            warnings.append(f"skipped_remote_child_sitemap:{loc}")
            continue
        child_path = (base_dir / loc).resolve()
        if not child_path.exists():
            warnings.append(f"missing_child_sitemap:{loc}")
            continue
        _process_file(
            child_path,
            rows=rows,
            sources=sources,
            warnings=warnings,
            seen_urls=seen_urls,
            visited=visited,
        )


def _find_children(root: ET.Element, name: str) -> list[ET.Element]:
    """Find direct ``<name>`` children, with or without the sitemap
    namespace. ElementTree's ``findall`` requires the namespace prefix when
    one is declared; some CMSes drop it, so we try both."""
    namespaced = root.findall(f"sm:{name}", _NS_MAP)
    if namespaced:
        return namespaced
    return root.findall(name)


def _text(node: ET.Element, name: str) -> str:
    """Return the trimmed text of the first matching child, or empty."""
    for child in _find_children(node, name):
        if child.text is not None:
            return child.text.strip()
    return ""


def _strip_ns(tag: str) -> str:
    """``{http://...}urlset`` → ``urlset``."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag
