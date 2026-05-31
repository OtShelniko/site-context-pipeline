"""End-to-end tests for the CLI.

These tests run the CLI in-process via ``cli.main(argv)`` so we never spawn
a subprocess and never need the package to be installed first.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from site_context_pipeline import __version__
from site_context_pipeline.cli import main


def _run(argv: list[str]) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    raw = buffer.getvalue().strip()
    payload = json.loads(raw) if raw else {}
    return code, payload


def test_package_imports_and_has_version() -> None:
    assert __version__ == "0.1.0"


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "site-context-pipeline" in captured.out


def test_init_dry_run_does_not_create_files(workspace: Path) -> None:
    code, payload = _run(["init", "--client", "demo", "--workspace", str(workspace)])
    assert code == 0
    assert payload["dry_run"] is True
    assert payload["write_performed"] is False
    assert payload["planned_writes"], "init should always plan writes"
    assert not (workspace / "clients" / "demo").exists()


def test_init_write_creates_layout(workspace: Path) -> None:
    code, payload = _run(["init", "--client", "demo", "--workspace", str(workspace), "--write"])
    assert code == 0
    assert payload["write_performed"] is True
    client_root = workspace / "clients" / "demo"
    for sub in ("input", "config", "data", "output", "logs"):
        assert (client_root / sub).is_dir()
    assert (client_root / "input" / "project.md").exists()
    assert (client_root / "input" / "urls.csv").exists()


def test_init_write_twice_is_idempotent(workspace: Path) -> None:
    _run(["init", "--client", "demo", "--workspace", str(workspace), "--write"])
    code, payload = _run(["init", "--client", "demo", "--workspace", str(workspace), "--write"])
    assert code == 0
    assert payload["skipped_existing"], "second run should skip existing files"


def test_build_inventory_dry_run_writes_nothing(
    seeded_workspace: Path, demo_urls_csv: Path
) -> None:
    code, payload = _run(
        [
            "build-inventory",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--source",
            str(demo_urls_csv),
        ]
    )
    assert code == 0
    assert payload["dry_run"] is True
    assert not (seeded_workspace / "clients" / "demo" / "data" / "content_inventory.json").exists()


def test_full_pipeline_writes_all_expected_artifacts(
    seeded_workspace: Path, demo_urls_csv: Path, demo_links_csv: Path
) -> None:
    inventory_path = seeded_workspace / "clients" / "demo" / "data" / "content_inventory.json"
    graph_path = seeded_workspace / "clients" / "demo" / "data" / "internal_link_graph.json"
    pack_json = seeded_workspace / "clients" / "demo" / "output" / "agent_context_pack.json"
    pack_md = seeded_workspace / "clients" / "demo" / "output" / "agent_context_pack.md"
    opp_md = seeded_workspace / "clients" / "demo" / "output" / "content_opportunities.md"

    code, _ = _run(
        [
            "build-inventory",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--source",
            str(demo_urls_csv),
            "--write",
        ]
    )
    assert code == 0
    assert inventory_path.exists()

    code, _ = _run(
        [
            "build-link-graph",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--source",
            str(demo_links_csv),
            "--write",
        ]
    )
    assert code == 0
    assert graph_path.exists()

    code, payload = _run(
        [
            "build-context-pack",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--write",
        ]
    )
    assert code == 0
    assert pack_json.exists()
    assert pack_md.exists()
    assert opp_md.exists()
    assert payload["data"]["pack"]["summary"]["page_count"] >= 1


def test_inspect_returns_check_list(seeded_workspace: Path) -> None:
    code, payload = _run(["inspect", "--client", "demo", "--workspace", str(seeded_workspace)])
    assert code == 0
    checks = payload["data"]["checks"]
    names = {check["name"] for check in checks}
    assert "input_dir" in names
    assert "data/content_inventory.json" in names


def test_invalid_client_id_is_rejected(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(ValueError):
        main(["init", "--client", "../etc", "--workspace", str(workspace)])
