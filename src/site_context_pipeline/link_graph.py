"""Internal link graph builder.

Reads a CSV (or JSON) edge list from ``<client>/input/links.csv`` and joins
it with the page inventory at ``<client>/data/content_inventory.json``. The
result is written to ``<client>/data/internal_link_graph.json``.

Two simple opportunity lists are derived:

* ``commercial_pages_low_blog_inlinks`` — landing/service/category pages
  that receive zero inlinks from blog pages.
* ``blog_pages_low_inlinks`` — blog pages with at most one inlink.

These are heuristic suggestions, not authoritative rankings.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .clients import ClientPaths, read_json, write_json
from .importers import (
    ScreamingFrogImportError,
    detect_screaming_frog_flavour,
    read_screaming_frog_links,
)
from .inventory import normalise_url
from .schemas import LinkEdge, LinkNode

_COMMERCIAL_TYPES = {"landing", "service", "category"}

_CSV_COLUMNS: dict[str, list[str]] = {
    "source_url": ["source_url", "source", "from"],
    "target_url": ["target_url", "target", "to", "destination"],
    "anchor_text": ["anchor_text", "anchor", "link_text"],
}


def build_link_graph(
    paths: ClientPaths,
    *,
    write: bool,
    source: str | Path | None = None,
    source_format: str | None = None,
) -> dict[str, Any]:
    """Build ``data/internal_link_graph.json``.

    ``source`` may be a path to a CSV/JSON edge list, or ``None`` to default
    to ``<client>/input/links.csv``. ``source_format`` forces a particular
    reader (``auto``, ``csv``, ``json``, ``screaming-frog``); ``auto``
    picks by extension and sniffs CSV headers — Screaming Frog
    ``all_inlinks.csv`` exports get auto-routed to the SF reader.

    If no edge list is available the graph still contains nodes derived
    from the inventory; edges are empty and a warning is recorded.
    """
    inventory_path = paths.data / "content_inventory.json"
    inventory_raw = read_json(inventory_path, [])
    inventory = inventory_raw if isinstance(inventory_raw, list) else []
    inventory_by_url = {
        item.get("url"): item
        for item in inventory
        if isinstance(item, dict) and item.get("url")
    }

    source_path = _resolve_source(source, paths)
    edge_rows, detected_format, parse_warnings = _read_source(source_path, source_format)

    inlinks: dict[str, set[str]] = defaultdict(set)
    outlinks: dict[str, set[str]] = defaultdict(set)
    edges_by_key: dict[tuple[str, str, str], LinkEdge] = {}

    for raw in edge_rows:
        source_url = _normalise_optional(raw.get("source_url"))
        target_url = _normalise_optional(raw.get("target_url"))
        if not source_url or not target_url or source_url == target_url:
            continue
        anchor = _string_or_none(raw.get("anchor_text"))
        key = (source_url, target_url, anchor or "")
        edges_by_key[key] = LinkEdge(source_url=source_url, target_url=target_url, anchor_text=anchor)
        inlinks[target_url].add(source_url)
        outlinks[source_url].add(target_url)

    all_urls = set(inventory_by_url) | set(inlinks) | set(outlinks)
    nodes: list[LinkNode] = []
    for url in sorted(all_urls):
        item = inventory_by_url.get(url, {})
        page_type = str(item.get("page_type") or "other")
        explicit_inlinks = len(inlinks[url])
        explicit_outlinks = len(outlinks[url])
        fallback_inlinks = item.get("inlinks_count")
        fallback_outlinks = item.get("outlinks_count")
        blog_inlinks = sum(
            1 for src in inlinks[url] if str(inventory_by_url.get(src, {}).get("page_type") or "") == "blog"
        )
        nodes.append(
            LinkNode(
                url=url,
                page_type=page_type,  # type: ignore[arg-type]
                inlink_count=explicit_inlinks if explicit_inlinks else int(fallback_inlinks or 0),
                outlink_count=explicit_outlinks if explicit_outlinks else int(fallback_outlinks or 0),
                blog_inlink_count=blog_inlinks,
                is_commercial_target=page_type in _COMMERCIAL_TYPES,
            )
        )

    edges = sorted(
        edges_by_key.values(),
        key=lambda edge: (edge.source_url, edge.target_url, edge.anchor_text or ""),
    )
    serialised_edges = [
        {
            "source_url": edge.source_url,
            "target_url": edge.target_url,
            "anchor_text": edge.anchor_text,
        }
        for edge in edges
    ]
    serialised_nodes = [
        {
            "url": node.url,
            "page_type": node.page_type,
            "inlink_count": node.inlink_count,
            "outlink_count": node.outlink_count,
            "blog_inlink_count": node.blog_inlink_count,
            "is_commercial_target": node.is_commercial_target,
        }
        for node in nodes
    ]

    commercial_low = [
        node for node in serialised_nodes
        if node["is_commercial_target"] and node["blog_inlink_count"] == 0
    ]
    blog_low = [
        node for node in serialised_nodes
        if node["page_type"] == "blog" and int(node["inlink_count"] or 0) <= 1
    ]

    warnings = list(parse_warnings)
    if not edges:
        warnings.append("no_edges_in_input_using_inventory_counts_only")

    graph_path = paths.data / "internal_link_graph.json"
    graph = {
        "nodes": serialised_nodes,
        "edges": serialised_edges,
        "commercial_pages_low_blog_inlinks": commercial_low,
        "blog_pages_low_inlinks": blog_low,
        "warnings": warnings,
    }
    result: dict[str, Any] = {
        "planned_writes": [str(graph_path)],
        "source_path": str(source_path) if source_path else None,
        "source_format": detected_format,
        "nodes_count": len(serialised_nodes),
        "edges_count": len(serialised_edges),
        "commercial_pages_low_blog_inlinks_count": len(commercial_low),
        "blog_pages_low_inlinks_count": len(blog_low),
        "warnings": warnings,
        "graph": graph,
    }
    if write:
        write_json(graph_path, graph)
        result["written_files"] = [str(graph_path)]
    return result


def _resolve_source(source: str | Path | None, paths: ClientPaths) -> Path | None:
    if source is None:
        candidate = paths.input / "links.csv"
        return candidate if candidate.exists() else None
    return Path(source)


def _read_source(
    source_path: Path | None, source_format: str | None
) -> tuple[list[dict[str, Any]], str, list[str]]:
    if source_path is None:
        return [], "missing", []
    if not source_path.exists():
        return [], "missing", [f"links_source_not_found:{source_path}"]
    chosen = (source_format or "auto").lower()
    if chosen == "auto":
        suffix = source_path.suffix.lower()
        if suffix == ".csv":
            # Screaming Frog all_inlinks.csv has Source/Destination
            # columns the generic CSV reader recognises too, but the
            # SF reader keeps the rich raw payload (Type, Link Position,
            # Follow, etc.) for forensics.
            if detect_screaming_frog_flavour(source_path) == "links":
                chosen = "screaming-frog"
            else:
                chosen = "csv"
        elif suffix == ".json":
            chosen = "json"
        else:
            return [], "unknown", [f"unsupported_links_extension:{suffix}"]

    if chosen == "csv":
        return _read_csv(source_path), "csv", []
    if chosen == "json":
        return _read_json_list(source_path), "json", []
    if chosen == "screaming-frog":
        return _read_screaming_frog_links_source(source_path)
    return [], "unknown", [f"unsupported_links_format:{chosen}"]


def _read_screaming_frog_links_source(
    source_path: Path,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Adapt Screaming Frog link rows to ``build_link_graph``'s shape."""
    try:
        sf = read_screaming_frog_links(source_path)
    except ScreamingFrogImportError as error:
        return [], "screaming-frog", [f"screaming_frog_import_error:{error}"]
    return list(sf.get("rows") or []), "screaming-frog", list(sf.get("warnings") or [])


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = []
        for raw in reader:
            mapped = {}
            for canonical, synonyms in _CSV_COLUMNS.items():
                value = _first_present(raw, synonyms)
                mapped[canonical] = value
            rows.append(mapped)
        return rows


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        loaded = json.load(file)
    if not isinstance(loaded, list):
        return []
    return [entry for entry in loaded if isinstance(entry, dict)]


def _first_present(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
        for key in row.keys():
            if isinstance(key, str) and key.lower() == name.lower() and row[key] not in (None, ""):
                return row[key]
    return None


def _normalise_optional(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text or not text.startswith(("http://", "https://")):
        return None
    return normalise_url(text)


def _string_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None
