"""Tests for the sitemap XML importer.

The importer must:
  * read a single ``<urlset>`` sitemap and emit one row per ``<loc>``;
  * follow a ``<sitemapindex>`` to its child sitemaps when they live on the
    local filesystem (relative paths resolved against the index file);
  * tolerate sitemaps with or without the canonical namespace;
  * preserve optional metadata (``lastmod``, ``changefreq``, ``priority``)
    inside each row's ``raw`` dict;
  * raise a typed error for malformed XML / missing files / non-sitemap roots;
  * never make a network call (paths starting with ``http://`` or
    ``https://`` inside a sitemap-index must be reported, not fetched).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from site_context_pipeline.importers.sitemap_xml import (
    SitemapImportError,
    read_sitemap,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_read_simple_sitemap_returns_all_urls() -> None:
    result = read_sitemap(FIXTURES / "sitemap_simple.xml")
    urls = [row["url"] for row in result["rows"]]
    assert urls == [
        "https://example.com/",
        "https://example.com/services/",
        "https://example.com/services/local-delivery/",
        "https://example.com/blog/how-to-plan-delivery/",
        "https://example.com/about/",
    ]
    assert result["sources"] == [str(FIXTURES / "sitemap_simple.xml")]
    assert "skipped_remote_child_sitemaps" not in result["warnings"]


def test_simple_sitemap_preserves_optional_metadata() -> None:
    result = read_sitemap(FIXTURES / "sitemap_simple.xml")
    by_url = {row["url"]: row for row in result["rows"]}

    home = by_url["https://example.com/"]
    assert home["raw"]["lastmod"] == "2026-04-12"
    assert home["raw"]["changefreq"] == "weekly"
    assert home["raw"]["priority"] == "1.0"

    minimal = by_url["https://example.com/blog/how-to-plan-delivery/"]
    assert minimal["raw"]["lastmod"] == "2026-04-15"
    assert "changefreq" not in minimal["raw"]


def test_loc_is_trimmed() -> None:
    """Whitespace around <loc> should not produce a different URL."""
    result = read_sitemap(FIXTURES / "sitemap_simple.xml")
    urls = [row["url"] for row in result["rows"]]
    assert "https://example.com/about/" in urls
    # Make sure none of the URLs have leading or trailing whitespace.
    assert all(url == url.strip() for url in urls)


def test_sitemap_without_namespace_is_accepted() -> None:
    """Some CMSes emit sitemaps without the xmlns declaration."""
    result = read_sitemap(FIXTURES / "sitemap_no_namespace.xml")
    urls = [row["url"] for row in result["rows"]]
    assert urls == ["https://example.com/", "https://example.com/about/"]


def test_empty_sitemap_returns_empty_rows() -> None:
    result = read_sitemap(FIXTURES / "sitemap_empty.xml")
    assert result["rows"] == []
    assert "empty_sitemap" in result["warnings"]


def test_sitemap_index_follows_local_children() -> None:
    result = read_sitemap(FIXTURES / "sitemap_index.xml")
    urls = [row["url"] for row in result["rows"]]
    # Both child sitemaps reference https://example.com/services/, the
    # importer must dedupe and keep first-seen order.
    assert urls == [
        "https://example.com/",
        "https://example.com/services/",
        "https://example.com/blog/how-to-plan-delivery/",
        "https://example.com/blog/delivery-cost-guide/",
    ]
    # All three files should be in `sources`.
    assert len(result["sources"]) == 3


def test_malformed_sitemap_raises() -> None:
    with pytest.raises(SitemapImportError):
        read_sitemap(FIXTURES / "sitemap_malformed.xml")


def test_missing_path_raises() -> None:
    with pytest.raises(SitemapImportError):
        read_sitemap(FIXTURES / "does_not_exist.xml")


def test_unknown_root_element_raises(tmp_path: Path) -> None:
    bad = tmp_path / "atom.xml"
    bad.write_text(
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"/>',
        encoding="utf-8",
    )
    with pytest.raises(SitemapImportError):
        read_sitemap(bad)


def test_remote_child_sitemap_is_skipped_with_warning(tmp_path: Path) -> None:
    """The 0.x core stays offline. A sitemap-index pointing at a remote
    child sitemap must be reported, not fetched."""
    index = tmp_path / "sitemap_index_remote.xml"
    index.write_text(
        '<?xml version="1.0"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<sitemap><loc>https://example.com/sitemap-2026.xml</loc></sitemap>'
        '</sitemapindex>',
        encoding="utf-8",
    )
    result = read_sitemap(index)
    assert result["rows"] == []
    assert any(
        warning.startswith("skipped_remote_child_sitemap:")
        for warning in result["warnings"]
    )


def test_dedup_within_single_sitemap(tmp_path: Path) -> None:
    sitemap = tmp_path / "dup.xml"
    sitemap.write_text(
        '<?xml version="1.0"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://example.com/a/</loc></url>"
        "<url><loc>https://example.com/a/</loc></url>"
        "<url><loc>https://example.com/b/</loc></url>"
        "</urlset>",
        encoding="utf-8",
    )
    result = read_sitemap(sitemap)
    urls = [row["url"] for row in result["rows"]]
    assert urls == ["https://example.com/a/", "https://example.com/b/"]
