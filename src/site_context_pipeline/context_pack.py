"""Aggregate inventory + link graph + project notes (and any keyword /
search-performance imports that exist) into one context pack.

The context pack has two outputs that share the same content:

* ``output/agent_context_pack.json`` — machine-readable, stable schema.
* ``output/agent_context_pack.md`` — human-readable summary for review.

Plus a sibling artifact:

* ``output/content_opportunities.md`` — the deterministic opportunity list.

The pack is *only* a re-shaping of facts already on disk. It does not call
any model and does not invent fields.

Optional sections (only included when the source files exist):

* **Top keyword opportunities** — read from
  ``data/keyword_metrics.json`` (produced by ``import-keywords``).
* **Existing search performance signals** — read from
  ``data/search_performance.json`` (produced by ``import-search-performance``).
* **Pages with impressions but weak CTR** — derived from search-performance.
* **Pages with rankings but weak internal support** — derived from
  search-performance × link graph.
* A clear ``missing_keyword_data`` warning when neither artifact exists.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import markdown as md
from .clients import ClientPaths, read_json, read_text, write_json
from .schemas import SCHEMA_VERSION


def build_context_pack(paths: ClientPaths, *, write: bool) -> dict[str, Any]:
    inventory = _read_list(paths.data / "content_inventory.json")
    link_graph = _read_dict(paths.data / "internal_link_graph.json")
    project_notes = read_text(paths.input / "project.md")

    keyword_metrics_payload = _read_provider_artifact(
        paths.data / "keyword_metrics.json"
    )
    search_performance_payload = _read_provider_artifact(
        paths.data / "search_performance.json"
    )
    search_evidence_payload = _read_provider_artifact(
        paths.data / "search_evidence.json"
    )
    keyword_items = list(keyword_metrics_payload.get("items") or [])
    performance_items = list(search_performance_payload.get("items") or [])
    evidence_items = list(search_evidence_payload.get("items") or [])

    page_type_counts = _count_by_field(inventory, "page_type")
    classification_reasons = _count_by_field(inventory, "classification_reason")

    home_pages = [item for item in inventory if item.get("page_type") == "home"]
    landings = [item for item in inventory if item.get("page_type") == "landing"]
    services = [item for item in inventory if item.get("page_type") == "service"]
    categories = [item for item in inventory if item.get("page_type") == "category"]
    blog_posts = [item for item in inventory if item.get("page_type") == "blog"]

    commercial_low = list(link_graph.get("commercial_pages_low_blog_inlinks") or [])
    blog_low = list(link_graph.get("blog_pages_low_inlinks") or [])

    keyword_opportunities = _top_keyword_opportunities(keyword_items)
    performance_summary = _performance_summary(performance_items)
    weak_ctr_pages = _weak_ctr_pages(performance_items)
    ranked_but_unsupported = _ranked_but_unsupported(
        performance_items=performance_items,
        link_graph=link_graph,
    )
    evidence_summary = _search_evidence_summary(evidence_items)

    pack = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "client": paths.client_code,
        "summary": {
            "page_count": len(inventory),
            "page_type_counts": page_type_counts,
            "edge_count": len(link_graph.get("edges") or []),
            "node_count": len(link_graph.get("nodes") or []),
            "keyword_metrics_count": len(keyword_items),
            "search_performance_rows": len(performance_items),
            "search_evidence_rows": len(evidence_items),
        },
        "classification": {
            "reasons": classification_reasons,
        },
        "pages": {
            "home": _trim_pages(home_pages),
            "landing": _trim_pages(landings),
            "service": _trim_pages(services),
            "category": _trim_pages(categories),
            "blog": _trim_pages(blog_posts),
        },
        "opportunities": {
            "commercial_pages_low_blog_inlinks": commercial_low,
            "blog_pages_low_inlinks": blog_low,
            "top_keywords": keyword_opportunities,
            "weak_ctr_pages": weak_ctr_pages,
            "ranked_but_unsupported": ranked_but_unsupported,
        },
        "search_performance_summary": performance_summary,
        "search_evidence": evidence_summary,
        "providers": {
            "keyword_metrics": _provider_summary(keyword_metrics_payload),
            "search_performance": _provider_summary(search_performance_payload),
            "search_evidence": _provider_summary(search_evidence_payload),
        },
        "project_notes": project_notes,
        "sources": {
            "content_inventory": str(paths.data / "content_inventory.json"),
            "internal_link_graph": str(paths.data / "internal_link_graph.json"),
            "project_md": str(paths.input / "project.md"),
            "keyword_metrics": str(paths.data / "keyword_metrics.json"),
            "search_performance": str(paths.data / "search_performance.json"),
            "search_evidence": str(paths.data / "search_evidence.json"),
        },
        "warnings": _collect_warnings(
            inventory=inventory,
            link_graph=link_graph,
            keyword_items=keyword_items,
            performance_items=performance_items,
        ),
    }

    pack_md = _render_pack_markdown(pack)
    opportunities_md = _render_opportunities_markdown(pack)

    pack_json_path = paths.output / "agent_context_pack.json"
    pack_md_path = paths.output / "agent_context_pack.md"
    opportunities_path = paths.output / "content_opportunities.md"
    planned_writes = [str(pack_json_path), str(pack_md_path), str(opportunities_path)]

    result: dict[str, Any] = {
        "planned_writes": planned_writes,
        "warnings": pack["warnings"],
        "summary": pack["summary"],
        "pack": pack,
    }
    if write:
        write_json(pack_json_path, pack)
        pack_md_path.parent.mkdir(parents=True, exist_ok=True)
        pack_md_path.write_text(pack_md, encoding="utf-8")
        opportunities_path.write_text(opportunities_md, encoding="utf-8")
        result["written_files"] = planned_writes
    return result


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def _read_list(path: Path) -> list[dict[str, Any]]:
    raw = read_json(path, [])
    return raw if isinstance(raw, list) else []


def _read_dict(path: Path) -> dict[str, Any]:
    raw = read_json(path, {})
    return raw if isinstance(raw, dict) else {}


def _read_provider_artifact(path: Path) -> dict[str, Any]:
    """Read an ``import-*`` artifact (or return an empty stub)."""
    raw = read_json(path, None)
    if isinstance(raw, dict):
        return raw
    return {"items": [], "metadata": {}, "warnings": []}


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


def _count_by_field(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(field) or "")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _trim_pages(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the public fields a downstream consumer needs."""
    trimmed: list[dict[str, Any]] = []
    for item in items:
        trimmed.append(
            {
                "url": item.get("url"),
                "title": item.get("title"),
                "h1": item.get("h1"),
                "status_code": item.get("status_code"),
                "word_count": item.get("word_count"),
                "classification_reason": item.get("classification_reason"),
            }
        )
    trimmed.sort(key=lambda it: str(it.get("url") or ""))
    return trimmed


