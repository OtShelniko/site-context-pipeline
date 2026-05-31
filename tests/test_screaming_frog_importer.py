"""Unit tests for the Screaming Frog CSV importer.

Behaviour we want:
  * read the canonical SF inventory CSV (`internal_html.csv`) and emit
    rows in the shape `build_inventory` consumes;
  * tolerate the legacy column layout (`Title` instead of `Title 1`,
    `H1` instead of `H1-1`, `From`/`To` instead of `Source`/`Destination`);
  * read the SF link export (`all_inlinks.csv`) and emit edges in the
    shape `build_link_graph` consumes;
  * preserve unconsumed columns inside each row's ``raw`` dict so no
    information is lost;
  * raise a typed error for missing files / malformed CSV / unknown
    flavour;
  * stay fully offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from site_context_pipeline.importers.screaming_frog import (
    ScreamingFrogImportError,
    detect_flavour,
    read_inventory_csv,
    read_link_csv,
)

FIXTURES = Path(__file__).parent / "fixtures" / "screaming_frog"


# ---------------------------------------------------------------------------
# Inventory CSV
# ---------------------------------------------------------------------------


def test_internal_html_canonical_columns() -> None:
    result = read_inventory_csv(FIXTURES / "internal_html.csv")
    by_url = {row["url"]: row for row in result["rows"]}

    home = by_url["https://example.com/"]
    assert home["title"] == "Example Co"
    assert home["h1"] == "Welcome"
    assert home["status_code"] == "200"
    assert home["word_count"] == "180"
    assert home["inlinks_count"] == "8"
    assert home["outlinks_count"] == "12"
    # Indexability is preserved in raw because the inventory builder
    # does not consume it directly today.
    assert home["raw"].get("indexability") == "Indexable"


def test_internal_legacy_column_aliases() -> None:
    """Older SF exports use 'Title'/'H1' instead of 'Title 1'/'H1-1'."""
    result = read_inventory_csv(FIXTURES / "internal_legacy.csv")
    by_url = {row["url"]: row for row in result["rows"]}

    home = by_url["https://example.com/"]
    assert home["title"] == "Example Co"
    assert home["h1"] == "Welcome"


def test_internal_minimal_csv_only_required_columns() -> None:
    result = read_inventory_csv(FIXTURES / "internal_minimal.csv")
    rows = result["rows"]
    assert len(rows) == 2
    home = rows[0]
    assert home["url"] == "https://example.com/"
    # Missing optional columns surface as None, not empty strings.
    assert home["h1"] is None
    assert home["word_count"] is None


def test_inventory_skips_rows_without_url(tmp_path: Path) -> None:
    csv_path = tmp_path / "internal.csv"
    csv_path.write_text(
        "Address,Status Code,Title 1\n"
        ",200,Empty\n"
        "https://example.com/,200,Home\n",
        encoding="utf-8",
    )
    result = read_inventory_csv(csv_path)
    assert len(result["rows"]) == 1
    assert any(w.startswith("skipped_rows_without_url:") for w in result["warnings"])


def test_inventory_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(ScreamingFrogImportError):
        read_inventory_csv(tmp_path / "no-such.csv")


def test_inventory_without_address_column_raises(tmp_path: Path) -> None:
    csv_path = tmp_path / "internal.csv"
    csv_path.write_text("Foo,Bar\nx,y\n", encoding="utf-8")
    with pytest.raises(ScreamingFrogImportError):
        read_inventory_csv(csv_path)


# ---------------------------------------------------------------------------
# Link CSV
# ---------------------------------------------------------------------------


def test_all_inlinks_canonical_columns() -> None:
    result = read_link_csv(FIXTURES / "all_inlinks.csv")
    edges = result["rows"]
    assert len(edges) == 5

    first = edges[0]
    assert first["source_url"] == "https://example.com/"
    assert first["target_url"] == "https://example.com/services/"
    assert first["anchor_text"] == "Services"

    blog_edge = next(
        e for e in edges
        if e["source_url"] == "https://example.com/blog/how-to-plan-delivery/"
    )
    assert blog_edge["target_url"] == "https://example.com/services/local-delivery/"


def test_link_legacy_from_to_columns() -> None:
    """Older SF exports use 'From'/'To' instead of 'Source'/'Destination'."""
    result = read_link_csv(FIXTURES / "inlinks_legacy.csv")
    edges = result["rows"]
    assert len(edges) == 2
    assert edges[0]["source_url"] == "https://example.com/"
    assert edges[0]["target_url"] == "https://example.com/services/"
    assert edges[0]["anchor_text"] == "Services"


def test_link_csv_skips_rows_without_source_or_target(tmp_path: Path) -> None:
    csv_path = tmp_path / "links.csv"
    csv_path.write_text(
        "Source,Destination,Anchor Text\n"
        ",https://example.com/x/,bad-source\n"
        "https://example.com/x/,,bad-target\n"
        "https://example.com/x/,https://example.com/y/,ok\n",
        encoding="utf-8",
    )
    result = read_link_csv(csv_path)
    assert len(result["rows"]) == 1
    assert any(w.startswith("skipped_rows_without_endpoints:") for w in result["warnings"])


def test_link_csv_without_recognised_columns_raises(tmp_path: Path) -> None:
    csv_path = tmp_path / "links.csv"
    csv_path.write_text("Foo,Bar\nx,y\n", encoding="utf-8")
    with pytest.raises(ScreamingFrogImportError):
        read_link_csv(csv_path)


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------


def test_detect_inventory_flavour() -> None:
    assert detect_flavour(FIXTURES / "internal_html.csv") == "inventory"
    assert detect_flavour(FIXTURES / "internal_legacy.csv") == "inventory"
    assert detect_flavour(FIXTURES / "internal_minimal.csv") == "inventory"


def test_detect_link_flavour() -> None:
    assert detect_flavour(FIXTURES / "all_inlinks.csv") == "links"
    assert detect_flavour(FIXTURES / "inlinks_legacy.csv") == "links"


def test_detect_unknown_flavour(tmp_path: Path) -> None:
    csv_path = tmp_path / "noise.csv"
    csv_path.write_text("Foo,Bar\nx,y\n", encoding="utf-8")
    assert detect_flavour(csv_path) == "unknown"


def test_detect_missing_file(tmp_path: Path) -> None:
    assert detect_flavour(tmp_path / "no-such.csv") == "unknown"
