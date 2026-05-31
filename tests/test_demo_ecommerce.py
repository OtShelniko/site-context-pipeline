"""End-to-end smoke test for the second demo client.

Builds the full pipeline against `examples/demo-ecommerce/` and asserts
that the classifier picks up the e-commerce-specific page types and
that the resulting context pack still validates against the public
JSON Schema.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.context_pack import build_context_pack
from site_context_pipeline.inventory import build_inventory
from site_context_pipeline.json_schema import list_schemas, load_schema, schema_filename
from site_context_pipeline.link_graph import build_link_graph

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_FIXTURE = REPO_ROOT / "examples" / "demo-ecommerce"


def _seed_workspace(tmp_path: Path) -> Path:
    """Mirror the e-commerce demo's input + config into a fresh workspace."""

    paths = get_client_paths("ecom", workspace=tmp_path)
    init_client(paths, write=True)
    for sub in ("input", "config"):
        src = DEMO_FIXTURE / sub
        if not src.exists():
            continue
        for path in src.iterdir():
            if path.is_file():
                shutil.copy2(path, getattr(paths, sub) / path.name)
    return tmp_path


def test_demo_ecommerce_inventory_classifies_product_and_category(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    paths = get_client_paths("ecom", workspace=tmp_path)
    build_inventory(
        paths, write=True, source=DEMO_FIXTURE / "input" / "urls.csv"
    )
    inventory = json.loads(
        (paths.data / "content_inventory.json").read_text("utf-8")
    )
    by_url = {item["url"]: item for item in inventory}

    # Categories that are also commercial URLs win the `landing` bucket
    # (the commercial-URL list takes precedence over the category rule).
    espresso = by_url["https://shop.example.com/category/coffee-makers/espresso/"]
    assert espresso["page_type"] == "landing"
    assert espresso["classification_reason"] == "matched_commercial_url_list"

    # Other category URLs fall through to the category rule.
    coffee_makers = by_url["https://shop.example.com/category/coffee-makers/"]
    assert coffee_makers["page_type"] == "category"

    # Product URLs hit the `*/product/*` pattern rule.
    grinder = by_url["https://shop.example.com/product/burr-grinder-pro/"]
    assert grinder["page_type"] == "landing"
    assert grinder["classification_reason"] == "matched_pattern:*/product/*"

    # Cart/checkout are forced into `other` via the rule's allow_urls.
    cart = by_url["https://shop.example.com/cart/"]
    assert cart["page_type"] == "other"


def test_demo_ecommerce_pack_validates_against_schema(tmp_path: Path) -> None:
    """Run the whole pipeline and validate the pack against its schema."""
    pytest.importorskip("jsonschema")
    pytest.importorskip("referencing")
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    _seed_workspace(tmp_path)
    paths = get_client_paths("ecom", workspace=tmp_path)
    build_inventory(
        paths, write=True, source=DEMO_FIXTURE / "input" / "urls.csv"
    )
    build_link_graph(
        paths, write=True, source=DEMO_FIXTURE / "input" / "links.csv"
    )
    build_context_pack(paths, write=True)
    pack = json.loads(
        (paths.output / "agent_context_pack.json").read_text("utf-8")
    )

    registry: Registry[object] = Registry()
    for name in list_schemas():
        doc = load_schema(name)
        resource = Resource.from_contents(doc)
        registry = registry.with_resource(uri=schema_filename(name), resource=resource)
        registry = registry.with_resource(uri=doc["$id"], resource=resource)
    validator = Draft202012Validator(load_schema("agent_context_pack"), registry=registry)
    errors = sorted(validator.iter_errors(pack), key=lambda e: list(e.absolute_path))
    assert not errors, [(list(e.absolute_path), e.message) for e in errors]

    # Sanity: e-commerce-specific signals show up in the summary.
    counts = pack["summary"]["page_type_counts"]
    assert counts.get("category", 0) >= 1
    assert counts.get("landing", 0) >= 3  # 3 promoted categories + products
    assert pack["summary"]["page_count"] == 14
