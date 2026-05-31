# Providers

A *provider* is a small adapter that reads one external data source
and emits normalised rows the rest of the pipeline can consume. This
document covers what providers do, the shape they return, the input
formats the local providers understand, and the rules every adapter
(present and future) must follow.

## Provider philosophy

1. **Providers are optional.** The base package never imports a
   provider's third-party dependency at the top level, never reads
   credentials, and never makes a network call from the core. If you
   only have a CSV, you only need the local provider.
2. **Providers normalise external data into local artifacts.** Every
   provider produces the same `ProviderResult` shape with the same
   `KeywordMetric` (or `SearchEvidence`) row type. The CLI persists
   that result to disk; nothing else cares which adapter wrote it.
3. **The core reads normalised artifacts, not providers.** The
   context-pack builder reads
   `data/keyword_metrics.json` and `data/search_performance.json`. It
   does not import any provider module. It does not branch on a
   row's `source` field. This avoids vendor lock-in.
4. **Vendor-specific names live in providers, never in the core.**
   Field names, schemas, and CLI verbs stay vendor-neutral. A
   provider *identifier* like `google-ads` may be vendor-specific by
   design — that is the contract that tells the user which API the
   future live adapter will call. Vendor-specific providers must
   remain optional adapters and never become core dependencies.

## Provider result schema

Every provider's `run(...)` method returns a `ProviderResult`:

```python
@dataclass(frozen=True)
class ProviderResult:
    ok: bool                       # False when the provider could not run
    provider: str                  # stable slug, e.g. "local-csv"
    dry_run: bool                  # True until the CLI is invoked with --write
    items: list[Any]               # KeywordMetric / SearchEvidence dicts
    warnings: list[str]            # human-readable, never carry secrets
    errors: list[str]              # machine-readable tokens (e.g. "not_configured")
    metadata: dict[str, Any]       # provider-specific provenance
```

Every row in `items` follows one of two row schemas. For keyword and
search-performance providers, the row is a `KeywordMetric`:

```python
@dataclass(frozen=True)
class KeywordMetric:
    query: str                     # required
    source: str                    # the provider slug that produced this row
    locale: str | None             # BCP 47 locale, e.g. "en-US"
    geo: str | None                # free-form region, e.g. "US", "Moscow"
    language: str | None           # ISO 639-1 language code, e.g. "en"
    avg_monthly_searches: int | None
    impressions: int | None
    clicks: int | None
    ctr: float | None              # fraction in [0..1], e.g. 0.123
    position: float | None
    competition: str | None        # free-form, e.g. "LOW" / "MEDIUM" / "HIGH"
    source_url: str | None         # landing page if known
    raw: dict[str, Any]            # provider-specific extras for forensics
```

For future search-evidence providers (0.3), `SearchEvidence` carries
`query`, `source`, `title`, `url`, `snippet`, `rank`, `page_type`,
`raw`. The dataclass is in `schemas.py`; its provider interface lands
in 0.3.

The on-disk artifact wraps the result in a small envelope:

```json
{
  "schema_version": 1,
  "provider": "local-csv",
  "items_count": 6,
  "metadata": {"source_path": "...", "row_count": 6, "items_count": 6},
  "warnings": [],
  "items": [ { "query": "...", "source": "local-csv", "...": "..." } ]
}
```

## `local-csv` input format

Read keyword metrics from any CSV. Headers are matched
case-insensitively; `_`, `-`, and space are treated as equivalent
(`Search Volume` ≡ `search_volume` ≡ `search-volume` ≡ `searchvolume`).

| Required (one of) | Aliases |
|---|---|
| `query` | `keyword`, `search_term` |

| Optional | Aliases | Type / parsing rule |
|---|---|---|
| `avg_monthly_searches` | `search_volume`, `monthly_searches`, `volume`, `searches` | int; thousand separators OK (`"1,234"` → `1234`) |
| `impressions` | — | int |
| `clicks` | — | int |
| `ctr` | `click_through_rate` | float in `[0..1]`; percent strings handled (`"12.3%"` → `0.123`); decimal commas handled (`"12,5"` → `12.5`) |
| `position` | `average_position`, `avg_position`, `rank` | float |
| `competition` | `competition_value`, `difficulty` | passthrough string |
| `locale` | — | string |
| `geo` | `country`, `location` | string |
| `language` | `lang` | string |
| `source_url` | `landing_page`, `url` | string |

Unknown columns are preserved in each row's `raw` dict so no
information is lost.

Sample (synthetic):

```csv
query,avg_monthly_searches,competition,geo,language,source_url
local delivery service,3600,HIGH,US,en,https://example.com/services/local-delivery/
delivery cost guide,2400,MEDIUM,US,en,https://example.com/blog/delivery-cost-guide/
```

## `local-gsc-csv` input format

Tolerant of any CSV that uses Google Search Console-like headers. The
same column-normalisation rules apply.

| Required | Aliases |
|---|---|
| `query` | `top queries`, `top_queries`, `search_term` |

