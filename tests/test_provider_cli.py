"""End-to-end tests for the provider CLI commands."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from site_context_pipeline.cli import main


def _run(argv: list[str]) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    raw = buffer.getvalue().strip()
    payload = json.loads(raw) if raw else {}
    return code, payload


def test_list_providers_returns_both_kinds() -> None:
    code, payload = _run(["list-providers"])
    assert code == 0
    providers = payload["data"]["providers"]
    keyword_names = {p["name"] for p in providers["keyword"]}
    perf_names = {p["name"] for p in providers["search_performance"]}
    assert "local-csv" in keyword_names
    assert "google-ads" in keyword_names
    assert "local-gsc-csv" in perf_names
    assert "google-search-console" in perf_names


def test_import_keywords_local_csv_dry_run(
    seeded_workspace: Path, demo_keyword_csv: Path
) -> None:
    code, payload = _run(
        [
            "import-keywords",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--provider",
            "local-csv",
            "--source",
            str(demo_keyword_csv),
        ]
    )
    assert code == 0
    assert payload["dry_run"] is True
    assert payload["data"]["items_count"] == 6
    assert payload["data"]["preview"], "preview should include first rows"
    target = seeded_workspace / "clients" / "demo" / "data" / "keyword_metrics.json"
    assert not target.exists()


def test_import_keywords_local_csv_write(
    seeded_workspace: Path, demo_keyword_csv: Path
) -> None:
    target = seeded_workspace / "clients" / "demo" / "data" / "keyword_metrics.json"
    code, payload = _run(
        [
            "import-keywords",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--provider",
            "local-csv",
            "--source",
            str(demo_keyword_csv),
            "--write",
        ]
    )
    assert code == 0
    assert payload["write_performed"] is True
    assert target.exists()
    artifact = json.loads(target.read_text(encoding="utf-8"))
    assert artifact["provider"] == "local-csv"
    assert artifact["items_count"] == 6
    assert artifact["items"][0]["query"]
    assert artifact["items"][0]["source"] == "local-csv"


def test_import_search_performance_local_gsc_write(
    seeded_workspace: Path, demo_search_console_csv: Path
) -> None:
    target = seeded_workspace / "clients" / "demo" / "data" / "search_performance.json"
    code, payload = _run(
        [
            "import-search-performance",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--provider",
            "local-gsc-csv",
            "--source",
            str(demo_search_console_csv),
            "--write",
        ]
    )
    assert code == 0
    assert payload["write_performed"] is True
    assert target.exists()
    artifact = json.loads(target.read_text(encoding="utf-8"))
    assert artifact["provider"] == "local-gsc-csv"
    assert artifact["items_count"] == 6


def test_import_keywords_google_ads_stub_returns_not_configured(
    seeded_workspace: Path,
) -> None:
    code, payload = _run(
        [
            "import-keywords",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--provider",
            "google-ads",
        ]
    )
    assert code == 1
    assert payload["ok"] is False
    assert "not_configured" in payload["errors"]
    assert payload["data"]["provider"] == "google-ads"
    assert payload["data"]["items_count"] == 0


def test_import_search_performance_gsc_stub_returns_not_configured(
    seeded_workspace: Path,
) -> None:
    code, payload = _run(
        [
            "import-search-performance",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--provider",
            "google-search-console",
        ]
    )
    assert code == 1
    assert payload["ok"] is False
    assert "not_configured" in payload["errors"]


def test_import_keywords_unknown_provider_returns_error(seeded_workspace: Path) -> None:
    code, payload = _run(
        [
            "import-keywords",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--provider",
            "no-such-thing",
        ]
    )
    assert code == 1
    assert payload["ok"] is False
    assert payload["errors"]


def test_import_keywords_missing_source_returns_error(seeded_workspace: Path) -> None:
    code, payload = _run(
        [
            "import-keywords",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--provider",
            "local-csv",
        ]
    )
    assert code == 1
    assert payload["ok"] is False
    assert payload["errors"]


def test_import_keywords_invalid_path_returns_error(
    seeded_workspace: Path, tmp_path: Path
) -> None:
    code, payload = _run(
        [
            "import-keywords",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--provider",
            "local-csv",
            "--source",
            str(tmp_path / "missing.csv"),
        ]
    )
    assert code == 1
    assert payload["ok"] is False


def test_import_keywords_invalid_config_returns_error(
    seeded_workspace: Path, demo_keyword_csv: Path, tmp_path: Path
) -> None:
    bad_config = tmp_path / "bad.json"
    bad_config.write_text("not json", encoding="utf-8")
    code, payload = _run(
        [
            "import-keywords",
            "--client",
            "demo",
            "--workspace",
            str(seeded_workspace),
            "--provider",
            "local-csv",
            "--source",
            str(demo_keyword_csv),
            "--config",
            str(bad_config),
        ]
    )
    assert code == 1
    assert payload["ok"] is False
    assert any("provider_config_invalid_json" in err for err in payload["errors"])
