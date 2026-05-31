"""Tests for the context pack and the link graph."""

from __future__ import annotations

import json
from pathlib import Path

from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.context_pack import build_context_pack
from site_context_pipeline.inventory import build_inventory
from site_context_pipeline.link_graph import build_link_graph


def _build_demo_state(tmp_path: Path, urls_csv: Path, links_csv: Path) -> Path:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    build_inventory(paths, write=True, source=urls_csv)
    build_link_graph(paths, write=True, source=links_csv)
    return tmp_path / "clients" / "demo"


def test_link_graph_counts_blog_inlinks(
    tmp_path: Path, demo_urls_csv: Path, demo_links_csv: Path
) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    build_inventory(paths, write=True, source=demo_urls_csv)
    result = build_link_graph(paths, write=True, source=demo_links_csv)

    nodes = {node["url"]: node for node in result["graph"]["nodes"]}
    local = nodes["https://example.com/services/local-delivery/"]
    assert local["blog_inlink_count"] == 1
    assert local["is_commercial_target"] is True


def test_link_graph_without_edges_warns(tmp_path: Path, demo_urls_csv: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    build_inventory(paths, write=True, source=demo_urls_csv)
    result = build_link_graph(paths, write=True, source=None)
    assert "no_edges_in_input_using_inventory_counts_only" in result["warnings"]


def test_context_pack_aggregates_inventory_and_graph(
    tmp_path: Path, demo_urls_csv: Path, demo_links_csv: Path
) -> None:
    client_root = _build_demo_state(tmp_path, demo_urls_csv, demo_links_csv)
    paths = get_client_paths("demo", workspace=tmp_path)

    result = build_context_pack(paths, write=True)
    pack = result["pack"]

    assert pack["client"] == "demo"
    assert pack["summary"]["page_count"] >= 5
    assert "blog" in pack["summary"]["page_type_counts"]
    assert pack["summary"]["edge_count"] >= 1

    json_path = client_root / "output" / "agent_context_pack.json"
    md_path = client_root / "output" / "agent_context_pack.md"
    opp_path = client_root / "output" / "content_opportunities.md"
    assert json_path.exists() and md_path.exists() and opp_path.exists()

    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == 1
    assert "summary" in on_disk and "opportunities" in on_disk

    md_text = md_path.read_text(encoding="utf-8")
    assert "Agent context pack" in md_text
    assert "## Summary" in md_text


def test_context_pack_preserves_project_notes(
    tmp_path: Path, demo_urls_csv: Path, demo_links_csv: Path
) -> None:
    _build_demo_state(tmp_path, demo_urls_csv, demo_links_csv)
    paths = get_client_paths("demo", workspace=tmp_path)
    notes = "Test note: blog focuses on shipping logistics for SMBs.\n"
    (paths.input / "project.md").write_text(notes, encoding="utf-8")

    result = build_context_pack(paths, write=True)
    assert notes.strip() in result["pack"]["project_notes"]


def test_context_pack_dry_run_writes_nothing(
    tmp_path: Path, demo_urls_csv: Path, demo_links_csv: Path
) -> None:
    _build_demo_state(tmp_path, demo_urls_csv, demo_links_csv)
    paths = get_client_paths("demo", workspace=tmp_path)
    result = build_context_pack(paths, write=False)
    assert "written_files" not in result
    assert not (paths.output / "agent_context_pack.json").exists()
