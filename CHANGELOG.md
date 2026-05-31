# Changelog

All notable changes to `site-context-pipeline` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Release drafter** workflow auto-maintains a draft release on
  every push to `main` and PR event. Categorises PRs by
  conventional-commit prefix (`feat:` / `fix:` / `docs:` / etc.) and
  by labels (`breaking`, `feature`, `fix`, `documentation`, ...).
  Bumps the draft version automatically: `breaking`/`major` →
  major, `feature`/`enhancement`/`minor` → minor, everything else →
  patch. New `.github/workflows/release-drafter.yml` and
  `.github/release-drafter.yml` config.
- **`CITATION.cff`** at the repo root makes "Cite this repository"
  appear on the GitHub project page and lets `cffconvert` render
  BibTeX, APA, RIS, etc. New
  [`docs/citation.md`](https://github.com/OtShelniko/site-context-pipeline/blob/main/docs/citation.md)
  walks through the formats. Linked from the mkdocs nav.
- **Second demo client (`examples/demo-ecommerce/`)** — synthetic
  coffee-equipment storefront on `shop.example.com` with 14 pages,
  15 internal links, deep category trees, individual product pages,
  cart/checkout, and a small editorial blog. Exercises a different
  IA than `demo-client`: product vs category disambiguation,
  `commercial_urls.json` promoting category URLs to `landing`, and a
  `*/cart/*` rule with `allow_urls` to keep specific URLs in scope.
  New `tests/test_demo_ecommerce.py` validates classification and
  pack-schema conformance end-to-end. New
  [`docs/demo-clients.md`](https://github.com/OtShelniko/site-context-pipeline/blob/main/docs/demo-clients.md)
  documents both shipped demos and a pattern for contributing more.
  Linked from the README, the mkdocs nav, and the docs index card
  grid.
- **Mypy strict mode in CI.** New `[tool.mypy]` config in
  `pyproject.toml` runs `mypy --strict` over
  `src/site_context_pipeline/` and the `lint-and-test` CI job now
  invokes it on every push and pull request. `mypy>=1.11` joined the
  `[dev]` extra. Strict mode is clean on all 22 source files.
- **Property-based tests with Hypothesis.** New
  `tests/test_property_based.py` adds 19 property tests covering URL
  normalisation, glob-style path matching, CSV header normalisation,
  integer/float/CTR parsing, and `classify_url`. Each test asserts
  invariants over randomly-generated inputs rather than concrete
  values. `hypothesis>=6.100` joined the `[dev]` extra. Test count
  rose from 147 to 166.

### Fixed

- `_first_int` now treats `inf` / `-inf` and unrepresentably-large
  floats as missing rather than raising `OverflowError`.
- `_first_ratio` (CTR parser) now treats `NaN` and `±inf` as missing
  rather than returning them as a valid ratio.
- `_first_float` now treats `NaN` and `±inf` as missing.

  All three were latent bugs surfaced by Hypothesis; example-based
  tests had not exercised those inputs.

- **"How this compares" doc** — new
  [`docs/comparison.md`](https://github.com/OtShelniko/site-context-pipeline/blob/main/docs/comparison.md)
  is an honest, opinionated comparison vs Screaming Frog, Sitebulb,
  ContentKing, Ahrefs/Semrush, and rolling-your-own scripts.
  Includes a capability matrix, where this toolkit is and isn't the
  right answer, common combinations (SF → this; GSC export → this;
  Ahrefs/Semrush export → this), and a "why not just write a
  script" section. Linked from the README, the mkdocs nav, and the
  index card grid.
- **Recipes documentation** — new
  [`docs/recipes.md`](https://github.com/OtShelniko/site-context-pipeline/blob/main/docs/recipes.md)
  ships nine end-to-end workflows that show the toolkit in real use:
  onboarding a new site, quarterly audits, finding blog posts that
  should be services, pre-rebrand link-graph snapshots, gating
  drafts in CI, handing the pack to an LLM with citations,
  side-by-side client comparison, classifier coverage audits, and
  running inside Docker. Linked from the README, the mkdocs nav, and
  the docs index card grid. No code changes.
- **Public JSON Schemas for every artifact.** New
  `site_context_pipeline.json_schema` subpackage ships six JSON
  Schema 2020-12 documents
  (`content_inventory`, `internal_link_graph`, `keyword_metrics`,
  `search_performance`, `search_evidence`, `agent_context_pack`)
  alongside a tiny stdlib loader (`list_schemas`, `load_schema`,
  `schema_filename`). The base install still has zero runtime
  dependencies. New `docs/schemas.md` documents the loader API,
  cross-schema reference resolution, CI gating with
  `check-jsonschema`, and code-gen recipes. Schemas are validated
  end-to-end against real artifacts in `tests/test_json_schemas.py`
  using `jsonschema` (dev extra). See
  [`docs/schemas.md`](https://github.com/OtShelniko/site-context-pipeline/blob/main/docs/schemas.md).

## [0.3.0] — 2026-05-31

Adds a deterministic content QA module, configurable classifier
rules, and the first search-evidence provider — closing every
0.3 roadmap item.

### Added

- **Deterministic content QA module** (#5) — new `site_context_pipeline.qa`
  module exposes `analyse_draft` / `analyse_draft_file` plus the
  `QAReport` and `QAFinding` dataclasses. Nine checks ship in 0.3:
  `single_h1`, `heading_hierarchy`, `keyphrase_in_h1`,
  `keyphrase_density`, `intro_length`, `competing_anchors`,
  `image_alt`, `links_resolve`, `slug_keyphrase`. No LLM involvement;
  every rule is regex + stdlib so the output is reproducible offline.
- **CLI verb `qa-draft`** — reads a Markdown draft and the client's
  `content_inventory.json` (when present) and prints a structured
  JSON report. Returns exit code 1 when any finding is red so CI
  gates can use it. With `--write`, persists the report to
  `<client>/output/qa_reports/<slug>.qa.json`.
- Documentation: [`docs/qa.md`](https://github.com/OtShelniko/site-context-pipeline/blob/main/docs/qa.md) describes every check,
  the JSON shape, the library API, and how to add a new rule.
- **Search-evidence provider interface** (#3) — `providers.base`
  finalises the `SearchEvidenceProvider` abstract base; the registry
  exposes a third map (`SEARCH_EVIDENCE_PROVIDERS`) and matching
  `get_search_evidence_provider` accessor.
- **Local SERP-evidence CSV provider** — new `local-serp-csv`
  reads hand-curated rows (`query`, `rank`, `title`, `url`,
  `snippet`, `page_type`) and emits `SearchEvidence` rows into
  `data/search_evidence.json`. Tolerant header aliases
  (`position` ↔ `rank`, `Page Type` ↔ `page_type`, etc.). Stdlib only.
- **CLI verb `import-search-evidence`** with the same
  `--provider / --source / --config / --write` shape as the existing
  import commands.
- **Context-pack integration** — when `data/search_evidence.json`
  exists, the pack adds a `search_evidence` block (rows, query count,
  per-query top-5 results with page_type counts) and the Markdown
  pack renders a "What competitors do" section. Missing → omitted
  silently; no scraping ever happens.
- **Configurable classifier rules** (#4) — `config/classifier.json`
  now supports per-rule `priority`, `exclude_patterns` (negation),
  and `allow_urls` (forced matches) on top of the existing
  `page_type` / `pattern` keys. The legacy two-key schema keeps
  working unchanged. Invalid rules surface as named warnings
  (`classifier_rule_invalid_page_type`, etc.) in the inventory output.
- New module: `inventory.ClassifierRule` dataclass; `classify_url`
  accepts both `ClassifierRule` instances and legacy
  `(page_type, pattern)` tuples for back-compat.
- Documentation: [`docs/classifier.md`](https://github.com/OtShelniko/site-context-pipeline/blob/main/docs/classifier.md)
  describes the schema, resolution order, and warning tokens.

## [0.2.0] — 2026-05-31

Adds two input adapters: sitemap XML and Screaming Frog SEO Spider CSV.
The toolkit now reads almost every common URL/link source format
without a manual reshape step.

### Added

- **Screaming Frog CSV importer** — `importers.screaming_frog` ships
  three public functions: `read_inventory_csv` (`internal_html.csv` /
  `internal_all.csv`), `read_link_csv` (`all_inlinks.csv` /
  `all_outlinks.csv`), and `detect_flavour` for auto-routing. Tolerant
  of header aliases between Screaming Frog versions (`Title 1` ↔
  `Title`, `H1-1` ↔ `H1`, `Source`/`Destination` ↔ `From`/`To`).
- `build-inventory --format screaming-frog` and `build-link-graph
  --format screaming-frog` flags. `--format auto` (the default) sniffs
  CSV headers and routes Screaming Frog exports to the SF reader
  automatically — no flag needed for canonical exports.
- **Sitemap XML importer** (carried over from 0.1.1) —
  `importers.sitemap_xml.read_sitemap` and `--format sitemap`.

### Changed

- `build_link_graph` now takes an optional `source_format` parameter
  to mirror `build_inventory`. Existing CSV/JSON usage is unchanged.

## [0.1.1] — 2026-05-31

First PyPI release. Adds the sitemap XML importer; everything else from
0.1.0 still applies.

### Added

- **Sitemap XML importer** (`importers.sitemap_xml.read_sitemap`) and a
  new `--format sitemap` flag on `build-inventory`. The importer reads
  a single `urlset` sitemap or follows a local `sitemapindex` to its
  child sitemaps. Pure stdlib (`xml.etree.ElementTree`); no network
  fetching — sitemap-index entries that point at remote URLs are
  reported in `warnings` and skipped.
- `build-inventory --format` accepts `auto` (default), `csv`, `json`,
  `sitemap`. `auto` picks the reader from the file extension.

### Changed

- `build_inventory` now takes an optional `source_format` parameter to
  match the new CLI flag. Existing CSV/JSON usage is unchanged.

## [0.1.0] — 2026-05-31

Initial public extraction.

### Added

- Initial OSS extraction from a private content-pipeline project.
- Offline core pipeline: page inventory, internal link graph, agent
  context pack, content opportunities report.
- Synthetic demo client at `examples/demo-client/` (no real domains,
  keywords, or client data).
- Provider abstraction layer:
  - `KeywordProvider` and `SearchPerformanceProvider` abstract bases.
  - `ProviderResult`, `KeywordMetric`, `SearchEvidence` data models.
  - Registry with `get_keyword_provider`, `get_search_performance_provider`,
    `available_providers`.
  - Error types: `ProviderError`, `ProviderConfigurationError`,
    `ProviderNotConfiguredError`.
- **Local CSV keyword provider** (`local-csv`).
- **Local Search-Console-style CSV provider** (`local-gsc-csv`).
- **Stub adapters** for `google-ads` and `google-search-console` that
  return a structured `not_configured` `ProviderResult`. No live calls,
  no SDK imports, no credentials needed.
- Context pack now includes optional sections when the provider
  artifacts exist:
  - top keyword opportunities,
  - search performance summary,
  - pages with impressions but weak CTR,
  - pages with rankings but weak internal support,
  - `missing_keyword_data` warning when neither artifact exists.
- CLI commands:
  - `init`, `build-inventory`, `build-link-graph`,
    `build-context-pack`, `inspect` (offline core),
  - `import-keywords`, `import-search-performance`, `list-providers`
    (provider commands).
- Documentation: `README.md`, `ROADMAP.md`, `CHANGELOG.md`,
  `docs/architecture.md`, `docs/providers.md`, `docs/artifacts.md`.
- 50 tests across 6 files; ruff lint configuration.
- GitHub Actions CI matrix on Python 3.11 and 3.12.

### Notes

- The base package has zero runtime dependencies. Dev extras
  (`pytest`, `ruff`) are installed via `pip install -e ".[dev]"`.
- Vendor-specific names are confined to provider identifiers
  (e.g. `google-ads`). Core schemas, CLI verbs, and artifact field
  names stay vendor-neutral.

[Unreleased]: https://github.com/OtShelniko/site-context-pipeline/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/OtShelniko/site-context-pipeline/releases/tag/v0.3.0
[0.2.0]: https://github.com/OtShelniko/site-context-pipeline/releases/tag/v0.2.0
[0.1.1]: https://github.com/OtShelniko/site-context-pipeline/releases/tag/v0.1.1
[0.1.0]: https://github.com/OtShelniko/site-context-pipeline/releases/tag/v0.1.0
