# How this compares

`site-context-pipeline` is a small piece of a larger toolchain. It does
not replace a crawler, an SEO suite, or a CMS. It complements them by
answering one specific question: *what does an LLM (or a human writer)
need to read about this site before drafting anything?*

This page is an honest, opinionated guide to where the toolkit fits
relative to the tools you probably already use. If we genuinely do
something better, it's said so. If a commercial tool is the right
answer, that's said too.

> **Bias disclosure.** This is the project's own docs page; treat it
> the way you'd treat any vendor comparison. The matrix below is
> based on the public capabilities of each tool at the time of
> writing; details change. If you find an inaccuracy, please open an
> issue.

## At a glance

| Capability | site-context-pipeline | Screaming Frog | Sitebulb | ContentKing | Ahrefs / Semrush | Custom Python script |
|---|---|---|---|---|---|---|
| **Crawls a live site** | no — bring a CSV/sitemap | yes | yes | yes (continuous) | yes | yes (you write it) |
| **Reads sitemap.xml** | yes (offline) | yes | yes | yes | yes | yes |
| **Reads SF exports** | yes (`internal_*.csv`, `*_inlinks.csv`) | n/a (it *is* SF) | partial | no | no | yes (you write it) |
| **Internal link graph** | yes — joined with inventory | yes | yes (richer) | yes | basic | yes |
| **Page-type classification** | yes — configurable rules with priority/exclude/allow | basic via filters | yes (segments) | yes | no | yes |
| **Keyword volume integration** | local CSV, vendor-neutral | no | partial | no | yes (proprietary) | yes |
| **Search Console integration** | local GSC CSV today; live API on roadmap | no | partial | no | indirect | yes |
| **Search-evidence (SERP) rows** | local hand-curated CSV | no | no | no | yes (proprietary) | yes |
| **Deterministic Markdown QA** | yes (9 checks, exit-coded) | no | no | no | no | partial |
| **Single-artifact LLM context pack** | yes (JSON + Markdown) | no | no | no | no | yes (you write it) |
| **Public JSON Schemas** | yes (six schemas, in-wheel) | no | no | no | no | n/a |
| **Offline / air-gapped CI** | yes — base install zero deps | no (desktop app) | no | no (cloud) | no (cloud) | maybe |
| **Open source** | yes (MIT) | no | no | no | no | yes (yours) |
| **Cost** | free | paid (license) | paid (subscription) | paid (subscription) | paid (subscription) | engineering time |

## Where this toolkit is better

**For everything below, "better" means *better at this specific job* —
a crawl-heavy job is still a job for Screaming Frog.**

- **Producing a stable digest for an LLM.** No commercial SEO suite
  publishes a structured, machine-readable, deterministic digest of a
  site that a model can consume without scraping screenshots of
  dashboards. That gap is the reason this project exists.
- **Reproducible pipelines.** Same input → same output, byte-for-byte.
  CI can compare today's pack against last quarter's via a normal
  Git diff. Cloud SEO tools change their numbers between page-loads.
- **Vendor-neutrality and air-gapped use.** Zero runtime dependencies
  in the base install means it runs on a locked-down CI runner that
  has no network access. Cloud SEO tools can't.
- **Putting human review first.** The output is designed to be read
  by a person before any LLM gets to it. The Markdown twin of the
  pack is human-friendly; the JSON twin is automation-friendly. Both
  ship out of the same command.
- **Custom classification rules.** Configurable rules with priority,
  exclude patterns, and allow-lists handle messy IAs (commercial
  pages mixed with content; localised slug variants; legacy URLs).
  Out-of-the-box page-type buckets in commercial tools rarely fit.

## Where this toolkit is *not* the right answer

- **You need to crawl a site.** Use Screaming Frog, Sitebulb, or
  Ahrefs Site Audit. This toolkit does not have a crawler in 0.x and
  has no plans to grow one — it integrates with the output of yours.
- **You need a managed SEO platform with dashboards, alerting, and
  proprietary keyword data.** Use Ahrefs, Semrush, or Sitebulb. They
  cost money for a reason.
- **You want continuous monitoring.** ContentKing exists for this and
  is good at it.
- **You want a "write me a 1500-word article" button.** Out of scope.
  Forever.
- **Your search engine is Yandex (or Baidu, or Naver) only.** The
  core is vendor-neutral and the local CSV providers don't care, so
  the toolkit *works* — but you'll bring the data yourself until a
  community provider for your engine of choice lands.

## Common combinations

Most teams using this toolkit also use one or more of:

- **Screaming Frog → site-context-pipeline.** The most common pairing.
  Run SF for a fresh crawl, hand its `internal_html.csv` and
  `all_inlinks.csv` to `build-inventory --format screaming-frog` and
  `build-link-graph --format screaming-frog`. The toolkit picks up
  exactly where SF stops being the right tool for the job.
- **Google Search Console export → site-context-pipeline.**
  Performance → Export → run `import-search-performance --provider
  local-gsc-csv`. The Markdown pack then has a "weak CTR pages"
  section your editor can act on.
- **Ahrefs / Semrush keyword export → site-context-pipeline.** Both
  vendors export to CSV; the local-csv provider reads either format
  with header normalisation, so an Ahrefs `Keyword Difficulty` CSV
  and a Semrush `Search Volume` CSV produce the same artifact shape.

## Why not just write a script?

A custom Python script is the obvious alternative for a one-off
audit. The toolkit beats a script when:

- **More than one person reviews the output.** A shared, documented,
  deterministic format means everyone reads the same digest.
- **The site is audited more than once.** Quarterly audits reuse the
  same pack format; the deltas across time become meaningful.
- **The output goes into an LLM step.** Without a stable schema and
  citation map, agents drift. The pack's `sources` field gives every
  fact a traceable origin.
- **You want to plug in vendor APIs later.** The provider abstraction
  means today's `local-csv` import becomes tomorrow's live API call
  without touching the rest of the pipeline.

If none of those apply, write the script. The toolkit isn't trying to
take work away from anyone.

## See also

- [Architecture](architecture.md) — why the pipeline is structured as
  one-way local-files-only.
- [Providers](providers.md) — the four safety rules that keep
  vendor-specific code optional.
- [Recipes](recipes.md) — concrete workflows that use this toolkit
  alongside the tools listed above.
