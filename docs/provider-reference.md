# Provider reference

A uniform, per-provider reference. Every provider shipped today is
documented with the same fixed set of headings so a new contributor
can copy the layout when adding their own adapter. For the philosophy,
the result schema, and the safety rules that bind every provider, see
[Providers](providers.md).

Each entry below answers the same eight questions:

1. **Identifier & kind** — the slug and which base class it extends.
2. **Status** — live, stub, or planned.
3. **Install requirements** — base install or an `[extra]`.
4. **Inputs** — CSV columns (with aliases) or config keys.
5. **Output** — the artifact path and the `source` value rows carry.
6. **Failure modes** — what `not_configured` /
   `ProviderConfigurationError` / `ProviderError` look like.
7. **Rate limits** — for live adapters only.
8. **Worked example** — a minimal end-to-end command.

---

## `local-csv`

| | |
|---|---|
| **Identifier & kind** | `local-csv` · `KeywordProvider` |
| **Status** | **live** |
| **Install requirements** | base install (zero runtime deps) |
| **Output artifact** | `data/keyword_metrics.json` |
| **Row `source`** | `local-csv` |
| **Rate limits** | n/a — reads a local file |

### Inputs

Reads keyword metrics from any CSV. Headers match case-insensitively;
`_`, `-`, and space are equivalent (`Search Volume` ≡ `search_volume`).

| Field | Required | Aliases | Parsing |
|---|---|---|---|
| `query` | **yes** (one of) | `keyword`, `search_term` | trimmed string |
| `avg_monthly_searches` | no | `search_volume`, `monthly_searches`, `volume`, `searches` | int; `"1,234"` → `1234` |
| `impressions` / `clicks` | no | — | int |
| `ctr` | no | `click_through_rate` | fraction `[0..1]`; `"12.3%"` → `0.123` |
| `position` | no | `average_position`, `avg_position`, `rank` | float |
| `competition` | no | `competition_value`, `difficulty` | passthrough |
| `geo` | no | `country`, `location` | string |
| `language` | no | `lang` | string |
| `locale` / `source_url` | no | `landing_page`, `url` (for `source_url`) | string |

Unknown columns are preserved in each row's `raw` dict.

### Failure modes

| Condition | Behaviour |
|---|---|
| `--source` omitted | raises `ProviderConfigurationError` |
| file does not exist | raises `ProviderConfigurationError` |
| row has no `query` | row skipped; `skipped_rows_without_query:<n>` warning |
| non-UTF-8 bytes | retries with `cp1251`; `csv_decoded_with_cp1251_fallback` warning |

### Worked example

```bash
site-context-pipeline import-keywords \
    --client demo \
    --provider local-csv \
    --source examples/demo-client/input/keyword_metrics.csv \
    --write
```

---

## `local-gsc-csv`

| | |
|---|---|
| **Identifier & kind** | `local-gsc-csv` · `SearchPerformanceProvider` |
| **Status** | **live** |
| **Install requirements** | base install |
| **Output artifact** | `data/search_performance.json` |
| **Row `source`** | `local-gsc-csv` |
| **Rate limits** | n/a — reads a local file |

### Inputs

Tolerant of any CSV using Google Search Console-style headers.

| Field | Required | Aliases | Notes |
|---|---|---|---|
| `query` | **yes** | `top queries`, `top_queries`, `search_term` | |
| `page` | no | `landing_page`, `url`, `address` | becomes `source_url` |
| `clicks` / `impressions` | no | — | int |
| `ctr` | no | `click_through_rate` | normalised to a fraction |
| `position` | no | `average_position`, `average position` | float |
| `country` | no | `geo`, `location` | becomes `geo` |
| `device` / `date` | no | — | preserved on `raw` |

One CSV row becomes one `KeywordMetric`; the provider never aggregates.

### Failure modes

Same shape as `local-csv`: missing `--source` or a missing file raises
`ProviderConfigurationError`; query-less rows are skipped with a
`skipped_rows_without_query:<n>` warning.

