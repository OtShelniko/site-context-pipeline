# Roadmap

This roadmap is intentionally narrow. Each milestone ships only what is
already designed and testable offline. Anything that would require a live
API, vendor SDK, or new runtime dependency stays in 0.4 or later, behind
an explicit opt-in.

The roadmap is a **direction document**, not a release schedule. Items
will land when they are ready and reviewed.

## 0.1 — current

Initial OSS extraction with the offline core. Shipped:

- **Local site inventory** — read URLs from a CSV or JSON, normalise,
  classify each page (`home`, `service`, `blog`, `category`, `landing`,
  `other`), record the rule that fired.
- **Internal link graph** — join an edge list with the inventory and
  flag commercial pages that receive no inlinks from blog posts and
  blog posts that receive at most one inlink.
- **Agent context pack** — JSON + Markdown digest aggregating
  inventory, link graph, project notes, and any provider artifacts.
- **Local CSV keyword provider (`local-csv`)** — import keyword metrics
  from any CSV with `query`/`keyword` plus optional volume,
  competition, geo, language, source URL columns. Tolerant of header
  variations (`Search Volume` ≡ `search_volume`) and number formats
  (`"1,234"` → `1234`, `"12.3%"` → `0.123`).
- **Local Search-Console-style CSV provider (`local-gsc-csv`)** —
  import per-query performance from a Google Search Console
  Performance export.
- **Provider registry** — `KEYWORD_PROVIDERS` and
  `SEARCH_PERFORMANCE_PROVIDERS` maps, plus stable error types
  (`ProviderError`, `ProviderConfigurationError`,
  `ProviderNotConfiguredError`).
- **CLI commands** — `init`, `build-inventory`, `build-link-graph`,
  `import-keywords`, `import-search-performance`, `list-providers`,
  `build-context-pack`, `inspect`.
- **Tests and CI** — 50 tests on Python 3.11/3.12 via GitHub Actions
  (ruff + pytest). Zero network access required.

## 0.2 — input adapters and configurable classification

Goal: make it easy to feed data in without hand-rolling CSVs.

- **Sitemap XML importer** ✅ *(merged in `Unreleased`)* — read one or more
  `sitemap.xml` (and sitemap-index) files into the inventory CSV format.
  Offline; no HTTP fetching.
- **Screaming Frog CSV importer** ✅ *(merged in `Unreleased`)* — accept
  the canonical Screaming Frog `internal_*.csv` and
  `*_inlinks/*_outlinks.csv` exports directly, without a manual reshape
  step. Tolerates the legacy column layout (SF v15-17).
- **Stronger configurable page classification** ✅ *(merged in
  `Unreleased`)* — `config/classifier.json` now supports priorities,
  negation patterns, and explicit URL allow-lists per page type. See
  [`docs/classifier.md`](https://github.com/OtShelniko/site-context-pipeline/blob/main/docs/classifier.md).
- **Improved context-pack templates** — make the Markdown sections
  customisable via simple template strings in
  `config/context_pack.json`. Defaults remain offline-safe and
  vendor-neutral.

## 0.3 — search evidence and offline QA

Goal: capture what the SERP looks like (without scraping it) and
provide deterministic checks over Markdown drafts.

- **Search evidence provider interface** ✅ *(merged in `Unreleased`)* —
  finalised the `SearchEvidenceProvider` abstract base.
- **Local SERP evidence CSV importer** ✅ *(merged in `Unreleased`)* —
  read top-N organic rows for a query from a hand-curated CSV. No
  live SERP scraping.
- **Deterministic content QA module** ✅ *(merged in `Unreleased`)* —
  offline checks over a Markdown
  draft (keyphrase distribution, internal-link sanity, slug shape,
  heading hierarchy, missing alt text). No LLM involvement.

## 0.4 — optional live adapters

Goal: bridge to real APIs **without** making them required. Each item
ships behind an optional extra (`pip install
site-context-pipeline[<extra>]`); credentials live in env or local
`.env` files and never in artifacts.

- **Optional live Google Ads Keyword Planner adapter** ✅ *(landed)* —
  replaces the `google-ads` stub with a real `KeywordPlanIdeaService`
  call behind the `[google-ads]` extra. Returns `not_configured` when
  the extra or credentials are missing; never imports the SDK at
  module load.
- **Optional live Google Search Console adapter** ✅ *(landed)* —
  replaces the `google-search-console` stub with a real Search
  Analytics API call behind the `[gsc]` extra. Returns
  `not_configured` when the extra or credentials are missing; never
  imports the client libraries at module load.
- **Optional third-party / regional keyword providers** — community
  adapters for the data sources their authors use. The toolkit will
  accept a Yandex Wordstat adapter, a DataForSEO adapter, an Ahrefs
  adapter, a Semrush adapter, a SerpApi adapter, etc., on the same
  terms as Google: optional extra, structured `not_configured` when
  unconfigured, no impact on the base install.
- **Provider config docs** — per-provider configuration schemas,
  credential setup walk-throughs, rate-limit guidance.

## Items intentionally not on the roadmap

- A built-in "write me an article" command.
- Bulk content generation across many sites in one run.
- Anything that touches a live site without an explicit opt-in flag.
- Hardcoded support for any single search vendor in the core.
  Vendors are providers; providers are optional.
- Background daemons, schedulers, or always-on services. The toolkit
  is and will remain a CLI you invoke from a script or a CI job.
