"""Context pack integration with the provider artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.context_pack import build_context_pack
from site_context_pipeline.inventory import build_inventory
from site_context_pipeline.link_graph import build_link_graph
from site_context_pipeline.providers.local_keyword_csv import LocalKeywordCsvProvider
from site_context_pipeline.providers.local_search_console_csv import (
    LocalSearchConsoleCsvProvider,
)


def _build_core(tmp_path: Path, urls_csv: Path, links_csv: Path) -> Path:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    build_inventory(paths, write=True, source=urls_csv)
    build_link_graph(paths, write=True, source=links_csv)
    return tmp_path / "clients" / "demo"


def _seed_keyword_artifact(client_root: Path, source_csv: Path) -> None:
    items = LocalKeywordCsvProvider().run(source=str(source_csv)).items
    artifact = {
        "schema_version": 1,
        "provider": "local-csv",
        "items_count": len(items),
        "metadata": {"source_path": str(source_csv)},
        "warnings": [],
        "items": items,
    }
    (client_root / "data" / "keyword_metrics.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _seed_search_artifact(client_root: Path, source_csv: Path) -> None:
    items = LocalSearchConsoleCsvProvider().run(source=str(source_csv)).items
    artifact = {
        "schema_version": 1,
        "provider": "local-gsc-csv",
        "items_count": len(items),
        "metadata": {"source_path": str(source_csv)},
        "warnings": [],
        "items": items,
    }
    (client_root / "data" / "search_performance.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def test_context_pack_warns_when_keyword_data_missing(
    tmp_path: Path, demo_urls_csv: Path, demo_links_csv: Path
) -> None:
    _build_core(tmp_path, demo_urls_csv, demo_links_csv)
    paths = get_client_paths("demo", workspace=tmp_path)
    result = build_context_pack(paths, write=False)
    assert "missing_keyword_data:run_import-keywords_or_import-search-performance" in result["warnings"]


def test_context_pack_includes_keyword_section_when_present(
    tmp_path: Path,
    demo_urls_csv: Path,
    demo_links_csv: Path,
    demo_keyword_csv: Path,
) -> None:
    client_root = _build_core(tmp_path, demo_urls_csv, demo_links_csv)
    _seed_keyword_artifact(client_root, demo_keyword_csv)
    paths = get_client_paths("demo", workspace=tmp_path)

    result = build_context_pack(paths, write=True)
    pack = result["pack"]

    assert pack["summary"]["keyword_metrics_count"] == 6
    top = pack["opportunities"]["top_keywords"]
    assert len(top) >= 5
    assert top[0]["query"] == "local delivery service"
    assert top[0]["avg_monthly_searches"] == 3600

    assert "missing_keyword_data:run_import-keywords_or_import-search-performance" not in pack["warnings"]

    md_text = (client_root / "output" / "agent_context_pack.md").read_text(encoding="utf-8")
    assert "Top keyword opportunities" in md_text


def test_context_pack_derives_performance_signals(
    tmp_path: Path,
    demo_urls_csv: Path,
    demo_links_csv: Path,
    demo_keyword_csv: Path,
    demo_search_console_csv: Path,
) -> None:
    client_root = _build_core(tmp_path, demo_urls_csv, demo_links_csv)
    _seed_keyword_artifact(client_root, demo_keyword_csv)
    _seed_search_artifact(client_root, demo_search_console_csv)
    paths = get_client_paths("demo", workspace=tmp_path)

    result = build_context_pack(paths, write=True)
    pack = result["pack"]

    summary = pack["search_performance_summary"]
    assert summary["rows"] == 6
    assert summary["total_clicks"] == 174
    assert summary["total_impressions"] == 8620

    weak_ctr = pack["opportunities"]["weak_ctr_pages"]
    weak_queries = {item["query"] for item in weak_ctr}
    # Both queries serving https://example.com/blog/delivery-cost-guide/ and
    # /services/long-haul-delivery/ have CTR <= 2% with >= 100 impressions.
    assert "delivery cost guide" in weak_queries
    assert "warehouse delivery service" in weak_queries

    unsupported = pack["opportunities"]["ranked_but_unsupported"]
    unsupported_urls = {row["url"] for row in unsupported}
    # /services/long-haul-delivery/ ranks at position 22.3 (above the
    # 20.0 floor) so it is excluded; /pricing/ has a blog inlink (from
    # /blog/delivery-cost-guide/) so it is also excluded. Both blog
    # posts rank well but receive zero inlinks → must be flagged.
    assert "https://example.com/blog/how-to-plan-delivery/" in unsupported_urls
    assert "https://example.com/blog/delivery-cost-guide/" in unsupported_urls
    assert "https://example.com/pricing/" not in unsupported_urls

    md_text = (client_root / "output" / "agent_context_pack.md").read_text(encoding="utf-8")
    assert "Pages with impressions but weak CTR" in md_text
    assert "Search performance summary" in md_text
