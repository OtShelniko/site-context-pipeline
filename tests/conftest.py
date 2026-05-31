"""Shared test fixtures.

Tests must remain offline and self-contained. The fixture below builds a
fresh workspace under ``tmp_path`` and seeds it with the static demo
fixtures shipped under ``examples/demo-client/``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_FIXTURE = REPO_ROOT / "examples" / "demo-client"


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """An empty workspace ready for ``init --client demo``."""
    return tmp_path


@pytest.fixture()
def seeded_workspace(tmp_path: Path) -> Path:
    """A workspace with ``clients/demo/`` populated from the demo fixtures."""
    target = tmp_path / "clients" / "demo"
    target.mkdir(parents=True, exist_ok=True)
    for sub in ("input", "config", "data", "output", "logs"):
        (target / sub).mkdir(exist_ok=True)
    for sub in ("input", "config"):
        src = DEMO_FIXTURE / sub
        if not src.exists():
            continue
        for path in src.iterdir():
            if path.is_file():
                shutil.copy2(path, target / sub / path.name)
    return tmp_path


@pytest.fixture()
def demo_urls_csv() -> Path:
    return DEMO_FIXTURE / "input" / "urls.csv"


@pytest.fixture()
def demo_links_csv() -> Path:
    return DEMO_FIXTURE / "input" / "links.csv"


@pytest.fixture()
def demo_keyword_csv() -> Path:
    return DEMO_FIXTURE / "input" / "keyword_metrics.csv"


@pytest.fixture()
def demo_search_console_csv() -> Path:
    return DEMO_FIXTURE / "input" / "search_console.csv"
