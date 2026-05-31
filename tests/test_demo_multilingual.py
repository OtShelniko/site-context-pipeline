"""End-to-end smoke test for the multilingual demo client.

Builds the full pipeline against `examples/demo-multilingual/` and
asserts that the classifier handles locale-prefixed URL trees and that
the keyword artifact preserves per-market `geo` / `language` / `locale`
values without the core needing to "understand" any language.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.context_pack import build_context_pack
from site_context_pipeline.inventory import build_inventory
from site_context_pipeline.link_graph import build_link_graph
from site_context_pipeline.providers.local_keyword_csv import LocalKeywordCsvProvider

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_FIXTURE = REPO_ROOT / "examples" / "demo-multilingual"


def _seed_workspace(tmp_path: Path) -> Path:
    paths = get_client_paths("ml", workspace=tmp_path)
    init_client(paths, write=True)
    for sub in ("input", "config"):
        src = DEMO_FIXTURE / sub
        if not src.exists():
            continue
        for path in src.iterdir():
            if path.is_file():
                shutil.copy2(path, getattr(paths, sub) / path.name)
    return tmp_path


def test_localized_slugs_map_to_the_same_page_type(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    paths = get_client_paths("ml", workspace=tmp_path)
    build_inventory(paths, write=True, source=DEMO_FIXTURE / "input" / "urls.csv")
    inventory = json.loads(
        (paths.data / "content_inventory.json").read_text("utf-8")
    )
    by_url = {item["url"]: item for item in inventory}

    # pricing == preise == tarifs all resolve to `landing` (via the
    # commercial-URL list, which beats the per-locale pattern rules).
    for url in (
        "https://docs.example.org/en/pricing/",
        "https://docs.example.org/de/preise/",
        "https://docs.example.org/fr/tarifs/",
    ):
        assert by_url[url]["page_type"] == "landing", url

    # guides == anleitungen both resolve to `blog`.
    assert (
        by_url["https://docs.example.org/en/guides/automations/"]["page_type"]
        == "blog"
    )
    assert (
        by_url["https://docs.example.org/de/anleitungen/automatisierungen/"][
            "page_type"
        ]
        == "blog"
    )

    # The three locale roots are section hubs forced into `category`
    # via allow_urls.
    for url in (
        "https://docs.example.org/en/",
        "https://docs.example.org/de/",
        "https://docs.example.org/fr/",
    ):
        node = by_url[url]
        assert node["page_type"] == "category", url
        assert node["classification_reason"] == "matched_allow_url:category"


def test_keyword_metrics_preserve_three_locales(tmp_path: Path) -> None:
    result = LocalKeywordCsvProvider().run(
        source=str(DEMO_FIXTURE / "input" / "keyword_metrics.csv")
    )
    locales = {item["locale"] for item in result.items}
    geos = {item["geo"] for item in result.items}
    languages = {item["language"] for item in result.items}
    assert locales == {"en-US", "de-DE", "fr-FR"}
    assert geos == {"US", "DE", "FR"}
    assert languages == {"en", "de", "fr"}


def test_demo_multilingual_pack_summary(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    paths = get_client_paths("ml", workspace=tmp_path)
    build_inventory(paths, write=True, source=DEMO_FIXTURE / "input" / "urls.csv")
    build_link_graph(paths, write=True, source=DEMO_FIXTURE / "input" / "links.csv")
    result = build_context_pack(paths, write=True)
    summary = result["pack"]["summary"]

    assert summary["page_count"] == 14
    counts = summary["page_type_counts"]
    assert counts["category"] == 3  # one locale hub per language
    assert counts["landing"] == 3  # one pricing page per language
    assert counts["blog"] == 7