### Worked example

```bash
site-context-pipeline import-search-performance \
    --client demo \
    --provider local-gsc-csv \
    --source examples/demo-client/input/search_console.csv \
    --write
```

---

## `local-serp-csv`

| | |
|---|---|
| **Identifier & kind** | `local-serp-csv` · `SearchEvidenceProvider` |
| **Status** | **live** |
| **Install requirements** | base install |
| **Output artifact** | `data/search_evidence.json` |
| **Row `source`** | `local-serp-csv` |
| **Rate limits** | n/a — the toolkit never scrapes SERPs |

### Inputs

Reads hand-curated SERP rows. The toolkit does **not** fetch search
results; you supply the rows.

| Field | Required | Aliases | Notes |
|---|---|---|---|
| `query` | **yes** | `keyword`, `search_term` | |
| `rank` | no | `position` | int; `"1.0"` → `1` |
| `title` / `url` / `snippet` | no | — | string |
| `page_type` | no | `Page Type`, `type` | free-form label |

Unknown columns are preserved in `raw`.

### Failure modes

Missing `--source` or a missing file raises
`ProviderConfigurationError`. A CSV with no recognisable `query` column
raises `ProviderConfigurationError` (the file is structurally wrong, not
merely empty).

### Worked example

```bash
site-context-pipeline import-search-evidence \
    --client demo \
    --provider local-serp-csv \
    --source examples/demo-client/input/search_evidence.csv \
    --write
```

---

## `google-ads`

| | |
|---|---|
| **Identifier & kind** | `google-ads` · `KeywordProvider` |
| **Status** | **live (opt-in)** — requires the `[google-ads]` extra and credentials |
| **Install requirements** | `pip install "site-context-pipeline[google-ads]"` |
| **Output artifact** | `data/keyword_metrics.json` |
| **Row `source`** | `google-ads` |

### Inputs