| Optional | Aliases | Notes |
|---|---|---|
| `page` | `landing_page`, `url`, `address` | becomes `source_url` |
| `clicks` | — | |
| `impressions` | — | |
| `ctr` | `click_through_rate` | normalised to fraction |
| `position` | `average_position`, `average position` | |
| `country` | `geo`, `location` | becomes `geo` |
| `device` | — | preserved on `raw.device` |
| `date` | — | preserved on `raw.date` |
| `locale` | — | |
| `language` | `lang` | |

The exporter never aggregates; one CSV row becomes one
`KeywordMetric`. The context pack does its own aggregation per page
when it computes `weak_ctr_pages` and `ranked_but_unsupported`.

Sample (synthetic):

```csv
query,page,clicks,impressions,ctr,position,country,device,date
local delivery service,https://example.com/services/local-delivery/,68,2800,2.43%,9.2,USA,DESKTOP,2026-04
business delivery pricing,https://example.com/pricing/,33,610,5.41%,8.9,USA,DESKTOP,2026-04
```

## Why API adapters are optional

- **Different markets, different vendors.** Hardcoding any one API
  would push the toolkit toward one market and against another.
- **Vendor APIs change.** Auth flows, rate limits, schemas, and
  access tiers shift. CSV files do not. Building the data contract
  around CSV/JSON keeps the pipeline working when an API changes.
- **Bring your own data.** The pipeline cannot tell whether your
  `keyword_metrics.csv` came from Google Ads, Yandex Wordstat,
  Ahrefs, Semrush, an internal database, or a hand-curated
  spreadsheet. Every row is treated the same way.
- **No surprise dependencies.** Adding `google-ads` or
  `google-api-python-client` to the base install would force every
  user — including users who only need the offline core — to
  download dozens of MB of vendor SDKs they will never call.

## How future providers should be added

1. **Pick a stable slug.** Lowercase, hyphen-separated, vendor-aware
   when the adapter is vendor-specific (e.g. `dataforseo-keywords`,
   `yandex-wordstat`). Generic when it is not (e.g.
   `local-keyword-json`).
2. **Subclass the right base.** `KeywordProvider` for demand-side or
   per-query metrics, `SearchPerformanceProvider` for performance
   data. Set `provider_name` to the slug from step 1.
3. **Implement `run(*, source, provider_config)`.**
   - Read inputs (a file path, an API config dict, or both).
   - Build `KeywordMetric` rows. Fill in only the fields you actually
     have; leave the rest `None`. Set `source` to your slug.
   - Return a `ProviderResult`. Use `blocked_result` from
     `providers.base` for "I cannot run yet" outcomes; raise
     `ProviderConfigurationError` for malformed inputs.
4. **Register the class** in
   `src/site_context_pipeline/providers/registry.py` —
   one line in `KEYWORD_PROVIDERS` or `SEARCH_PERFORMANCE_PROVIDERS`,
   plus a one-line description in `_PROVIDER_DESCRIPTIONS`.
5. **Add tests** under `tests/`. The test suite must run offline.
   For live adapters, mock at the HTTP layer or test only the
   `not_configured` path.
6. **Document the adapter.** Add a row to the README provider table
   and, for live adapters, a short config section in this file.
7. **Live adapters use optional extras.** If your adapter needs a
   third-party SDK, declare it in `pyproject.toml` under
   `[project.optional-dependencies]` (e.g. `google-ads = ["google-ads"]`)
   so the base install stays dependency-free.

## Provider safety rules

These rules apply to every present and future provider:

- **No credentials in the repository.** Not in code, not in tests,
  not in fixtures, not in CI logs. Read credentials from environment
  variables or a local `.env` file the user maintains. Never serialise
  a credential into an artifact.
- **No required SDKs in the base install.** Vendor SDKs are optional
  extras (`pip install site-context-pipeline[<extra>]`). The base
  package must `pip install` cleanly with `dependencies = []`.
- **No live network calls in tests.** Every test must pass with the
  network disabled. Tests for live adapters either stop at the
  `not_configured` path or mock the HTTP layer with stdlib
  `unittest.mock`. Tests must not require API keys to run.
- **Structured `not_configured` result when config is missing.**
  Adapters that cannot run because credentials or optional
  dependencies are missing must return a `ProviderResult` with
  `ok=False`, `items=[]`, `errors=["not_configured"]`, and a
  human-readable suggestion in `metadata.suggestion`. They must never
  raise. The CLI converts this into `exit code 1` plus a clean JSON
  payload the user can act on.
- **Sanitise `warnings`.** Warning strings are surfaced to humans and
  to LLMs that read the context pack. Never include credentials,
  request bodies, or full URLs with query strings that could carry
  tokens.
- **Preserve provenance.** Every row carries `source = <provider_name>`
  so a reviewer can tell which adapter produced which data.

## Listing providers in this release

| Name | Kind | Status | Live in 0.1? |
|---|---|---|---|
| `local-csv` | keyword | live | yes |
| `google-ads` | keyword | stub | no — returns `not_configured` |
| `local-gsc-csv` | search_performance | live | yes |
| `google-search-console` | search_performance | stub | no — returns `not_configured` |
| `local-serp-csv` | search_evidence | live | yes |

Run `site-context-pipeline list-providers` to see the same list as JSON.

> **Per-provider reference.** For a uniform, self-contained reference
> on each shipped provider — config keys, input columns, failure
> modes, rate limits, and a worked example — see
> [Provider reference](provider-reference.md).
