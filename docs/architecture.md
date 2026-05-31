# Architecture

`site-context-pipeline` is a one-way pipeline that turns local input
files into local output files. It does not run as a service, does not
hold state between commands, and never reaches the network from its
core code. The intended deployment is a developer's laptop or a CI
runner.

## High-level flow

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Local inputs     │ ──► │ Providers        │ ──► │ Normalised data  │
│ (CSV / JSON / MD)│     │ (optional)       │     │ artifacts (JSON) │
└──────────────────┘     └──────────────────┘     └────────┬─────────┘
                                                           │
                                                           ▼
                                                  ┌──────────────────┐
                                                  │ Context pack     │
                                                  │ (JSON + Markdown)│
                                                  └────────┬─────────┘
                                                           │
                                                           ▼
                                            Human review → downstream
                                            LLM-assisted workflows
```

Every box on the left is a file the user owns. Every box in the middle
is plain Python on plain dicts. The right-hand side is also files —
JSON and Markdown — that any tool can read.

## Components

```
src/site_context_pipeline/
├── cli.py                 argparse entry point; one JSON payload per command
├── clients.py             ClientPaths, init_client, JSON I/O helpers
├── inventory.py           classify URLs into page types, write content_inventory.json
├── link_graph.py          join inventory + edges, write internal_link_graph.json
├── context_pack.py        aggregate everything → agent_context_pack.{json,md}
├── markdown.py            tiny Markdown rendering helpers (no third-party deps)
├── schemas.py             dataclasses (InventoryItem, LinkNode, KeywordMetric, ...)
└── providers/
    ├── base.py            abstract base classes + error types + result helpers
    ├── registry.py        KEYWORD_PROVIDERS, SEARCH_PERFORMANCE_PROVIDERS
    ├── local_keyword_csv.py        live, offline
    ├── local_search_console_csv.py live, offline
    ├── google_ads_keyword_planner.py        stub → not_configured
    └── google_search_console.py             stub → not_configured
```

The `providers/` package is the only place the toolkit allows
vendor-specific code. Everything outside `providers/` reads and writes
generic shapes (`InventoryItem`, `LinkNode`, `KeywordMetric`) and never
mentions a search vendor.

## Why a one-way pipeline?

The data flow goes from inputs to outputs and never loops back. This is
deliberate:

- **Re-runnable.** If an upstream input changes, the user re-runs the
  affected step. No state to invalidate.
- **Composable.** Each step's output is a file the next step reads.
  Users can replace any step with a script of their own as long as it
  emits the documented JSON shape.
- **Auditable.** Every artifact carries a `source` or
  `classification_reason` field so a reviewer can trace a fact back to
  the file that produced it.
- **Test-friendly.** Tests run each step against a `tmp_path` workspace
  and check the generated files. No mocks for external services
  because there are no external services.

## Vendor neutrality

The pipeline is built around a hard rule: the **core does not know
which vendor produced the data**.

This works because:

1. **Providers normalise external data into local files.** A provider
   reads its source (today: a CSV; tomorrow: a vendor API) and emits a
   `ProviderResult` whose `items` are generic `KeywordMetric` rows.
   The CLI persists that to `data/keyword_metrics.json` or
   `data/search_performance.json`.
2. **`context_pack.py` reads normalised artifacts only.** It opens
   `data/keyword_metrics.json` and treats every row as data. It does
   not branch on `item["source"]`. It does not import any provider.
   It does not even need the providers package on the import path to
   run.
3. **Vendor-specific names live in providers, never in the core.**
   The schemas, the CLI verbs (`build-context-pack`, `inspect`,
   `import-keywords`, `list-providers`), the artifact filenames
   (`keyword_metrics.json`, `search_performance.json`) and the field
   names (`avg_monthly_searches`, `impressions`, `clicks`, `ctr`,
   `position`) are all vendor-neutral. A provider's *identifier* like
   `google-ads` may be vendor-specific by design — that is what tells
   the user which API the future live adapter will call.

The result: swapping `google-ads` for a hypothetical Yandex Wordstat
adapter, or for a community DataForSEO adapter, is a one-file change in
`providers/`. Nothing in the core needs to move.

## Process model

Every CLI command:

1. Resolves the workspace path and the client identifier (validating
   the latter against a strict regex).
2. Calls one pure-Python builder function (e.g. `build_inventory`,
   `build_context_pack`).
3. Writes a JSON payload to stdout describing what happened. With
   `--write`, the builder also touches the filesystem; without it,
   the command is a dry run.
4. Exits with code `0` on success, `1` on failure. Failure is always
   represented in the JSON payload (`ok: false`, `errors: [...]`)
   before the process returns.

This means the CLI is safe to invoke from a CI matrix or a Makefile:
the JSON output is always parseable, even on the failure path.

## Failure modes

The pipeline distinguishes three kinds of failure:

| Kind | Example | How it surfaces |
|---|---|---|
| Malformed input | CSV path does not exist | `ProviderConfigurationError` raised inside the builder, converted to `ok: false` + a single error string by the CLI. Exit code 1. |
| Adapter not configured | `google-ads` stub called without credentials | Adapter returns a `ProviderResult` with `ok=False`, `errors=["not_configured"]`, no exception. Exit code 1. |
| Empty but legal | Inventory CSV with zero rows | Builder writes an empty `content_inventory.json` and records a warning (`inventory_missing_or_empty`). Exit code 0. |

The first two yield a non-zero exit code; the third does not. This
keeps the CLI usable in pipelines where "0 rows" is a valid outcome
(e.g. a brand-new client) but "your CSV is missing" is not.

## What is *not* in scope

- No live HTTP from the core. No live HTTP from `local-*` providers.
  Live HTTP only ever appears in optional adapters under
  `providers/`, behind an `pip install site-context-pipeline[<extra>]`
  install gate.
- No mutable global state. Every command reads and writes through
  `ClientPaths` so two clients never share data by accident.
- No long-running processes. Every command runs to completion and
  exits.
