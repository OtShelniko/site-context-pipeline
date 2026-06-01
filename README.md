# site-context-pipeline

> Convert website crawls, URL inventories, and editorial notes into
> structured **context packs** for human-reviewed, LLM-assisted content
> workflows.

[![CI](https://github.com/OtShelniko/site-context-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/OtShelniko/site-context-pipeline/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/OtShelniko/site-context-pipeline/graph/badge.svg)](https://codecov.io/gh/OtShelniko/site-context-pipeline)
[![PyPI](https://img.shields.io/pypi/v/site-context-pipeline.svg)](https://pypi.org/project/site-context-pipeline/)
[![Python versions](https://img.shields.io/pypi/pyversions/site-context-pipeline.svg)](https://pypi.org/project/site-context-pipeline/)
[![Downloads](https://static.pepy.tech/badge/site-context-pipeline/month)](https://pepy.tech/project/site-context-pipeline)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

`site-context-pipeline` is a small, dependency-free Python CLI that turns
the boring-but-essential facts about a website into a stable, machine- and
human-readable digest. The digest is the artifact you hand to a language
model (or to a human writer) before they touch a brief or a draft.

The 0.x core is intentionally small: it reads a CSV/JSON URL list,
classifies pages, builds a simple internal-link graph, optionally folds
in keyword and search-performance data from local CSV exports, and emits
an aggregated **agent context pack** plus a **content opportunities**
report. The **core schemas, artifacts, and pipeline are vendor-neutral**
and have **no required external API dependency**. Optional provider
adapters may carry vendor-specific names (e.g. `google-ads`,
`google-search-console`) — see [Provider philosophy](#provider-philosophy)
and [`docs/providers.md`](./docs/providers.md) for the rules.

> **Documentation:** the full docs site lives at
> **<https://otshelniko.github.io/site-context-pipeline/>**, with
> [Tutorial](./docs/tutorial.md) ·
> [Recipes](./docs/recipes.md) ·
> [How this compares](./docs/comparison.md) ·
> [Demo clients](./docs/demo-clients.md) ·
> [Architecture](./docs/architecture.md) ·
> [Providers](./docs/providers.md) ·
> [Provider reference](./docs/provider-reference.md) ·
> [Artifacts](./docs/artifacts.md) ·
> [Classifier](./docs/classifier.md) ·
> [QA](./docs/qa.md) ·
> [JSON Schemas](./docs/schemas.md) ·
> [Roadmap](./ROADMAP.md) ·
> [Changelog](./CHANGELOG.md) also viewable here on GitHub.

## What you get out

The pipeline emits a single Markdown digest plus a JSON twin. Below is
a real, trimmed excerpt of `output/agent_context_pack.md` produced
from the synthetic `examples/demo-client/` fixtures — no hand-editing,
no LLM, fully reproducible from the workspace.

```markdown
# Agent context pack — preview

## Summary

- page_count: 8
- edge_count: 6
- keyword_metrics_count: 6
- search_performance_rows: 6

### Page-type breakdown

- blog: 2
- home: 1
- landing: 1
- service: 3
- other: 1

## Opportunities

### Top keyword opportunities

- local delivery service — volume=3600 — source: local-csv
- delivery cost guide   — volume=2400 — source: local-csv
- local delivery planning — volume=1900 — source: local-csv

### Pages with impressions but weak CTR

- delivery cost guide → /blog/delivery-cost-guide/
  impressions=2200, ctr=0.82%, position=18.6

### Pages with rankings but weak internal support

- /blog/how-to-plan-delivery/ — best position 12.4
  for "local delivery planning", impressions=2490, zero_inlinks

## What competitors do

### delivery cost guide

- #1 How Delivery Costs Work — competitor-a.example  (article)
- #2 Delivery Pricing Calculator — competitor-b.example (calculator)
- #3 Cost of Last-Mile Delivery — competitor-d.example (article)
```

The full pack also includes per-page-type listings, classification
reasons, the project-notes block, and a `sources` map that records
which artifact every fact came from. Hand this to a reviewer or to an
LLM and they can produce a brief without guessing what your site
already covers.

## What this project is

- A **CLI toolkit** for assembling structured context about a single site.
- A **deterministic pipeline**: same input, same output. Every artifact
  records where its facts came from.
- A **safe foundation** for LLM-assisted workflows: humans (and models)
  consume the pack, but the pack is built without calling an LLM.
- An **opinionated layout**: every site lives in its own
  `clients/<name>/{input,config,data,output,logs}` workspace, so several
  sites can coexist without contaminating each other.

## What this project is **not**

- It is **not a one-click SEO article generator**. There is no built-in
  prompt that says "write me a 1500-word article ranked #1 on Google."
- It is **not a Yandex-only or Google-only tool**. The base package
  works without any search vendor at all.
- It is **not a crawler**. You bring a CSV of URLs (export from
  Screaming Frog, your CMS, a sitemap parser, etc.). 0.x does not fetch
  pages.
- It is **not a SERP scraper, keyword scraper, or link-building automator**.
- It is **not a CMS publisher**. Outputs are local files; pushing them to
  WordPress or anywhere else is your responsibility.
- It is **not a black-hat SEO toolkit**. If your goal is to generate
  doorway pages or scaled spam, this isn't your tool.

## Why structured context matters

Asking an LLM "write a blog post about local delivery" without context
produces text that:

- duplicates pages already on your site,
- targets keywords that don't match your real services,
- recommends links that don't exist,
- invents facts that conflict with your live copy.

Hand the same model a stable digest of the site (page inventory, link
graph, classification reasons, project notes, real keyword volumes,
real Search-Console performance) and the failure modes shrink. You also
get something every author and reviewer needs: an auditable trail
showing *where each claim came from*. The pack is designed for human
review first; LLM consumption is a side benefit.

## Installation

Requires **Python ≥ 3.11**. The core has zero runtime dependencies.

```bash
pip install site-context-pipeline
```

Or, from a clone:

```bash
git clone https://github.com/OtShelniko/site-context-pipeline.git
cd site-context-pipeline
pip install -e ".[dev]"
```

## Quickstart

The shipped demo uses synthetic `example.com` data — no real sites or
keywords.

```bash
# 1. Initialise an empty client workspace.
site-context-pipeline init --client demo --write

# 2. Build the inventory from a URL CSV.
site-context-pipeline build-inventory \
    --client demo \
    --source examples/demo-client/input/urls.csv \
    --write

# 2a. (alternative) Or feed a sitemap.xml — same command, different format.
#     Auto-detection picks "sitemap" from the .xml extension; --format
#     sitemap forces it explicitly.
# site-context-pipeline build-inventory \
#     --client demo \
#     --source path/to/sitemap.xml \
#     --format sitemap \
#     --write

# 3. Build the internal link graph from an edge CSV.
site-context-pipeline build-link-graph \
    --client demo \
    --source examples/demo-client/input/links.csv \
    --write

# 4. (optional) Import keyword volume data from a local CSV.
site-context-pipeline import-keywords \
    --client demo \
    --provider local-csv \
    --source examples/demo-client/input/keyword_metrics.csv \
    --write

# 5. (optional) Import per-query performance from a Search-Console-style CSV.
site-context-pipeline import-search-performance \
    --client demo \
    --provider local-gsc-csv \
    --source examples/demo-client/input/search_console.csv \
    --write

# 6. Aggregate everything into the agent context pack.
site-context-pipeline build-context-pack --client demo --write

# 7. See what's there.
site-context-pipeline inspect --client demo
```

After step 6 you will have:

```
clients/demo/
├── data/
│   ├── content_inventory.json
│   ├── internal_link_graph.json
│   ├── keyword_metrics.json          # only if step 4 ran
│   └── search_performance.json       # only if step 5 ran
└── output/
    ├── agent_context_pack.json
    ├── agent_context_pack.md
    └── content_opportunities.md
```

Steps 4 and 5 are optional. The context pack works without them; if both
artifacts are missing the pack records a clear `missing_keyword_data`
warning so reviewers know the demand and performance sections were not
filled in.

## CLI commands

Every command takes `--client <id>` and an optional `--workspace <path>`
(defaults to the current directory). Every command supports `--write`;
without it, the command runs as a dry-run and prints the planned writes.

| Command | What it does | Reads | Writes |
|---|---|---|---|
| `init` | Creates the `clients/<id>/` directory tree and seed files. | — | `clients/<id>/{input,config,data,output,logs}/`, `input/{urls.csv,links.csv,project.md}` placeholders |
| `build-inventory --source PATH` | Normalises URLs, classifies each as `home`/`service`/`blog`/`category`/`landing`/`other`, records the rule that fired. Accepts CSV, JSON, sitemap XML, or Screaming Frog `internal_*.csv` via `--format auto\|csv\|json\|sitemap\|screaming-frog`. | CSV, JSON, sitemap.xml, or Screaming Frog inventory CSV | `data/content_inventory.json` |
| `build-link-graph --source PATH` | Joins an edge list with the inventory; tags commercial pages with low blog inlinks. Accepts CSV, JSON, or Screaming Frog `all_inlinks.csv` via `--format`. | CSV, JSON, or Screaming Frog link CSV | `data/internal_link_graph.json` |
| `import-keywords --provider NAME --source PATH` | Reads keyword metrics from a provider into a normalised artifact. | provider-specific | `data/keyword_metrics.json` |
| `import-search-performance --provider NAME --source PATH` | Reads per-query performance data into a normalised artifact. | provider-specific | `data/search_performance.json` |
| `list-providers` | Lists available keyword and search-performance providers and whether each is live in this release. | — | nothing |
| `build-context-pack` | Aggregates inventory, link graph, project notes, keywords, and performance into one digest. No LLM, no network. | The JSON artifacts above + project notes | `output/agent_context_pack.json`, `output/agent_context_pack.md`, `output/content_opportunities.md` |
| `qa-draft --draft PATH` | Runs deterministic QA checks over a Markdown draft (heading hierarchy, keyphrase density, alt text, link sanity, slug). Exits non-zero on any red finding so CI can gate on it. | Markdown draft + (optional) inventory | `output/qa_reports/<slug>.qa.json` (with `--write`) |
| `inspect` | Reports which expected files exist. Useful for CI scripts. | The whole workspace | nothing |

All commands print one JSON document on stdout, so you can pipe them.

> **Looking for a longer walkthrough?** See
> [`docs/tutorial.md`](./docs/tutorial.md) — a 10-minute end-to-end
> tutorial that goes from "I have a sitemap" to a finished context
> pack, with explanations for every step.

## Provider philosophy

Providers are how external data — keyword volume, search performance,
SERP rows — gets into the pipeline. The toolkit follows four rules:

1. **Providers are optional.** The base package works without any of
   them. The core artifacts (inventory, link graph, context pack) never
   touch the network.
2. **Providers convert external data into normalised local artifacts.**
   A provider's job is to read a CSV (today) or call a vendor API (in
   the future) and emit `data/keyword_metrics.json` or
   `data/search_performance.json` in a stable, vendor-independent
   shape. Every row carries a `source` field so you can tell which
   provider produced it.
3. **The core pipeline reads normalised artifacts only.** Once a
   provider has written the artifact, no other code in the pipeline
   cares which provider produced it. This prevents vendor lock-in and
   keeps the context pack reproducible from a single workspace
   directory.
4. **Vendor-specific names live in providers, never in the core.**
   The schemas, artifact field names, and CLI core commands stay
   vendor-neutral. A provider *identifier* like `google-ads` may be
   vendor-specific by design — that is what tells the user which API
   the future live adapter will call. Vendor-specific providers must
   remain optional adapters and never become core dependencies.

Listing in this release:

| Provider name | Kind | Status | Notes |
|---|---|---|---|
| `local-csv` | keyword | **live** | Read keyword metrics from any local CSV (Google Ads export, Ahrefs / Semrush export, hand-curated research). Offline. |
| `google-ads` | keyword | **live (opt-in)** | Live Google Ads Keyword Planner ideas. Needs `pip install "site-context-pipeline[google-ads]"` and credentials via `--config`; returns `not_configured` otherwise. |
| `local-gsc-csv` | search_performance | **live** | Read per-query performance from a Google Search Console Performance CSV export. Offline. |
| `google-search-console` | search_performance | **live (opt-in)** | Live Search Console Search Analytics. Needs `pip install "site-context-pipeline[gsc]"` and credentials via `--config`; returns `not_configured` otherwise. |
| `local-serp-csv` | search_evidence | **live** | Read hand-curated SERP rows (query, rank, title, url, snippet, page_type) from a local CSV. Offline; the toolkit does not scrape SERPs. |

## Why not hardcode Yandex or Google?

- Different markets use different search engines. Yandex still leads in
  some regions; Google leads in others; Baidu, Naver, DuckDuckGo, and
  vertical search matter for specific niches. Hardcoding any single
  vendor would push the toolkit toward one market and against another.
- OSS users should be able to **bring their own data**. The pipeline
  cannot tell whether your `keyword_metrics.csv` came from Google Ads,
  Yandex Wordstat, Ahrefs, Semrush, an internal database, or a
  hand-curated spreadsheet — and it does not need to. Every row is
  treated the same way.
- **Local CSV imports are the stable baseline.** Vendors change auth
  flows, schemas, and access tiers. Files do not. Building the data
  contract around CSV/JSON keeps the pipeline working when an API
  changes overnight.
- **API adapters should never be required for core usage.** When a live
  adapter ships, it lives behind an optional extra (e.g.
  `pip install site-context-pipeline[gsc]`) and the rest of the
  pipeline stays dependency-free.

If you need a Yandex-specific or Google-specific adapter, add it as a
new provider that produces the same `KeywordMetric` rows the rest of
the toolkit already understands. No core changes required.

## Demo client

Run `site-context-pipeline init --client demo --write` to start a fresh
workspace, or use the synthetic fixtures in `examples/demo-client/`
directly. The fixtures contain:

- 8 pages on a fictional `example.com` (home, services, blog posts,
  pricing, about).
- 6 internal links between them.
- 6 fake search queries with synthetic volumes (`local delivery
  planning`, `delivery cost guide`, `same day delivery checklist`,
  `business delivery pricing`, `warehouse delivery service`, `local
  delivery service`).
- 6 fake Search-Console rows with impressions, clicks, CTR, and average
  position.
- A short `project.md` describing the imaginary business.
- `config/commercial_urls.json` promoting one URL to `landing`.
- `config/classifier.json` showing how to override the default
  page-pattern rules.

The fixtures are intentionally tiny and language-neutral. They are not
copied from any real site or client.

## Generated artifacts

### `data/content_inventory.json`

A list of objects, one per page:

```json
{
  "url": "https://example.com/blog/how-to-plan-delivery/",
  "path": "/blog/how-to-plan-delivery/",
  "page_type": "blog",
  "classification_reason": "matched_pattern:*/blog/*",
  "title": "How to plan a delivery",
  "h1": "How to plan a delivery",
  "status_code": 200,
  "word_count": 1100,
  "inlinks_count": 2,
  "outlinks_count": 3,
  "source": "csv"
}
```

### `data/internal_link_graph.json`

```json
{
  "nodes": [{"url": "...", "page_type": "service", "blog_inlink_count": 1, "is_commercial_target": true, "...": "..."}],
  "edges": [{"source_url": "...", "target_url": "...", "anchor_text": "..."}],
  "commercial_pages_low_blog_inlinks": [],
  "blog_pages_low_inlinks": [],
  "warnings": []
}
```

### `data/keyword_metrics.json` *(optional)*

Produced by `import-keywords`. Every row carries a `source` field
identifying the provider that wrote it.

```json
{
  "schema_version": 1,
  "provider": "local-csv",
  "items_count": 6,
  "metadata": {"source_path": "examples/demo-client/input/keyword_metrics.csv", "row_count": 6, "items_count": 6},
  "warnings": [],
  "items": [
    {
      "query": "local delivery service",
      "source": "local-csv",
      "avg_monthly_searches": 3600,
      "competition": "HIGH",
      "geo": "US",
      "language": "en",
      "source_url": "https://example.com/services/local-delivery/",
      "raw": {}
    }
  ]
}
```

### `data/search_performance.json` *(optional)*

Produced by `import-search-performance`. Same shape as
`keyword_metrics.json` but the rows usually fill `impressions`,
`clicks`, `ctr`, and `position` instead of `avg_monthly_searches`.

### `output/agent_context_pack.json`

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-31T00:00:00+00:00",
  "client": "demo",
  "summary": {
    "page_count": 8,
    "edge_count": 6,
    "node_count": 8,
    "keyword_metrics_count": 6,
    "search_performance_rows": 6,
    "page_type_counts": {"blog": 2, "home": 1, "...": "..."}
  },
  "classification": {"reasons": {"...": "..."}},
  "pages": {"home": [], "blog": [], "...": []},
  "opportunities": {
    "commercial_pages_low_blog_inlinks": [],
    "blog_pages_low_inlinks": [],
    "top_keywords": [],
    "weak_ctr_pages": [],
    "ranked_but_unsupported": []
  },
  "search_performance_summary": {"rows": 6, "total_clicks": 174, "total_impressions": 8620, "average_ctr": 0.0218, "average_position": 13.62},
  "providers": {"keyword_metrics": {}, "search_performance": {}},
  "project_notes": "...",
  "sources": {"...": "..."},
  "warnings": []
}
```

`output/agent_context_pack.md` is the same content as a Markdown
document, with sections for top keyword opportunities, weak-CTR pages,
and pages that already rank but receive no internal support.

`output/content_opportunities.md` is a deterministic shortlist of gaps:
commercial pages without blog inlinks, orphan blog posts, weak-CTR
queries, and ranked-but-unsupported URLs. It is a prompt for human
review, not a ranking.

## Provider input formats

### `local-csv` (keyword data)

Recognised columns (case-insensitive, `_`/`-`/space treated as
equivalent — `Search Volume`, `search_volume`, and `search-volume` all
match):

| Required (one of) | Optional |
|---|---|
| `query`, `keyword`, `search_term` | `avg_monthly_searches` (`search_volume`, `monthly_searches`, `volume`, `searches`) |
| | `impressions`, `clicks`, `ctr`, `position` (`average_position`, `rank`) |
| | `competition`, `locale`, `geo` (`country`, `location`), `language`, `source_url` |

Numeric values handle thousand separators (`"1,234"` → `1234`) and CTR
percentages (`"12.3%"` → `0.123`). Unknown columns are preserved in
each row's `raw` dict so no information is lost.

### `local-gsc-csv` (search-performance data)

Tolerant of any CSV that uses Google Search Console-like headers. The
same column-normalisation rules apply.

| Required | Optional |
|---|---|
| `query` (also `top queries`, `search_term`) | `page` / `landing_page` / `url`, `clicks`, `impressions`, `ctr`, `position`, `country`, `device`, `date` |

`device` and `date` are preserved on each row's `raw` dict so future
filters can use them.

## Dry-run / write principle

Every command runs as a **dry-run by default**. The exit code is `0`, the
JSON payload lists `planned_writes`, but nothing is created on disk.
Re-run with `--write` to materialise the artifacts. This makes the
pipeline safe to integrate into CI, code reviews, and PR previews.

## Data safety

This toolkit is designed for **public, source-backed processing**. A few
ground rules:

- **Use synthetic data in public examples.** Never check real client
  domains, keyword lists, briefs, or scraped HTML into a public repo.
  See `examples/demo-client/` for the bar.
- **Keep secrets out of the workspace.** No API keys are needed for the
  0.x core. When live network adapters are added (see Roadmap), they
  will read keys from environment variables and `.env` files that are
  gitignored; keys must never be written into artifacts.
- **Treat input files as untrusted data.** The CLI never executes
  anything from your CSV/JSON; it only reads fields it knows about.
  Unknown columns are preserved in `raw` but never executed.
- **Path traversal is rejected.** Client identifiers are validated
  against a strict pattern; `--client ../etc` exits with an error.

If you find a security issue, please follow [`SECURITY.md`](./SECURITY.md).

## Architecture overview

```
┌──────────────────────┐     ┌─────────────────────────┐
│ input/urls.csv       │ ──► │ inventory.py            │
│ input/links.csv      │     │  classify URLs          │
│ input/project.md     │     │  build content_inventory│
└──────────────────────┘     └────────────┬────────────┘
                                          │
                                          ▼
                             ┌─────────────────────────┐
                             │ link_graph.py           │
                             │  join inventory + edges │
                             │  flag opportunities     │
                             └────────────┬────────────┘
                                          │
   ┌──────────────────────┐               │
   │ keyword_metrics.csv  │ ──┐           │
   │ search_console.csv   │ ──┤           │
   │ ...                  │   │           │
   └──────────────────────┘   ▼           │
                          ┌─────────────────────────┐
                          │ providers/              │
                          │  local-csv              │
                          │  local-gsc-csv          │
                          │  google-ads (stub)      │
                          │  google-search-console  │
                          │      (stub)             │
                          └────────────┬────────────┘
                                       │ data/keyword_metrics.json
                                       │ data/search_performance.json
                                       ▼
                             ┌─────────────────────────┐
                             │ context_pack.py         │
                             │  aggregate everything   │
                             │  emit pack.{json,md}    │
                             └─────────────────────────┘
```

The pipeline is intentionally one-way: each step reads from the previous
step's artifact on disk. This means you can run any step independently
and re-run cheaply when an upstream input changes.

## Roadmap

The 0.x core is offline-only on purpose. Future versions will add
**optional adapters** behind explicit opt-in flags and `[extras]`. The
shape these will take:

- **`crawl`** adapter — wrap an external crawler (SiteOne, Screaming Frog,
  a sitemap parser) so users do not have to assemble the input CSV by
  hand. The adapter must be opt-in and never crawl by default.
- **Live keyword providers** — Google Ads Keyword Planner, plus future
  adapters for any vendor (DataForSEO, Yandex Wordstat, SerpApi,
  Ahrefs, Semrush) where the user has credentials. Each lives behind
  its own optional extra and produces the same normalised
  `KeywordMetric` rows.
- **Live search-performance providers** — Google Search Console
  Search Analytics API, plus future adapters for any equivalent
  service. Same opt-in pattern.
- **Search evidence providers** — read top-N organic rows for a query
  from a search API. Behind an explicit `--allow-external` flag and
  one of several pluggable backends.
- **`llm-brief`** adapter — feed the context pack to an LLM to produce a
  *brief* (not a draft). Output must be reviewable JSON, not free-form
  prose, and every claim must cite a source field from the pack.
- **`yoast-style-qa`** module — deterministic, offline content QA over
  Markdown drafts (keyphrase distribution, internal-link sanity, slug
  checks). No LLM involvement.
- **`schema-org`** module — generate JSON-LD `Article` / `FAQPage` /
  `BreadcrumbList` from a draft + the context pack. Validation against
  Google's required-property checklist.
- **WordPress publish** — explicitly out of scope until everything above
  is stable. When added, it will be a separate package.

Items intentionally **not** on the roadmap:

- A built-in "write me an article" command.
- Bulk content generation across many sites in one run.
- Anything that touches a live site without an explicit opt-in flag.
- Hardcoded support for any single search vendor in the core. Vendors
  are providers; providers are optional.

## Using this with OpenAI Codex (or any coding assistant)

The agent context pack is designed to be a stable input for a coding or
content assistant. A typical loop:

1. Run the pipeline locally and review `agent_context_pack.md` by eye.
2. Paste the pack (or attach `agent_context_pack.json`) into the
   assistant's context window.
3. Ask the assistant to draft a brief, an outline, or a code change that
   *cites the pack's `sources` and `pages` fields*.
4. Verify the assistant's references against the live site before
   acting on the output.

The pack's `schema_version` field lets you write a small validator in
your own codebase to refuse drafts that drift from the agreed schema.

## Development

```bash
git clone <this repo>
cd site-context-pipeline
python -m venv .venv
. .venv/Scripts/activate     # Windows
pip install -e ".[dev]"
ruff check .
pytest
```

CI runs the same commands on Python 3.11 and 3.12.

## License

[MIT](./LICENSE).

## Code of conduct

By participating you agree to the [Contributor Covenant](./CODE_OF_CONDUCT.md).
