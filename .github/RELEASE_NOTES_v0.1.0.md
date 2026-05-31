# v0.1.0 — initial public release

`site-context-pipeline` is a small, dependency-free Python CLI that turns
website inventories, internal-link data, and local keyword/search exports
into a structured **agent context pack** for human-reviewed,
LLM-assisted content workflows.

## Highlights

- **Offline core.** Inventory, link graph, and context pack run with zero
  runtime dependencies. No live network calls, no API keys required.
- **Provider abstraction.** Keyword and search-performance data enter the
  pipeline through pluggable providers; the core never knows which vendor
  produced a row.
  - `local-csv` — keyword metrics from any CSV (Ads/Ahrefs/Semrush/manual).
  - `local-gsc-csv` — Google Search Console-style Performance CSV.
  - `google-ads`, `google-search-console` — stubs that return a clean
    `not_configured` result, with live adapters scheduled for 0.4.
- **Deterministic context pack** with optional sections for top keyword
  opportunities, weak-CTR pages, and ranked-but-unsupported pages.
- **Dry-run by default.** Every CLI verb plans writes; `--write` materialises.
- **Honest documentation.** Architecture, providers, artifacts, and roadmap
  docs ship alongside the package.

## Install

```bash
pip install -e ".[dev]"
```

(PyPI release planned for 0.2.x once the input adapters land.)

## Quickstart

```bash
site-context-pipeline init --client demo --write
site-context-pipeline build-inventory --client demo \
    --source examples/demo-client/input/urls.csv --write
site-context-pipeline build-link-graph --client demo \
    --source examples/demo-client/input/links.csv --write
site-context-pipeline import-keywords --client demo \
    --provider local-csv \
    --source examples/demo-client/input/keyword_metrics.csv --write
site-context-pipeline import-search-performance --client demo \
    --provider local-gsc-csv \
    --source examples/demo-client/input/search_console.csv --write
site-context-pipeline build-context-pack --client demo --write
```

Output lands at `clients/demo/output/agent_context_pack.{json,md}` and
`clients/demo/output/content_opportunities.md`.

## What's not in 0.1

- No live API adapters yet (Google Ads / Search Console land in 0.4).
- No sitemap or Screaming Frog importers (0.2).
- No deterministic content QA module (0.3).

See [ROADMAP.md](https://github.com/OtShelniko/site-context-pipeline/blob/main/ROADMAP.md)
for the full plan.

## Verified

- 50 tests passing on Python 3.11 and 3.12 (GitHub Actions).
- `ruff check .` clean.

## License

MIT.
