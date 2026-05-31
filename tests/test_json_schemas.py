"""Validate every shipped artifact against its public JSON Schema.

The schemas live under ``site_context_pipeline/json_schema/`` and are
loaded via ``load_schema()``. The tests build a real demo workspace,
run every CLI verb, then validate the on-disk JSON output against the
matching schema.

If a future change accidentally drops a required field or changes a
type, these tests fail loudly so downstream consumers (LLM agents, CI
pipelines, lint rules) can keep relying on the contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.context_pack import build_context_pack
from site_context_pipeline.inventory import build_inventory
from site_context_pipeline.json_schema import list_schemas, load_schema, schema_filename
from site_context_pipeline.link_graph import build_link_graph
from site_context_pipeline.providers.local_keyword_csv import LocalKeywordCsvProvider
from site_context_pipeline.providers.local_search_console_csv import (
    LocalSearchConsoleCsvProvider,
)
from site_context_pipeline.providers.local_search_evidence_csv import (
    LocalSearchEvidenceCsvProvider,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_FIXTURE = REPO_ROOT / "examples" / "demo-client"


def _build_validator(schema_name: str) -> Draft202012Validator:
    """Build a 2020-12 validator with cross-schema $refs resolved.

    The pack and link-graph schemas reference inventory definitions via
    relative ``$ref`` strings. The registry maps the schema's $id to its
    document so the validator can resolve those references without ever
    touching the network.
    """

    main = load_schema(schema_name)
    registry: Registry[Any] = Registry()
    for name in list_schemas():
        doc = load_schema(name)
        resource = Resource.from_contents(doc)
        # Register under both the file basename (used as relative ref
        # from sibling schemas) and the canonical $id.
        registry = registry.with_resource(uri=schema_filename(name), resource=resource)
        registry = registry.with_resource(uri=doc["$id"], resource=resource)
    return Draft202012Validator(main, registry=registry)


def _validate(schema_name: str, instance: Any) -> None:
    validator = _build_validator(schema_name)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if errors:
        formatted = "\n".join(
            f"  - {list(err.absolute_path)}: {err.message}" for err in errors
        )
        raise AssertionError(
            f"Schema {schema_name!r} rejected instance:\n{formatted}"
        )


# ---------------------------------------------------------------------------
# Loader / packaging contract
# ---------------------------------------------------------------------------


def test_six_schemas_ship_with_the_package() -> None:
    expected = {
        "agent_context_pack",
        "content_inventory",
        "internal_link_graph",
        "keyword_metrics",
        "search_performance",
        "search_evidence",
    }
    assert set(list_schemas()) == expected


def test_every_schema_loads_and_has_id() -> None:
    for name in list_schemas():
        doc = load_schema(name)
        assert doc.get("$schema", "").endswith("2020-12/schema")
        assert isinstance(doc.get("$id"), str) and doc["$id"].startswith("https://")
        assert doc.get("title")


def test_every_schema_is_self_consistent() -> None:
    """The schema document itself must be a valid Draft 2020-12 schema."""

    for name in list_schemas():
        Draft202012Validator.check_schema(load_schema(name))


# ---------------------------------------------------------------------------
# Real artifacts validate against their schemas
# ---------------------------------------------------------------------------


def test_inventory_and_link_graph_match_schemas(
    tmp_path: Path, demo_urls_csv: Path, demo_links_csv: Path
) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    build_inventory(paths, write=True, source=demo_urls_csv)
    build_link_graph(paths, write=True, source=demo_links_csv)

    inventory = json.loads((paths.data / "content_inventory.json").read_text("utf-8"))
    link_graph = json.loads((paths.data / "internal_link_graph.json").read_text("utf-8"))

    _validate("content_inventory", inventory)
    _validate("internal_link_graph", link_graph)


def test_keyword_metrics_artifact_matches_schema(demo_keyword_csv: Path) -> None:
    result = LocalKeywordCsvProvider().run(source=str(demo_keyword_csv))
    payload = {
        "schema_version": 1,
        "provider": "local-csv",
        "items_count": len(result.items),
        "metadata": result.metadata,
        "warnings": result.warnings,
        "items": result.items,
    }
    _validate("keyword_metrics", payload)


def test_search_performance_artifact_matches_schema(
    demo_search_console_csv: Path,
) -> None:
    result = LocalSearchConsoleCsvProvider().run(source=str(demo_search_console_csv))
    payload = {
        "schema_version": 1,
        "provider": "local-gsc-csv",
        "items_count": len(result.items),
        "metadata": result.metadata,
        "warnings": result.warnings,
        "items": result.items,
    }
    _validate("search_performance", payload)


def test_search_evidence_artifact_matches_schema() -> None:
    fixture = DEMO_FIXTURE / "input" / "search_evidence.csv"
    assert fixture.exists(), f"missing demo fixture {fixture}"
    result = LocalSearchEvidenceCsvProvider().run(source=str(fixture))
    payload = {
        "schema_version": 1,
        "provider": "local-serp-csv",
        "items_count": len(result.items),
        "metadata": result.metadata,
        "warnings": result.warnings,
        "items": result.items,
    }
    _validate("search_evidence", payload)


def test_agent_context_pack_matches_schema(
    tmp_path: Path, demo_urls_csv: Path, demo_links_csv: Path
) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    build_inventory(paths, write=True, source=demo_urls_csv)
    build_link_graph(paths, write=True, source=demo_links_csv)
    result = build_context_pack(paths, write=True)

    on_disk = json.loads(
        (paths.output / "agent_context_pack.json").read_text("utf-8")
    )
    _validate("agent_context_pack", result["pack"])
    _validate("agent_context_pack", on_disk)
