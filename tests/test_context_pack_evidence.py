"""Context pack integration with the search-evidence artifact."""

from __future__ import annotations

import json
from pathlib import Path

from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.context_pack import build_context_pack
from site_context_pipeline.inventory import build_inventory
from site_context_pipeline.link_graph import build_link_graph
from site_context_pipeline.providers.local_search_evidence_csv import (
    LocalSearchEvidenceCsvProvider,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_FIXTURE = REPO_ROOT / "examples" / "demo-client"


def _build_core(tmp_path: Path) -> Path:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    build_inventory(paths, write=True, source=DEMO_FIXTURE / "input" / "urls.csv")
    build_link_graph(paths, write=True, source=DEMO_FIXTURE / "input" / "links.csv")
    return tmp_path / "clients" / "demo"


def _seed_evidence(client_root: Path) -> None:
    src = DEMO_FIXTURE / "input" / "search_evidence.csv"
    items = LocalSearchEvidenceCsvProvider().run(source=str(src)).items
    artifact = {
        "schema_version": 1,
        "provider": "local-serp-csv",
        "items_count": len(items),
        "metadata": {"source_path": str(src)},
        "warnings": [],
        "items": items,
    }
    (client_root / "data" / "search_evidence.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def test_context_pack_includes_evidence_when_present(tmp_path: Path) -> None:
    client_root = _build_core(tmp_path)
    _seed_evidence(client_root)
    paths = get_client_paths("demo", workspace=tmp_path)

    result = build_context_pack(paths, write=True)
    pack = result["pack"]

    assert pack["summary"]["search_evidence_rows"] == 8
    evidence = pack["search_evidence"]
    assert evidence["rows"] == 8
    assert evidence["queries"] == 3

    queries = {entry["query"] for entry in evidence["per_query"]}
    assert queries == {
        "local delivery planning",
        "delivery cost guide",
        "business delivery pricing",
    }

    cost_guide = next(
        e for e in evidence["per_query"] if e["query"] == "delivery cost guide"
    )
    assert cost_guide["result_count"] == 3
    assert cost_guide["page_types"]["article"] == 2
    assert cost_guide["page_types"]["calculator"] == 1
    # Top results sorted by rank ascending.
    ranks = [r["rank"] for r in cost_guide["top_results"]]
    assert ranks == sorted(ranks)


def test_context_pack_md_renders_competitor_section(tmp_path: Path) -> None:
    client_root = _build_core(tmp_path)
    _seed_evidence(client_root)
    paths = get_client_paths("demo", workspace=tmp_path)

    build_context_pack(paths, write=True)
    md_text = (client_root / "output" / "agent_context_pack.md").read_text(
        encoding="utf-8"
    )
    assert "What competitors do" in md_text
    assert "delivery cost guide" in md_text


def test_context_pack_omits_evidence_when_artifact_missing(tmp_path: Path) -> None:
    _build_core(tmp_path)
    paths = get_client_paths("demo", workspace=tmp_path)

    result = build_context_pack(paths, write=True)
    pack = result["pack"]

    assert pack["summary"]["search_evidence_rows"] == 0
    assert pack["search_evidence"]["rows"] == 0
    assert pack["search_evidence"]["per_query"] == []

    md_text = (
        tmp_path / "clients" / "demo" / "output" / "agent_context_pack.md"
    ).read_text(encoding="utf-8")
    assert "What competitors do" not in md_text
