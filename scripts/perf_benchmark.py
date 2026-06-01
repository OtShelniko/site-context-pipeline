#!/usr/bin/env python3
"""Standalone performance benchmark for the offline pipeline.

Generates a synthetic site of N pages plus an edge list, then times the
three core builders (inventory, link graph, context pack) end to end.
Everything is synthetic ``example.com`` data — no real site, no network.

Usage::

    python scripts/perf_benchmark.py            # default 50,000 URLs
    python scripts/perf_benchmark.py --urls 100000
    python scripts/perf_benchmark.py --urls 10000 --keep   # keep workspace

This is a developer tool, not part of the test suite. The pytest
benchmark in ``tests/test_perf_benchmark.py`` runs a smaller, budgeted
version on every CI run to catch algorithmic regressions; this script
is for ad-hoc profiling at realistic scale.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.context_pack import build_context_pack
from site_context_pipeline.inventory import build_inventory
from site_context_pipeline.link_graph import build_link_graph

# A handful of path shapes so the classifier exercises several rules.
_PAGE_SHAPES = (
    ("blog", "/blog/post-{i}/"),
    ("service", "/services/service-{i}/"),
    ("category", "/category/cat-{i}/"),
    ("landing", "/lp/landing-{i}/"),
    ("other", "/misc/page-{i}/"),
)


def write_inventory_csv(path: Path, url_count: int) -> None:
    """Write a synthetic inventory CSV with ``url_count`` rows."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["url", "title", "h1", "status_code", "word_count", "inlinks_count", "outlinks_count"]
        )
        writer.writerow(["https://example.com/", "Home", "Home", 200, 200, 10, 20])
        for i in range(url_count):
            _, shape = _PAGE_SHAPES[i % len(_PAGE_SHAPES)]
            url = "https://example.com" + shape.format(i=i)
            writer.writerow([url, f"Title {i}", f"H1 {i}", 200, 800 + (i % 700), i % 5, i % 9])


def write_links_csv(path: Path, url_count: int) -> None:
    """Write a synthetic edge list: each page links to the next two."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source_url", "target_url", "anchor_text"])
        for i in range(url_count):
            _, shape = _PAGE_SHAPES[i % len(_PAGE_SHAPES)]
            src = "https://example.com" + shape.format(i=i)
            for offset in (1, 2):
                j = (i + offset) % url_count
                _, tshape = _PAGE_SHAPES[j % len(_PAGE_SHAPES)]
                dst = "https://example.com" + tshape.format(i=j)
                writer.writerow([src, dst, f"link {i}->{j}"])


@contextmanager
def timed(label: str) -> Iterator[None]:
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"  {label:<22} {elapsed:8.3f}s")


def run(url_count: int, keep: bool) -> None:
    workspace = Path(tempfile.mkdtemp(prefix="scp_perf_"))
    try:
        urls_csv = workspace / "urls.csv"
        links_csv = workspace / "links.csv"
        print(f"Generating {url_count:,} URLs + edges …")
        write_inventory_csv(urls_csv, url_count)
        write_links_csv(links_csv, url_count)

        paths = get_client_paths("perf", workspace=workspace)
        init_client(paths, write=True)

        print(f"Timing pipeline for {url_count:,} URLs:")
        with timed("build_inventory"):
            build_inventory(paths, write=True, source=urls_csv)
        with timed("build_link_graph"):
            build_link_graph(paths, write=True, source=links_csv)
        with timed("build_context_pack"):
            build_context_pack(paths, write=True)

        pack = paths.output / "agent_context_pack.json"
        print(f"  pack size: {pack.stat().st_size / 1024:.0f} KiB")
    finally:
        if keep:
            print(f"workspace kept at: {workspace}")
        else:
            shutil.rmtree(workspace, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--urls", type=int, default=50_000, help="number of URLs to synthesize")
    parser.add_argument("--keep", action="store_true", help="keep the temp workspace")
    args = parser.parse_args()
    run(args.urls, args.keep)


if __name__ == "__main__":
    main()
