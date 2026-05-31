"""Integration tests: Screaming Frog CSVs flowing through the builders.

These cover both:

* ``build_inventory(... source_format='screaming-frog')``  — reading a
  ``internal_html.csv`` style export.
* ``build_link_graph(... source_format='screaming-frog')`` — reading an
  ``all_inlinks.csv`` style export.
* The auto-detect path: a `.csv` whose headers look like a Screaming
  Frog export should route to the SF reader without ``--format`` set.
* The CLI flags accept ``screaming-frog`` and reject typos.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from site_context_pipeline.cli import main
from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.inventory import build_inventory
from site_context_pipeline.link_graph import build_link_graph

FIXTURES = Path(__file__).parent / "fixtures" / "screaming_frog"


def _run(argv: list[str]) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    raw = buffer.getvalue().strip()
    payload = json.loads(raw) if raw else {}
    return code, payload


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def test_build_inventory_from_screaming_frog_explicit_format(tmp_path: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    result = build_inventory(
        paths,
        write=True,
        source=FIXTURES / "internal_html.csv",
        source_format="screaming-frog",
    )
    assert result["source_format"] == "screaming-frog"
    by_url = {item["url"]: item for item in result["items"]}

    home = by_url["https://example.com/"]
    assert home["page_type"] == "home"
    assert home["title"] == "Example Co"
    assert home["h1"] == "Welcome"
    assert home["status_code"] == 200
    assert home["word_count"] == 180
    assert home["inlinks_count"] == 8
    assert home["outlinks_count"] == 12
    assert home["source"] == "screaming-frog"

    blog = by_url["https://example.com/blog/how-to-plan-delivery/"]
    assert blog["page_type"] == "blog"
    assert blog["classification_reason"] == "matched_pattern:*/blog/*"


def test_inventory_auto_detect_screaming_frog_format(tmp_path: Path) -> None:
    """A CSV with `Address` + `Title 1` columns is routed to SF reader
    automatically, no `--format` needed."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    result = build_inventory(
        paths,
        write=False,
        source=FIXTURES / "internal_html.csv",
    )
    assert result["source_format"] == "screaming-frog"
    assert result["items_count"] == 5


def test_inventory_legacy_screaming_frog_columns(tmp_path: Path) -> None:
    """SF v15-17 used `Title`/`H1` (no '1' / '-1' suffix). Still works."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    result = build_inventory(
        paths,
        write=False,
        source=FIXTURES / "internal_legacy.csv",
        source_format="screaming-frog",
    )
    by_url = {item["url"]: item for item in result["items"]}
    assert by_url["https://example.com/"]["title"] == "Example Co"
    assert by_url["https://example.com/"]["h1"] == "Welcome"


def test_inventory_screaming_frog_via_cli(tmp_path: Path) -> None:
    code, _ = _run(
        ["init", "--client", "demo", "--workspace", str(tmp_path), "--write"]
    )
    assert code == 0
    code, payload = _run(
        [
            "build-inventory",
            "--client",
            "demo",
            "--workspace",
            str(tmp_path),
            "--source",
            str(FIXTURES / "internal_html.csv"),
            "--format",
            "screaming-frog",
            "--write",
        ]
    )
    assert code == 0
    assert payload["data"]["source_format"] == "screaming-frog"
    on_disk = json.loads(
        (tmp_path / "clients" / "demo" / "data" / "content_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    assert any(item["url"] == "https://example.com/" for item in on_disk)


def test_inventory_unknown_format_rejected_by_cli(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "build-inventory",
                "--client",
                "demo",
                "--workspace",
                str(tmp_path),
                "--source",
                str(FIXTURES / "internal_html.csv"),
                "--format",
                "screaming_frog",  # underscore typo
            ]
        )


# ---------------------------------------------------------------------------
# Link graph
# ---------------------------------------------------------------------------


def test_build_link_graph_from_screaming_frog(tmp_path: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    # Inventory first so nodes carry page_type info
    build_inventory(
        paths,
        write=True,
        source=FIXTURES / "internal_html.csv",
        source_format="screaming-frog",
    )
    result = build_link_graph(
        paths,
        write=True,
        source=FIXTURES / "all_inlinks.csv",
        source_format="screaming-frog",
    )
    assert result["source_format"] == "screaming-frog"
    edges = result["graph"]["edges"]
    assert {(e["source_url"], e["target_url"]) for e in edges} == {
        ("https://example.com/", "https://example.com/services/"),
        ("https://example.com/", "https://example.com/about/"),
        ("https://example.com/services/", "https://example.com/services/local-delivery/"),
        ("https://example.com/blog/how-to-plan-delivery/", "https://example.com/services/local-delivery/"),
        ("https://example.com/services/local-delivery/", "https://example.com/"),
    }


def test_link_graph_auto_detects_screaming_frog(tmp_path: Path) -> None:
    """A links CSV with Source/Destination/Anchor Text headers is
    auto-routed to the SF reader."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    build_inventory(
        paths,
        write=True,
        source=FIXTURES / "internal_html.csv",
        source_format="screaming-frog",
    )
    result = build_link_graph(
        paths,
        write=False,
        source=FIXTURES / "all_inlinks.csv",
    )
    assert result["source_format"] == "screaming-frog"
    assert result["edges_count"] == 5


def test_link_graph_legacy_screaming_frog_columns(tmp_path: Path) -> None:
    """`From`/`To` instead of `Source`/`Destination`."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    result = build_link_graph(
        paths,
        write=False,
        source=FIXTURES / "inlinks_legacy.csv",
        source_format="screaming-frog",
    )
    assert result["source_format"] == "screaming-frog"
    assert result["edges_count"] == 2


def test_link_graph_screaming_frog_via_cli(tmp_path: Path) -> None:
    _run(["init", "--client", "demo", "--workspace", str(tmp_path), "--write"])
    _run(
        [
            "build-inventory",
            "--client",
            "demo",
            "--workspace",
            str(tmp_path),
            "--source",
            str(FIXTURES / "internal_html.csv"),
            "--format",
            "screaming-frog",
            "--write",
        ]
    )
    code, payload = _run(
        [
            "build-link-graph",
            "--client",
            "demo",
            "--workspace",
            str(tmp_path),
            "--source",
            str(FIXTURES / "all_inlinks.csv"),
            "--format",
            "screaming-frog",
            "--write",
        ]
    )
    assert code == 0
    assert payload["data"]["source_format"] == "screaming-frog"
    assert payload["data"]["edges_count"] == 5
