"""End-to-end tests for the `qa-draft` CLI command."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from site_context_pipeline.cli import main
from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.inventory import build_inventory

FIXTURES = Path(__file__).parent / "fixtures" / "qa"
DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo-client"


def _run(argv: list[str]) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    raw = buffer.getvalue().strip()
    payload = json.loads(raw) if raw else {}
    return code, payload


def _seed_workspace(tmp_path: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    build_inventory(paths, write=True, source=DEMO / "input" / "urls.csv")


def test_qa_draft_dry_run_returns_report(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    code, payload = _run(
        [
            "qa-draft",
            "--client",
            "demo",
            "--workspace",
            str(tmp_path),
            "--draft",
            str(FIXTURES / "green_draft.md"),
        ]
    )
    # green_draft passes every check; exit code is 0.
    assert code == 0
    data = payload["data"]
    assert data["overall_level"] in {"green", "orange"}
    assert data["report"]["findings"]
    # Dry run — no qa report file written.
    assert not (tmp_path / "clients" / "demo" / "output" / "qa_reports").exists()


def test_qa_draft_red_draft_exits_nonzero(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    code, payload = _run(
        [
            "qa-draft",
            "--client",
            "demo",
            "--workspace",
            str(tmp_path),
            "--draft",
            str(FIXTURES / "red_no_h1.md"),
        ]
    )
    assert code == 1
    assert payload["ok"] is False
    assert payload["data"]["overall_level"] == "red"


def test_qa_draft_write_persists_report(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    code, payload = _run(
        [
            "qa-draft",
            "--client",
            "demo",
            "--workspace",
            str(tmp_path),
            "--draft",
            str(FIXTURES / "green_draft.md"),
            "--write",
        ]
    )
    assert code == 0
    written = payload["written_files"]
    assert len(written) == 1
    on_disk = json.loads(Path(written[0]).read_text(encoding="utf-8"))
    assert on_disk["overall_level"] in {"green", "orange"}
    assert isinstance(on_disk["findings"], list)


def test_qa_draft_missing_path(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    code, payload = _run(
        [
            "qa-draft",
            "--client",
            "demo",
            "--workspace",
            str(tmp_path),
            "--draft",
            str(tmp_path / "no-such.md"),
        ]
    )
    assert code == 1
    assert any(err.startswith("draft_not_found") for err in payload["errors"])


def test_qa_draft_uses_inventory_for_link_check(tmp_path: Path) -> None:
    """Internal links pointing at URLs not in the inventory must come
    back red — proves the CLI passes the inventory through."""
    _seed_workspace(tmp_path)
    code, payload = _run(
        [
            "qa-draft",
            "--client",
            "demo",
            "--workspace",
            str(tmp_path),
            "--draft",
            str(FIXTURES / "red_link_off_inventory.md"),
        ]
    )
    findings = {f["name"]: f for f in payload["data"]["report"]["findings"]}
    assert findings["links_resolve"]["level"] == "red"
    assert "legacy-page" in str(findings["links_resolve"]["details"])


def test_qa_draft_keyphrase_override(tmp_path: Path) -> None:
    """A draft without frontmatter keyphrase still works when the CLI
    supplies one explicitly."""
    _seed_workspace(tmp_path)
    md_path = tmp_path / "no_fm.md"
    md_path.write_text(
        "# Hello world\n\nA short body about hello world.\n",
        encoding="utf-8",
    )
    code, payload = _run(
        [
            "qa-draft",
            "--client",
            "demo",
            "--workspace",
            str(tmp_path),
            "--draft",
            str(md_path),
            "--keyphrase",
            "hello world",
            "--slug",
            "hello-world",
        ]
    )
    assert code in {0, 1}  # may be red because intro is short, but no crash
    assert payload["data"]["keyphrase"] == "hello world"


def test_qa_draft_without_keyphrase_returns_error(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    md_path = tmp_path / "no_fm.md"
    md_path.write_text("# Hello\n\nbody\n", encoding="utf-8")
    code, payload = _run(
        [
            "qa-draft",
            "--client",
            "demo",
            "--workspace",
            str(tmp_path),
            "--draft",
            str(md_path),
        ]
    )
    assert code == 1
    assert payload["ok"] is False
    assert payload["errors"]
