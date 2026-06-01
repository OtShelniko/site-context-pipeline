"""Performance regression guard for the offline pipeline.

Builds a synthetic site and asserts each core builder finishes within a
generous wall-clock budget. The point is not to measure absolute speed
(CI runners vary wildly) but to catch *algorithmic* regressions — an
accidental O(n²) join in the link graph, say, would blow the budget by
orders of magnitude even on a slow runner.

Scale is configurable via the ``SCP_PERF_URLS`` environment variable so
the same test can run a fast smoke in CI and a realistic 50k load
locally:

    SCP_PERF_URLS=50000 pytest tests/test_perf_benchmark.py -v

The default (2,000 URLs) keeps the suite fast. For ad-hoc profiling at
full scale use ``scripts/perf_benchmark.py`` instead.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

# Reuse the synthetic generators from the standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from perf_benchmark import write_inventory_csv, write_links_csv  # noqa: E402

from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.context_pack import build_context_pack
from site_context_pipeline.inventory import build_inventory
from site_context_pipeline.link_graph import build_link_graph

# Keep the default small so the suite stays fast; override for load tests.
_URL_COUNT = int(os.environ.get("SCP_PERF_URLS", "2000"))

# Per-stage budgets in seconds. Deliberately loose — a healthy build of a
# few thousand URLs runs in well under a second locally; these budgets
# scale with the URL count and only trip on a real algorithmic blow-up.
# Allow extra headroom for large opt-in loads and slow CI runners.
_BUDGET_PER_1K_SECONDS = 3.0
_MIN_BUDGET_SECONDS = 5.0


def _budget() -> float:
    return max(_MIN_BUDGET_SECONDS, _BUDGET_PER_1K_SECONDS * (_URL_COUNT / 1000.0))


@pytest.fixture(scope="module")
def perf_workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    workspace = tmp_path_factory.mktemp("perf")
    write_inventory_csv(workspace / "urls.csv", _URL_COUNT)
    write_links_csv(workspace / "links.csv", _URL_COUNT)
    paths = get_client_paths("perf", workspace=workspace)
    init_client(paths, write=True)
    return workspace


def test_build_inventory_within_budget(perf_workspace: Path) -> None:
    paths = get_client_paths("perf", workspace=perf_workspace)
    start = time.perf_counter()
    result = build_inventory(paths, write=True, source=perf_workspace / "urls.csv")
    elapsed = time.perf_counter() - start

    # +1 for the home page row.
    assert result["items_count"] == _URL_COUNT + 1
    assert elapsed < _budget(), (
        f"build_inventory took {elapsed:.2f}s for {_URL_COUNT} URLs; "
        f"budget {_budget():.1f}s"
    )


def test_build_link_graph_within_budget(perf_workspace: Path) -> None:
    paths = get_client_paths("perf", workspace=perf_workspace)
    # inventory must exist first (module-scoped order is not guaranteed,
    # so build it here if the inventory test has not run).
    if not (paths.data / "content_inventory.json").exists():
        build_inventory(paths, write=True, source=perf_workspace / "urls.csv")

    start = time.perf_counter()
    result = build_link_graph(paths, write=True, source=perf_workspace / "links.csv")
    elapsed = time.perf_counter() - start

    assert result["nodes_count"] >= _URL_COUNT
    assert result["edges_count"] >= _URL_COUNT  # two edges per page, deduped
    assert elapsed < _budget(), (
        f"build_link_graph took {elapsed:.2f}s for {_URL_COUNT} URLs; "
        f"budget {_budget():.1f}s"
    )


def test_build_context_pack_within_budget(perf_workspace: Path) -> None:
    paths = get_client_paths("perf", workspace=perf_workspace)
    if not (paths.data / "content_inventory.json").exists():
        build_inventory(paths, write=True, source=perf_workspace / "urls.csv")
    if not (paths.data / "internal_link_graph.json").exists():
        build_link_graph(paths, write=True, source=perf_workspace / "links.csv")

    start = time.perf_counter()
    result = build_context_pack(paths, write=True)
    elapsed = time.perf_counter() - start

    assert result["pack"]["summary"]["page_count"] == _URL_COUNT + 1
    assert elapsed < _budget(), (
        f"build_context_pack took {elapsed:.2f}s for {_URL_COUNT} URLs; "
        f"budget {_budget():.1f}s"
    )
