"""Unit tests for the URL classifier and the inventory builder."""

from __future__ import annotations

from pathlib import Path

from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.inventory import (
    build_inventory,
    classify_url,
    normalise_url,
)


def test_normalise_url_lowercases_host_and_strips_fragment() -> None:
    assert normalise_url("HTTPS://Example.COM/Path/?x=1#frag") == "https://example.com/Path/?x=1"


def test_normalise_url_collapses_double_slashes() -> None:
    assert normalise_url("https://example.com//foo//bar/") == "https://example.com/foo/bar/"


def test_classify_home_path() -> None:
    page_type, reason = classify_url(
        "https://example.com/", commercial_urls=set(), rules=[("blog", "*/blog/*")]
    )
    assert page_type == "home"
    assert reason == "matched_home_path"


def test_classify_blog_pattern() -> None:
    page_type, reason = classify_url(
        "https://example.com/blog/post-1/",
        commercial_urls=set(),
        rules=[("blog", "*/blog/*")],
    )
    assert page_type == "blog"
    assert reason == "matched_pattern:*/blog/*"


def test_explicit_commercial_url_wins_over_pattern() -> None:
    url = "https://example.com/services/local-delivery/"
    page_type, reason = classify_url(
        url, commercial_urls={url}, rules=[("service", "*/services/*")]
    )
    assert page_type == "landing"
    assert reason == "matched_commercial_url_list"


def test_unknown_falls_back_to_other() -> None:
    page_type, reason = classify_url(
        "https://example.com/random/", commercial_urls=set(), rules=[("blog", "*/blog/*")]
    )
    assert page_type == "other"
    assert reason == "fallback_other"


def test_build_inventory_classifies_demo_urls(tmp_path: Path, demo_urls_csv: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)

    result = build_inventory(paths, write=True, source=demo_urls_csv)
    assert (tmp_path / "clients" / "demo" / "data" / "content_inventory.json").exists()

    by_url = {item["url"]: item for item in result["items"]}
    assert by_url["https://example.com/"]["page_type"] == "home"
    assert by_url["https://example.com/blog/how-to-plan-delivery/"]["page_type"] == "blog"
    assert by_url["https://example.com/services/local-delivery/"]["page_type"] == "service"
    assert by_url["https://example.com/about/"]["page_type"] == "other"


def test_build_inventory_with_commercial_override(
    tmp_path: Path, demo_urls_csv: Path
) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    (paths.config / "commercial_urls.json").write_text(
        '["https://example.com/services/local-delivery/"]\n', encoding="utf-8"
    )
    result = build_inventory(paths, write=True, source=demo_urls_csv)
    by_url = {item["url"]: item for item in result["items"]}
    landing = by_url["https://example.com/services/local-delivery/"]
    assert landing["page_type"] == "landing"
    assert landing["classification_reason"] == "matched_commercial_url_list"


def test_build_inventory_dry_run_does_not_write(tmp_path: Path, demo_urls_csv: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    build_inventory(paths, write=False, source=demo_urls_csv)
    assert not (paths.data / "content_inventory.json").exists()


def test_build_inventory_skips_duplicates(tmp_path: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    csv_path = tmp_path / "dup.csv"
    csv_path.write_text(
        "url,title\n"
        "https://example.com/a/,Page A\n"
        "https://example.com/a/,Page A duplicate\n",
        encoding="utf-8",
    )
    result = build_inventory(paths, write=False, source=csv_path)
    assert result["items_count"] == 1
