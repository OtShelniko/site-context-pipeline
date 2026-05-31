"""Public JSON Schema files for every artifact this toolkit emits.

The schemas live alongside the package so they ship in the wheel and can
be loaded from a fresh `pip install`. Each schema follows JSON Schema
2020-12 and uses the canonical filename of the artifact it describes.

Usage::

    from site_context_pipeline.json_schema import load_schema, list_schemas

    schema = load_schema("agent_context_pack")
    print(list_schemas())

The loader is intentionally tiny — it returns the raw dict so callers
can plug in any validator they prefer (`jsonschema`, `fastjsonschema`,
`check-jsonschema`, etc.). The base package does not require any of
them at runtime.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

# Logical name -> file basename (without `.schema.json`).
_SCHEMAS: dict[str, str] = {
    "content_inventory": "content_inventory.schema.json",
    "internal_link_graph": "internal_link_graph.schema.json",
    "keyword_metrics": "keyword_metrics.schema.json",
    "search_performance": "search_performance.schema.json",
    "search_evidence": "search_evidence.schema.json",
    "agent_context_pack": "agent_context_pack.schema.json",
}


def list_schemas() -> list[str]:
    """Return the logical names of every shipped schema."""

    return sorted(_SCHEMAS)


def schema_filename(name: str) -> str:
    """Map a logical schema name to its file basename."""

    try:
        return _SCHEMAS[name]
    except KeyError as exc:
        known = ", ".join(sorted(_SCHEMAS))
        raise KeyError(
            f"Unknown schema {name!r}. Known schemas: {known}."
        ) from exc


def load_schema(name: str) -> dict[str, Any]:
    """Load a schema by logical name and return it as a dict.

    Reads the JSON file packaged with this distribution. Safe to call
    repeatedly; the JSON is parsed each time so callers can mutate the
    returned dict without affecting other readers.
    """

    filename = schema_filename(name)
    text = resources.files(__package__).joinpath(filename).read_text(encoding="utf-8")
    parsed: dict[str, Any] = json.loads(text)
    return parsed


__all__ = ["list_schemas", "load_schema", "schema_filename"]
