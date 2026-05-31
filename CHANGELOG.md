# Changelog

All notable changes to `site-context-pipeline` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet. See [`ROADMAP.md`](./ROADMAP.md) for what is planned.

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

[Unreleased]: https://github.com/OtShelniko/site-context-pipeline/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/OtShelniko/site-context-pipeline/releases/tag/v0.1.1
[0.1.0]: https://github.com/OtShelniko/site-context-pipeline/releases/tag/v0.1.0
