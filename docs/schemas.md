# JSON Schemas

Every public artifact this toolkit emits has a corresponding
[JSON Schema 2020-12](https://json-schema.org/draft/2020-12) document.
The schemas are the contract between the pipeline and any downstream
consumer — an LLM agent, a CI pipeline, a custom dashboard, a data
warehouse loader, or a hand-written script that reads
`agent_context_pack.json`.

The schemas ship with the wheel under
`site_context_pipeline.json_schema` and are loaded via a tiny stdlib
helper:

```python
from site_context_pipeline.json_schema import list_schemas, load_schema

print(list_schemas())
schema = load_schema("agent_context_pack")
```

The base install does **not** depend on `jsonschema`. Loading the
schema is just `json.loads()` from the packaged file. Validation is
left to whichever validator the consumer prefers
(`jsonschema`, `fastjsonschema`, `check-jsonschema`, etc.).

## Why schemas

- **Stable contract for LLM consumers.** When you hand
  `agent_context_pack.json` to a model and ask it to produce a brief,
  the schema is what guarantees your post-processor can read the
  output without surprises across pipeline upgrades.
- **CI gating.** Drop a `check-jsonschema` step into your downstream
  pipeline and fail fast when a contract violation slips through.
- **Self-documentation.** Every field has a `description`; reading the
  schema is the fastest way to learn what the pipeline produces.
- **Static analysis.** Tools like
  [`datamodel-code-generator`](https://github.com/koxudaxi/datamodel-code-generator)
  can turn the schemas into typed Pydantic models, Go structs, or
  TypeScript interfaces.

## Available schemas

| Logical name | File | Describes |
|---|---|---|
| `content_inventory` | `content_inventory.schema.json` | `data/content_inventory.json` |
| `internal_link_graph` | `internal_link_graph.schema.json` | `data/internal_link_graph.json` |
| `keyword_metrics` | `keyword_metrics.schema.json` | `data/keyword_metrics.json` |
| `search_performance` | `search_performance.schema.json` | `data/search_performance.json` |
| `search_evidence` | `search_evidence.schema.json` | `data/search_evidence.json` |
| `agent_context_pack` | `agent_context_pack.schema.json` | `output/agent_context_pack.json` |

Every schema has:

- a stable `$id` of the form
  `https://otshelniko.github.io/site-context-pipeline/schemas/<name>.schema.json`
- `$schema: https://json-schema.org/draft/2020-12/schema`
- a `title` that matches the artifact's filename
- a `description` explaining when and how the artifact is produced
- inline `description` fields on every interesting property

## Cross-schema references

`internal_link_graph.schema.json` and `agent_context_pack.schema.json`
reference page-type and inventory definitions from
`content_inventory.schema.json` via relative `$ref`s. To resolve those
references during validation, register every shipped schema in your
validator's registry:

```python
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from site_context_pipeline.json_schema import list_schemas, load_schema, schema_filename

registry = Registry()
for name in list_schemas():
    doc = load_schema(name)
    res = Resource.from_contents(doc)
    registry = registry.with_resource(uri=schema_filename(name), resource=res)
    registry = registry.with_resource(uri=doc["$id"], resource=res)

validator = Draft202012Validator(load_schema("agent_context_pack"), registry=registry)

import json
pack = json.loads(open("clients/demo/output/agent_context_pack.json").read())
errors = sorted(validator.iter_errors(pack), key=lambda e: list(e.absolute_path))
assert not errors, errors
```

This is exactly the pattern the project's own test suite uses (see
`tests/test_json_schemas.py`).

## Versioning

Each artifact carries a `schema_version` integer field (currently `1`).

- **Backward-compatible additions** (a new optional field, a new
  enumerated `page_type`, a new opportunity bucket) **do not** bump
  `schema_version`. The schemas use `additionalProperties: true` so
  validators built today will still pass tomorrow's artifacts.
- **Breaking changes** (a renamed field, a removed field, a tightened
  type) bump `schema_version` to `2`, and the change lands in a
  minor-version release of the package with a CHANGELOG entry.

## Validating in CI

The simplest gate, using the standalone
[`check-jsonschema`](https://github.com/python-jsonschema/check-jsonschema)
CLI:

```bash
pip install check-jsonschema
check-jsonschema \
    --schemafile https://otshelniko.github.io/site-context-pipeline/schemas/agent_context_pack.schema.json \
    clients/*/output/agent_context_pack.json
```

For pipelines that already install this package, prefer the in-process
validator from `site_context_pipeline.json_schema` — it never reaches
the network and works in air-gapped CI runners.

## Generating typed models

If you want typed Python models for downstream code, point
`datamodel-code-generator` at the schemas:

```bash
pip install datamodel-code-generator
python -c "from site_context_pipeline.json_schema import load_schema; \
    import json; json.dump(load_schema('agent_context_pack'), open('pack.json', 'w'))"
datamodel-codegen --input pack.json --output pack_models.py
```

The same trick works for TypeScript via `json-schema-to-typescript`,
for Go via `quicktype`, etc. The schemas are the canonical contract;
language-specific bindings are downstream concerns and out of scope
for this project.