def _provider_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": payload.get("provider"),
        "items_count": len(payload.get("items") or []),
        "metadata": payload.get("metadata") or {},
        "warnings": list(payload.get("warnings") or []),
    }


def _top_keyword_opportunities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank keyword rows by demand. Used to surface "what's worth covering"."""
    if not items:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()
        if not query:
            continue
        volume = _coerce_int(item.get("avg_monthly_searches"))
        impressions = _coerce_int(item.get("impressions"))
        score = volume or 0
        if not score and impressions:
            # When demand-side volume is missing, fall back to
            # impressions so a Search-Console-only client still gets a
            # useful ordering.
            score = int(impressions)
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].get("query", "")))
    out: list[dict[str, Any]] = []
    for score, item in scored[:25]:
        out.append(
            {
                "query": item.get("query"),
                "avg_monthly_searches": item.get("avg_monthly_searches"),
                "impressions": item.get("impressions"),
                "clicks": item.get("clicks"),
                "ctr": item.get("ctr"),
                "position": item.get("position"),
                "competition": item.get("competition"),
                "geo": item.get("geo"),
                "language": item.get("language"),
                "source": item.get("source"),
                "rank_score": score,
            }
        )
    return out


def _performance_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    """High-level totals for the search-performance import."""
    if not items:
        return {
            "rows": 0,
            "total_clicks": 0,
            "total_impressions": 0,
            "average_ctr": None,
            "average_position": None,
        }
    total_clicks = 0
    total_impressions = 0
    weighted_position = 0.0
    weight = 0
    ctr_sum = 0.0
    ctr_count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        clicks = _coerce_int(item.get("clicks")) or 0
        impressions = _coerce_int(item.get("impressions")) or 0
        position = _coerce_float(item.get("position"))
        ctr = _coerce_float(item.get("ctr"))
        total_clicks += clicks
        total_impressions += impressions
        if position is not None and impressions > 0:
            weighted_position += position * impressions
            weight += impressions
        if ctr is not None:
            ctr_sum += ctr
            ctr_count += 1
    avg_position = round(weighted_position / weight, 2) if weight else None
    avg_ctr = round(ctr_sum / ctr_count, 4) if ctr_count else None
    return {
        "rows": len(items),
        "total_clicks": total_clicks,
        "total_impressions": total_impressions,
        "average_ctr": avg_ctr,
        "average_position": avg_position,
    }


def _search_evidence_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Group evidence rows by query and surface a summary the pack
    consumer can read at a glance.

    Returns a dict with three keys:

    * ``rows`` — total number of evidence rows across all queries.
    * ``queries`` — number of distinct queries.
    * ``per_query`` — list of ``{"query", "result_count", "page_types",
      "top_results"}``, one entry per distinct query, sorted by query
      string for stable output. Each entry's ``top_results`` is the
      top-5 results by ``rank`` (ascending).
    """
    if not items:
        return {"rows": 0, "queries": 0, "per_query": []}

    by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()
        if not query:
            continue
        by_query[query].append(item)

    per_query: list[dict[str, Any]] = []
    for query in sorted(by_query):
        rows = by_query[query]
        sorted_rows = sorted(
            rows,
            key=lambda r: (r.get("rank") is None, r.get("rank") or 999),
        )
        page_types: dict[str, int] = {}
        for row in rows:
            page_type = str(row.get("page_type") or "").strip() or "unknown"
            page_types[page_type] = page_types.get(page_type, 0) + 1
        per_query.append(
            {
                "query": query,
                "result_count": len(rows),
                "page_types": dict(sorted(page_types.items())),
                "top_results": [
                    {
                        "rank": row.get("rank"),
                        "title": row.get("title"),
                        "url": row.get("url"),
                        "page_type": row.get("page_type"),
                        "snippet": row.get("snippet"),
                        "source": row.get("source"),
                    }
                    for row in sorted_rows[:5]
                ],
            }
        )

    return {
        "rows": len(items),
        "queries": len(by_query),
        "per_query": per_query,
    }


