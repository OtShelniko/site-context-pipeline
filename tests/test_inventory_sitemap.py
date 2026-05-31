"""Integration tests: build_inventory with the sitemap importer.

The flat-CSV path is already covered by tests/test_inventory.py; this
module focuses on the sitemap-specific behaviour wired through
``build_inventory(... source_format='sitemap')`` and the CLI's
``--format sitemap`` flag.
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

FIXTURES = Path(__file__).parent / "fixtures"


def _run(argv: list[str]) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    raw = buffer.getvalue().strip()
    payload = json.loads(raw) if raw else {}
    return code, payload


def test_build_inventory_from_sitemap(tmp_path: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    result = build_inventory(
        paths,
        write=True,
        source=FIXTURES / "sitemap_simple.xml",
        source_format="sitemap",
    )
    assert result["source_format"] == "sitemap"
    by_url = {item["url"]: item for item in result["items"]}
    assert "https://example.com/" in by_url
    home = by_url["https://example.com/"]
    assert home["page_type"] == "home"
    assert home["classification_reason"] == "matched_home_path"
    assert home["source"] == "sitemap"
    # Sitemap rows do not carry titles or word counts.
    assert home["title"] is None
    assert home["word_count"] is None

    blog = by_url["https://example.com/blog/how-to-plan-delivery/"]
    assert blog["page_type"] == "blog"
    assert blog["classification_reason"] == "matched_pattern:*/blog/*"


def test_format_auto_detects_xml_extension(tmp_path: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    result = build_inventory(
        paths,
        write=False,
        source=FIXTURES / "sitemap_simple.xml",
    )
    assert result["source_format"] == "sitemap"
    assert result["items_count"] == 5


def test_explicit_format_overrides_extension(tmp_path: Path) -> None:
    """If a user mislabels their file, the --format flag wins."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    # Copy the sitemap to a .txt path so auto-detection would fail.
    odd = tmp_path / "weird-name.txt"
    odd.write_bytes((FIXTURES / "sitemap_simple.xml").read_bytes())
    result = build_inventory(
        paths,
        write=False,
        source=odd,
        source_format="sitemap",
    )
    assert result["source_format"] == "sitemap"
    assert result["items_count"] == 5


def test_sitemap_index_walks_local_children(tmp_path: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    result = build_inventory(
        paths,
        write=False,
        source=FIXTURES / "sitemap_index.xml",
        source_format="sitemap",
    )
    urls = {item["url"] for item in result["items"]}
    assert "https://example.com/blog/how-to-plan-delivery/" in urls
    assert "https://example.com/blog/delivery-cost-guide/" in urls
    assert result["items_count"] >= 4


def test_malformed_sitemap_returns_warning_not_exception(tmp_path: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    result = build_inventory(
        paths,
        write=False,
        source=FIXTURES / "sitemap_malformed.xml",
        source_format="sitemap",
    )
    assert result["items_count"] == 0
    assert any(w.startswith("sitemap_import_error:") for w in result["warnings"])


def test_unsupported_extension_warns(tmp_path: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    bogus = tmp_path / "data.bogus"
    bogus.write_text("nope", encoding="utf-8")
    result = build_inventory(paths, write=False, source=bogus)
    assert result["items_count"] == 0
    assert any("unsupported_source_extension" in w for w in result["warnings"])


def test_explicit_format_sitemap_via_cli(tmp_path: Path) -> None:
    """End-to-end: the CLI exposes --format sitemap and it round-trips."""
    code, _ = _run(
        [
            "init",
            "--client",
            "demo",
            "--workspace",
            str(tmp_path),
            "--write",
        ]
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
            str(FIXTURES / "sitemap_simple.xml"),
            "--format",
            "sitemap",
            "--write",
        ]
    )
    assert code == 0
    assert payload["data"]["source_format"] == "sitemap"
    on_disk_path = tmp_path / "clients" / "demo" / "data" / "content_inventory.json"
    assert on_disk_path.exists()
    items = json.loads(on_disk_path.read_text(encoding="utf-8"))
    assert any(item["url"] == "https://example.com/" for item in items)


def test_invalid_format_choice_is_rejected_by_cli(tmp_path: Path) -> None:
    """argparse must reject an unknown --format value."""
    with pytest.raises(SystemExit):
        main(
            [
                "build-inventory",
                "--client",
                "demo",
                "--workspace",
                str(tmp_path),
                "--source",
                str(FIXTURES / "sitemap_simple.xml"),
                "--format",
                "totally-made-up",
            ]
        )
