---
title: site-context-pipeline
hide:
  - navigation
---

# site-context-pipeline

> Convert website crawls, URL inventories, and editorial notes into
> structured **context packs** for human-reviewed, LLM-assisted content
> workflows.

[![CI](https://github.com/OtShelniko/site-context-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/OtShelniko/site-context-pipeline/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/OtShelniko/site-context-pipeline/graph/badge.svg)](https://codecov.io/gh/OtShelniko/site-context-pipeline)
[![PyPI](https://img.shields.io/pypi/v/site-context-pipeline.svg)](https://pypi.org/project/site-context-pipeline/)
[![Python versions](https://img.shields.io/pypi/pyversions/site-context-pipeline.svg)](https://pypi.org/project/site-context-pipeline/)
[![Downloads](https://static.pepy.tech/badge/site-context-pipeline/month)](https://pepy.tech/project/site-context-pipeline)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/OtShelniko/site-context-pipeline/blob/main/LICENSE)

`site-context-pipeline` is a small, dependency-free Python CLI that
turns the boring-but-essential facts about a website — URL inventory,
internal link graph, keyword data, search performance — into a stable,
machine- and human-readable digest. The digest is the artifact you
hand to a language model (or to a human writer) before they touch a
brief or a draft.

## What this site covers

<div class="grid cards" markdown>

- :material-rocket-launch:{ .lg .middle } **[Tutorial](tutorial.md)**

    ---

    A 10-minute end-to-end walk-through. From a CSV (or sitemap) to a
    finished context pack, with explanations for every step.

- :material-toolbox-outline:{ .lg .middle } **[Recipes](recipes.md)**

    ---

    Concrete workflows: onboarding a new site, quarterly audits,
    pre-rebrand snapshots, gating drafts in CI, handing the pack to
    an LLM with citations.

- :material-compare:{ .lg .middle } **[How this compares](comparison.md)**

    ---

    Honest comparison vs Screaming Frog, Sitebulb, ContentKing, and
    rolling your own script. Where this toolkit is the right answer
    and where it isn't.

- :material-storefront-outline:{ .lg .middle } **[Demo clients](demo-clients.md)**

    ---

    Three synthetic workspaces shipped under `examples/`: a small
    services site, a coffee-equipment storefront, and a
    three-language docs site. Concrete starting points that exercise
    different IAs.

- :material-sitemap:{ .lg .middle } **[Architecture](architecture.md)**

    ---

    The one-way pipeline: local inputs → providers → normalised
    artifacts → context pack. Why the core never reaches the network.

- :material-database-import:{ .lg .middle } **[Providers](providers.md)**

    ---

    The provider abstraction, the four safety rules, and reference
    docs for every shipped provider (`local-csv`, `local-gsc-csv`,
    `local-serp-csv`, plus the `google-ads` and
    `google-search-console` stubs).

- :material-file-document-outline:{ .lg .middle } **[Artifacts](artifacts.md)**

    ---

    Every file the pipeline writes: when it is generated, the command
    that produces it, and whether it is required or optional.

- :material-shape:{ .lg .middle } **[Classifier](classifier.md)**

    ---

    The `config/classifier.json` schema: priorities, exclude
    patterns, allow-lists, and the warnings the inventory emits when
    a rule is invalid.

- :material-clipboard-check-outline:{ .lg .middle } **[QA](qa.md)**

    ---

    The deterministic Markdown-draft QA module. Nine offline checks,
    structured JSON output, exit code 1 on red findings so CI can
    gate on them.

- :material-shield-check-outline:{ .lg .middle } **[JSON Schemas](schemas.md)**

    ---

    Public JSON Schema 2020-12 contracts for every artifact, shipped
    with the wheel. Stable contract for LLM consumers, CI gating,
    and code generation in any language.

- :material-road:{ .lg .middle } **[Roadmap](roadmap.md)**

    ---

    What landed in 0.x and what is planned for 0.4. Every live API
    adapter is opt-in behind an extra; the base install never grows
    runtime dependencies.

- :material-history:{ .lg .middle } **[Changelog](changelog.md)**

    ---

    Every release with what was added, changed, and fixed.

</div>

## Install

```bash
pip install site-context-pipeline
```

Requires Python ≥ 3.11. The base install has zero runtime
dependencies.

## Sixty-second demo

```bash
site-context-pipeline init --client demo --write
site-context-pipeline build-inventory --client demo \
    --source examples/demo-client/input/urls.csv --write
site-context-pipeline build-link-graph --client demo \
    --source examples/demo-client/input/links.csv --write
site-context-pipeline build-context-pack --client demo --write
site-context-pipeline inspect --client demo
```

After that, `clients/demo/output/agent_context_pack.md` is the digest a
reviewer (or an LLM) reads before drafting anything.

## Project at a glance

- **Offline by default.** The 0.x core is standard-library only.
  Live API adapters, when they ship, sit behind optional extras.
- **Deterministic.** Same input, same output. Every artifact records
  where each fact came from in a `sources` map.
- **Vendor-neutral core.** Vendor-specific names (e.g. `google-ads`)
  live only on provider identifiers, never in core schemas, artifact
  field names, or CLI verbs.
- **Human-review first.** The pack is designed for a human reviewer;
  LLM consumption is a side benefit.

For the full README and contribution guide, see the
[GitHub repository](https://github.com/OtShelniko/site-context-pipeline).