def _weak_ctr_pages(
    items: list[dict[str, Any]],
    *,
    impressions_floor: int = 100,
    ctr_ceiling: float = 0.02,
) -> list[dict[str, Any]]:
    """Rows with real impressions but weaker than ``ctr_ceiling``.

    The thresholds are intentionally conservative; the goal is to surface
    candidates for human review, not to score performance.
    """
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        impressions = _coerce_int(item.get("impressions")) or 0
        ctr = _coerce_float(item.get("ctr"))
        if impressions < impressions_floor:
            continue
        if ctr is None or ctr > ctr_ceiling:
            continue
        out.append(
            {
                "query": item.get("query"),
                "url": item.get("source_url"),
                "impressions": impressions,
                "clicks": _coerce_int(item.get("clicks")) or 0,
                "ctr": ctr,
                "position": _coerce_float(item.get("position")),
            }
        )
    out.sort(key=lambda row: -int(row.get("impressions") or 0))
    return out[:25]


def _ranked_but_unsupported(
    *,
    performance_items: list[dict[str, Any]],
    link_graph: dict[str, Any],
    position_floor: float = 20.0,
) -> list[dict[str, Any]]:
    """Pages that already rank somewhere (position ≤ floor) but receive
    little internal-link support according to the link graph."""
    if not performance_items:
        return []
    nodes = link_graph.get("nodes") or []
    inlink_by_url: dict[str, int] = {}
    blog_inlink_by_url: dict[str, int] = {}
    for node in nodes:
        if not isinstance(node, dict) or not node.get("url"):
            continue
        url = str(node["url"])
        inlink_by_url[url] = int(node.get("inlink_count") or 0)
        blog_inlink_by_url[url] = int(node.get("blog_inlink_count") or 0)

    by_url: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "url": "",
            "best_position": None,
            "best_query": None,
            "impressions": 0,
            "clicks": 0,
        }
    )
    for item in performance_items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("source_url") or "").strip()
        if not url:
            continue
        position = _coerce_float(item.get("position"))
        if position is None or position > position_floor:
            continue
        bucket = by_url[url]
        bucket["url"] = url
        impressions = _coerce_int(item.get("impressions")) or 0
        clicks = _coerce_int(item.get("clicks")) or 0
        bucket["impressions"] = int(bucket["impressions"] or 0) + impressions
        bucket["clicks"] = int(bucket["clicks"] or 0) + clicks
        if bucket["best_position"] is None or position < bucket["best_position"]:
            bucket["best_position"] = position
            bucket["best_query"] = item.get("query")

    out: list[dict[str, Any]] = []
    for url, bucket in by_url.items():
        if not bucket.get("url"):
            continue
        inlinks = inlink_by_url.get(url)
        blog_inlinks = blog_inlink_by_url.get(url)
        # "Weak internal support": no inlinks at all, or no blog inlinks.
        if inlinks is None:
            support_signal = "url_not_in_link_graph"
        elif inlinks == 0:
            support_signal = "zero_inlinks"
        elif (blog_inlinks or 0) == 0:
            support_signal = "zero_blog_inlinks"
        else:
            continue
        out.append(
            {
                "url": url,
                "best_position": bucket["best_position"],
                "best_query": bucket["best_query"],
                "impressions": bucket["impressions"],
                "clicks": bucket["clicks"],
                "inlinks": inlinks,
                "blog_inlinks": blog_inlinks,
                "support_signal": support_signal,
            }
        )
    out.sort(
        key=lambda row: (
            float(row.get("best_position") or position_floor),
            -int(row.get("impressions") or 0),
        )
    )
    return out[:25]


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _collect_warnings(
    *,
    inventory: list[dict[str, Any]],
    link_graph: dict[str, Any],
    keyword_items: list[dict[str, Any]],
    performance_items: list[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    if not inventory:
        warnings.append("inventory_missing_or_empty")
    if not link_graph:
        warnings.append("link_graph_missing")
    elif not link_graph.get("edges"):
        warnings.append("link_graph_has_no_edges")
    if not keyword_items and not performance_items:
        warnings.append(
            "missing_keyword_data:run_import-keywords_or_import-search-performance"
        )
    return warnings


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Markdown renderers
# ---------------------------------------------------------------------------


def _render_pack_markdown(pack: dict[str, Any]) -> str:
    summary = pack["summary"]
    parts: list[str] = [
        md.render_heading(1, f"Agent context pack — {pack['client']}"),
        md.render_paragraph(f"Generated at: `{pack['generated_at']}`"),
        md.render_paragraph(
            "This file is a structured digest of the site. It is the single "
            "document an LLM (or a human reviewer) should read before "
            "drafting topic ideas, briefs, or articles. All facts here are "
            "sourced from local artifacts; nothing is inferred from the "
            "open web."
        ),
        md.render_heading(2, "Summary"),
        md.render_definition_list(
            [
                ("page_count", summary.get("page_count")),
                ("edge_count", summary.get("edge_count")),
                ("node_count", summary.get("node_count")),
                ("keyword_metrics_count", summary.get("keyword_metrics_count")),
                ("search_performance_rows", summary.get("search_performance_rows")),
            ]
        ),
        md.render_heading(3, "Page-type breakdown"),
        md.render_definition_list(summary.get("page_type_counts", {}).items()),
        md.render_heading(2, "Classification reasons"),
        md.render_definition_list(pack["classification"]["reasons"].items()),
        md.render_heading(2, "Pages by type"),
    ]
    for label, key in (
        ("Home", "home"),
        ("Landing", "landing"),
        ("Service", "service"),
        ("Category", "category"),
        ("Blog", "blog"),
    ):
        parts.append(md.render_heading(3, label))
        parts.append(md.render_bullet_list(_page_lines(pack["pages"].get(key) or [])))

    parts.append(md.render_heading(2, "Opportunities"))
    parts.append(md.render_heading(3, "Commercial pages with no inlinks from blog posts"))
    parts.append(
        md.render_bullet_list(_node_lines(pack["opportunities"]["commercial_pages_low_blog_inlinks"]))
    )
    parts.append(md.render_heading(3, "Blog posts with at most one inlink"))
    parts.append(md.render_bullet_list(_node_lines(pack["opportunities"]["blog_pages_low_inlinks"])))

    keyword_lines = _keyword_lines(pack["opportunities"].get("top_keywords") or [])
    if keyword_lines:
        parts.append(md.render_heading(3, "Top keyword opportunities"))
        parts.append(md.render_bullet_list(keyword_lines))

    weak_ctr = _weak_ctr_lines(pack["opportunities"].get("weak_ctr_pages") or [])
    if weak_ctr:
        parts.append(md.render_heading(3, "Pages with impressions but weak CTR"))
        parts.append(md.render_bullet_list(weak_ctr))

    unsupported = _unsupported_lines(pack["opportunities"].get("ranked_but_unsupported") or [])
    if unsupported:
        parts.append(md.render_heading(3, "Pages with rankings but weak internal support"))
        parts.append(md.render_bullet_list(unsupported))

    perf = pack.get("search_performance_summary") or {}
    if perf and perf.get("rows"):
        parts.append(md.render_heading(2, "Search performance summary"))
        parts.append(
            md.render_definition_list(
                [
                    ("rows", perf.get("rows")),
                    ("total_clicks", perf.get("total_clicks")),
                    ("total_impressions", perf.get("total_impressions")),
                    ("average_ctr", perf.get("average_ctr")),
                    ("average_position", perf.get("average_position")),
                ]
            )
        )

    evidence = pack.get("search_evidence") or {}
    if evidence and evidence.get("rows"):
        parts.append(md.render_heading(2, "What competitors do"))
        parts.append(
            md.render_paragraph(
                "Hand-curated SERP evidence imported through "
                "`import-search-evidence`. The toolkit does not scrape "
                "live SERPs; what you see here is what was put into the "
                "CSV by the operator."
            )
        )
        for entry in evidence.get("per_query") or []:
            parts.append(md.render_heading(3, str(entry.get("query") or "")))
            page_types = entry.get("page_types") or {}
            page_types_str = ", ".join(
                f"{name}={count}" for name, count in page_types.items()
            ) or "_unknown_"
            parts.append(
                md.render_definition_list(
                    [
                        ("result_count", entry.get("result_count")),
                        ("page_types", page_types_str),
                    ]
                )
            )
            top_lines = _evidence_lines(entry.get("top_results") or [])
            if top_lines:
                parts.append(md.render_bullet_list(top_lines))

    parts.append(md.render_heading(2, "Project notes"))
    notes = pack.get("project_notes") or ""
    parts.append(notes.rstrip() + "\n" if notes.strip() else "_no project notes provided_\n")

    parts.append(md.render_heading(2, "Sources"))
    parts.append(md.render_definition_list(pack["sources"].items()))

    if pack["warnings"]:
        parts.append(md.render_heading(2, "Warnings"))
        parts.append(md.render_bullet_list(pack["warnings"]))
    return "\n".join(parts)


def _render_opportunities_markdown(pack: dict[str, Any]) -> str:
    parts: list[str] = [
        md.render_heading(1, f"Content opportunities — {pack['client']}"),
        md.render_paragraph(
            "Heuristic opportunity list derived from the link graph and "
            "any imported keyword/search-performance data. Each row points "
            "at a deterministic gap; review by hand before acting on any "
            "of them."
        ),
        md.render_heading(2, "Commercial pages with no inlinks from blog posts"),
        md.render_bullet_list(
            _node_lines(pack["opportunities"]["commercial_pages_low_blog_inlinks"])
        ),
        md.render_heading(2, "Blog posts with at most one inlink"),
        md.render_bullet_list(_node_lines(pack["opportunities"]["blog_pages_low_inlinks"])),
    ]

    keyword_lines = _keyword_lines(pack["opportunities"].get("top_keywords") or [])
    if keyword_lines:
        parts.append(md.render_heading(2, "Top keyword opportunities"))
        parts.append(md.render_bullet_list(keyword_lines))

    weak_ctr = _weak_ctr_lines(pack["opportunities"].get("weak_ctr_pages") or [])
    if weak_ctr:
        parts.append(md.render_heading(2, "Pages with impressions but weak CTR"))
        parts.append(md.render_bullet_list(weak_ctr))

    unsupported = _unsupported_lines(pack["opportunities"].get("ranked_but_unsupported") or [])
    if unsupported:
        parts.append(md.render_heading(2, "Pages with rankings but weak internal support"))
        parts.append(md.render_bullet_list(unsupported))

    if "missing_keyword_data:run_import-keywords_or_import-search-performance" in (
        pack.get("warnings") or []
    ):
        parts.append(md.render_heading(2, "Missing keyword data"))
        parts.append(
            md.render_paragraph(
                "No `data/keyword_metrics.json` or `data/search_performance.json` "
                "found. Run `import-keywords` or `import-search-performance` to "
                "fold demand and performance data into this report."
            )
        )

    return "\n".join(parts)


def _page_lines(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in items:
        url = item.get("url") or ""
        title = item.get("title") or item.get("h1") or url
        reason = item.get("classification_reason") or ""
        lines.append(f"{md.render_link(title, url)} — _{reason}_")
    return lines


def _evidence_lines(rows: list[dict[str, Any]]) -> list[str]:
    """Render top-N SERP rows as a bullet list for the context pack.

    Each line is short on purpose — the JSON sibling carries the full
    payload; this is just for human review."""
    out: list[str] = []
    for row in rows:
        rank = row.get("rank")
        title = row.get("title") or row.get("url") or ""
        url = row.get("url") or ""
        page_type = row.get("page_type")
        rank_text = f"#{rank}" if isinstance(rank, int) else "#?"
        link = md.render_link(title, url) if url else title
        suffix = f" — `{page_type}`" if page_type else ""
        out.append(f"{rank_text} {link}{suffix}")
    return out


def _node_lines(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for node in items:
        url = node.get("url") or ""
        page_type = node.get("page_type") or "other"
        inlinks = node.get("inlink_count") or 0
        blog_in = node.get("blog_inlink_count") or 0
        lines.append(
            f"{md.render_link(url, url)} — `{page_type}`, "
            f"inlinks={inlinks}, blog_inlinks={blog_in}"
        )
    return lines


def _keyword_lines(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in items:
        query = item.get("query") or ""
        if not query:
            continue
        volume = item.get("avg_monthly_searches")
        impressions = item.get("impressions")
        clicks = item.get("clicks")
        position = item.get("position")
        bits: list[str] = [f"**{query}**"]
        if volume not in (None, ""):
            bits.append(f"volume={volume}")
        if impressions not in (None, ""):
            bits.append(f"impressions={impressions}")
        if clicks not in (None, ""):
            bits.append(f"clicks={clicks}")
        if position not in (None, ""):
            bits.append(f"position={position}")
        bits.append(f"_source: {item.get('source')}_")
        lines.append(" — ".join(bits))
    return lines


def _weak_ctr_lines(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in items:
        query = item.get("query") or ""
        url = item.get("url") or ""
        ctr = item.get("ctr")
        impressions = item.get("impressions")
        position = item.get("position")
        ctr_text = f"{ctr * 100:.2f}%" if isinstance(ctr, (int, float)) else "—"
        suffix = (
            f"impressions={impressions}, ctr={ctr_text}"
            f"{'' if position is None else f', position={position}'}"
        )
        if url:
            lines.append(f"**{query}** → {md.render_link(url, url)} — {suffix}")
        else:
            lines.append(f"**{query}** — {suffix}")
    return lines


def _unsupported_lines(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in items:
        url = item.get("url") or ""
        position = item.get("best_position")
        query = item.get("best_query") or ""
        impressions = item.get("impressions") or 0
        signal = item.get("support_signal") or ""
        lines.append(
            f"{md.render_link(url, url)} — best position {position} for "
            f"**{query}**, impressions={impressions}, _{signal}_"
        )
    return lines