The adapter calls
[`KeywordPlanIdeaService.GenerateKeywordIdeas`](https://developers.google.com/google-ads/api/docs/keyword-planning/generate-keyword-ideas)
with config supplied via `--config <client>/config/google_ads.json`
(gitignored) or built from environment variables:

| Config key | Required | Purpose |
|---|---|---|
| `customer_id` | **yes** | Google Ads customer ID |
| `developer_token` | **yes** | Google Ads developer token |
| `client_id` / `client_secret` | **yes** | OAuth client credentials |
| `refresh_token` | **yes** | OAuth refresh token |
| `seeds` | one of `seeds`/`page_url` | list of seed phrases |
| `page_url` | one of `seeds`/`page_url` | URL seed to expand from |
| `geo_target_constants` | no | e.g. `["geoTargetConstants/2840"]` |
| `language_constant` | no | e.g. `"languageConstants/1000"` |
| `login_customer_id` | no | manager (MCC) account, if used |

Credentials are read from the config or the environment — **never**
committed, never logged, never serialised into an artifact. The
`customer_id` is masked in result metadata.

### Output

One `KeywordMetric` per returned idea: `query`, `avg_monthly_searches`,
`competition` (`LOW`/`MEDIUM`/`HIGH`), and `raw` with the top-of-page
bid micros for forensics. `source` is `google-ads`.

### Failure modes

| Condition | Behaviour |
|---|---|
| no `--config` / empty config | `not_configured` result (`ok=false`, exit 1), points at `local-csv` |
| config present but missing a required key | raises `ProviderConfigurationError` naming the keys |
| `[google-ads]` extra not installed | `missing_dependency` result (`ok=false`, exit 1) |
| config complete but no `seeds`/`page_url` | raises `ProviderConfigurationError` |

The not-configured payload:

```json
{
  "ok": false,
  "provider": "google-ads",
  "items": [],
  "errors": ["not_configured"],
  "metadata": {"blocked_reason": "not_configured", "suggestion": "…"}
}
```

The adapter never makes a network call until a complete credential
block is supplied, and never imports the SDK at module load.

### Rate limits

The Google Ads API enforces per-developer-token operation quotas and
raises `GoogleAdsException` with `RESOURCE_EXHAUSTED` when throttled.
Keep seed batches modest; the adapter sends all seeds in a single
`GenerateKeywordIdeas` request.

### Worked example

```bash
# Offline: returns not_configured + a suggestion, exits 1.
site-context-pipeline import-keywords --client demo --provider google-ads

# Live (requires the extra + a credentials file):
pip install "site-context-pipeline[google-ads]"
site-context-pipeline import-keywords \
    --client demo \
    --provider google-ads \
    --config clients/demo/config/google_ads.json \
    --write
```

---

## `google-search-console`

| | |
|---|---|
| **Identifier & kind** | `google-search-console` · `SearchPerformanceProvider` |
| **Status** | **live (opt-in)** — requires the `[gsc]` extra and credentials |
| **Install requirements** | `pip install "site-context-pipeline[gsc]"` |
| **Output artifact** | `data/search_performance.json` |
| **Row `source`** | `google-search-console` |

### Inputs

The adapter calls the
[Search Analytics API](https://developers.google.com/webmaster-tools/v1/searchanalytics/query)
with config supplied via `--config <client>/config/google_search_console.json`
(gitignored):

| Config key | Required | Purpose |
|---|---|---|
| `site_url` | **yes** | verified property (`sc-domain:example.com` or a URL prefix) |
| `credentials_path` | **yes** | service-account JSON file path |
| `start_date` / `end_date` | **yes** | ISO date range |
| `dimensions` | no | subset of `query`/`page`/`country`/`device`/`date`/`searchAppearance`; must include `query`; default `["query", "page"]` |
| `row_limit` | no | 1–25000; default 1000 (clamped to the API cap) |

Credentials are read from the service-account file — **never**
committed, never logged, never serialised into an artifact.

### Output

One `KeywordMetric` per Search Analytics row: `query`, `source_url`
(from the `page` dimension), `geo` (from `country`), `impressions`,
`clicks`, `ctr` (already a fraction), `position`, and any extra
dimensions (`device`, `date`, `searchAppearance`) preserved in `raw`.
`source` is `google-search-console`.

### Failure modes

| Condition | Behaviour |
|---|---|
| no `--config` / empty config | `not_configured` result (`ok=false`, exit 1), points at `local-gsc-csv` |
| config present but missing a required key | raises `ProviderConfigurationError` naming the keys |
| `dimensions` without `query` or with an unknown value | raises `ProviderConfigurationError` |
| `[gsc]` extra not installed | `missing_dependency` result (`ok=false`, exit 1) |

The adapter never makes a network call until a complete config is
supplied, and never imports the Google client libraries at module load.

### Rate limits

Search Analytics enforces per-site and per-project QPS limits plus a
daily query cap. `row_limit` is clamped to the API's 25000-row maximum
per request; for larger pulls, page by date range. The adapter sends a
single `query` request per invocation.

### Worked example

```bash
# Offline: returns not_configured + a suggestion, exits 1.
site-context-pipeline import-search-performance \
    --client demo --provider google-search-console

# Live (requires the extra + a credentials file):
pip install "site-context-pipeline[gsc]"
site-context-pipeline import-search-performance \
    --client demo \
    --provider google-search-console \
    --config clients/demo/config/google_search_console.json \
    --write
```

---

## Adding your own provider

The eight-heading layout above is the template. To contribute a new
adapter:

1. Copy one of the entries above into this file as a starting point.
2. Follow the step-by-step in
   [Providers → How future providers should be added](providers.md#how-future-providers-should-be-added).
3. Honour the
   [provider safety rules](providers.md#provider-safety-rules):
   no credentials in the repo, no required SDK in the base install,
   no live network calls in tests, structured `not_configured` when
   config is missing.

Run `site-context-pipeline list-providers` to confirm your provider is
registered and to see its live/stub status as JSON.
