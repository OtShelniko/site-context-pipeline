# Tutorial: from a sitemap to a context pack

This walkthrough takes a fictional site and produces every artifact the
toolkit can emit. It is the long version of the README quickstart: each
step explains *why* it exists and what changes in the workspace.

The whole tutorial runs offline and uses only the synthetic
`example.com` fixtures shipped under `examples/demo-client/`. There is
no real site behind any of these URLs.

> Reading time: ~10 minutes. Hands-on time: ~5 minutes.

## The scenario

Imagine you are a content lead at a small logistics company called
**Example Co**. You have a small marketing site (~8 pages) and a
handful of blog posts. You also run Google Search Console and have an
exported keyword list.

You want to:

1. Capture what the site looks like today as one structured digest.
2. Surface gaps — pages that rank but get no internal-link support,
   blog posts orphaned from your services, queries that get
   impressions but no clicks.
3. Hand that digest to a writer (or to an LLM) before they touch a
   brief.

The toolkit is built for exactly this loop. By the end of this
tutorial you will have produced the agent context pack that replaces
"please go look at the site yourself" with one source-backed JSON +
Markdown document.

## Step 0 — install

```bash
pip install site-context-pipeline
```

Python 3.11 or newer. Zero runtime dependencies, so this finishes in
about a second.

Verify:

```bash
site-context-pipeline --version
# site-context-pipeline 0.1.1
```

## Step 1 — initialise a workspace

Each site lives in its own `clients/<id>/` directory tree. Create one:

```bash
site-context-pipeline init --client demo --write
```

What this creates:

```
clients/demo/
├── input/
│   ├── project.md         editorial notes (verbatim in the pack)
│   ├── urls.csv           empty header — fill in or replace
│   └── links.csv          empty header — optional
├── config/                per-client overrides go here
├── data/                  generated JSON artifacts land here
├── output/                generated context packs land here
└── logs/
```

The dry-run pattern: every CLI command supports `--write`. Without
that flag the command runs in dry-run mode and prints `planned_writes`
on stdout instead of touching the filesystem. Try it:

```bash
site-context-pipeline init --client another-demo
# Shows what would be created. Nothing is touched.
```

## Step 2 — build the inventory

The inventory is the foundation of every other step. It says *which
pages exist on the site*, what type each page is, and the rule that
fired during classification (so you can audit the result).

There are three ways to feed URLs in. Pick whichever your data already
has — the rest of the pipeline does not care.

### Option A: sitemap.xml

If your site already publishes a sitemap, use it directly. The
toolkit reads `<urlset>` files and follows local `<sitemapindex>`
files to their children. It never fetches anything over HTTP.

```bash
site-context-pipeline build-inventory \
    --client demo \
    --source path/to/sitemap.xml \
    --format sitemap \
    --write
```

`--format auto` (the default) picks the reader from the file
extension, so `--format sitemap` is only needed if your sitemap has
an unusual extension.

If your sitemap-index points at remote child sitemaps, they are
*reported* in `warnings` (`skipped_remote_child_sitemap:<url>`) and
not fetched. You can save those children locally and point at them
explicitly.

### Option B: a CSV from your CMS

```bash
site-context-pipeline build-inventory \
    --client demo \
    --source examples/demo-client/input/urls.csv \
    --write
```

The CSV recognises common columns case-insensitively:

| Column | Aliases |
|---|---|
| `url` | `address` |
| `title` | `title 1` |
| `h1` | `h1-1` |
| `status_code` | `status code`, `status` |
| `word_count` | `word count`, `words` |
| `inlinks_count` | `inlinks count`, `inlinks` |
| `outlinks_count` | `outlinks count`, `outlinks` |

Spaces, dashes, and underscores are interchangeable in headers
(`Word Count`, `word_count`, and `word-count` all map to the same
field).

### Option C: a JSON URL list

If you already have a structured list (from a CMS export, an Airtable
view, etc.):

```json
[
  {"url": "https://example.com/", "title": "Home"},
  {"url": "https://example.com/services/", "title": "Services"}
]
```

```bash
site-context-pipeline build-inventory \
    --client demo --source urls.json --write
```

### What just happened

For the demo CSV, the result looks like this:

```bash
site-context-pipeline inspect --client demo
```

```jsonc
{
  "command": "inspect",
  "data": {
    "checks": [
      {"name": "data/content_inventory.json", "ok": true, "...": "..."}
    ]
  }
}
```

Open `clients/demo/data/content_inventory.json`. Each row has a
`page_type` (`home`, `service`, `blog`, `category`, `landing`,
`other`) and a `classification_reason` (e.g.
`matched_pattern:*/blog/*` or `matched_home_path`) so you can tell
*why* a URL ended up where it did.

### Customising the classifier

If your URL structure does not match the built-in patterns, drop a
`classifier.json` into `clients/demo/config/`:

```json
{
  "rules": [
    { "page_type": "blog", "pattern": "*/articles/*" },
    { "page_type": "service", "pattern": "*/what-we-do/*" },
    { "page_type": "landing", "pattern": "*/get-started/*" }
  ]
}
```

Rules are evaluated in order; the first match wins. The reason string
records which pattern fired, so the result stays auditable.

To pin specific URLs as commercial regardless of pattern, list them
in `clients/demo/config/commercial_urls.json`:

```json
["https://example.com/pricing/"]
```

These get `page_type: "landing"` with reason
`matched_commercial_url_list`.

## Step 3 — build the link graph

Internal links matter for two reasons: they tell the toolkit which
pages are linked together, and they let it spot pages that *should*
be linked but are not. Feed it an edge CSV (Screaming Frog all-inlinks
exports work directly):

```bash
site-context-pipeline build-link-graph \
    --client demo \
    --source examples/demo-client/input/links.csv \
    --write
```

The output, `clients/demo/data/internal_link_graph.json`, contains:

- `nodes` — one per URL, with `inlink_count`, `outlink_count`,
  `blog_inlink_count`, and an `is_commercial_target` flag.
- `edges` — the actual link data.
- `commercial_pages_low_blog_inlinks` — services / categories /
  landings receiving zero inlinks from blog posts.
- `blog_pages_low_inlinks` — blog posts with at most one inlink.

You do not need an edge list for the toolkit to work. Without one,
the graph contains nodes only and a warning
`no_edges_in_input_using_inventory_counts_only` lets the pack flag
the limited support data.

## Step 4 — import keyword and performance data (optional)

If you have keyword volume data — from Google Ads Keyword Planner,
Ahrefs, Semrush, hand-curated research, anything — bring it in:

```bash
site-context-pipeline import-keywords \
    --client demo \
    --provider local-csv \
    --source examples/demo-client/input/keyword_metrics.csv \
    --write
```

The provider normalises every row into the same `KeywordMetric`
shape, no matter which tool exported the CSV. See
[`docs/providers.md`](./providers.md) for the field mapping.

Search Console data goes through a sibling provider:

```bash
site-context-pipeline import-search-performance \
    --client demo \
    --provider local-gsc-csv \
    --source examples/demo-client/input/search_console.csv \
    --write
```

This step is fully optional. Skip it and the context pack will
include a clear `missing_keyword_data` warning so reviewers know the
demand and performance sections were not filled in.

## Step 5 — generate the context pack

The pack is the deliverable. It aggregates every artifact above into
one machine- and human-readable document:

```bash
site-context-pipeline build-context-pack --client demo --write
```

Three files appear in `clients/demo/output/`:

| File | What it contains |
|---|---|
| `agent_context_pack.json` | Stable schema (`schema_version: 1`) suitable for downstream LLMs and validators. |
| `agent_context_pack.md` | Human-readable mirror with the same content, plus opportunity sections rendered as Markdown lists. |
| `content_opportunities.md` | A focused review prompt: orphan blog posts, commercial pages with no blog support, weak-CTR queries, ranked-but-unsupported pages. |

### What the pack actually says

Open `agent_context_pack.md`. Sections you should expect:

- **Summary** — page count, link counts, and the count of keyword /
  performance rows.
- **Page-type breakdown** — counts per `page_type`.
- **Pages by type** — the actual URL list, grouped by type, with the
  classification reason next to each.
- **Opportunities → Top keyword opportunities** *(only if you
  imported keyword data)* — keywords ranked by demand.
- **Opportunities → Pages with impressions but weak CTR** *(only if
  you imported performance data)* — queries that got ≥ 100
  impressions but a CTR ≤ 2 %.
- **Opportunities → Pages with rankings but weak internal support** —
  pages that already rank (best position ≤ 20) but receive zero
  inlinks or zero blog inlinks.
- **Search performance summary** — totals and impression-weighted
  averages.
- **Project notes** — verbatim contents of `input/project.md`.
- **Sources** — absolute paths of every file the pack was built from.

The JSON sibling has the same data with a stable shape. A downstream
consumer should validate `schema_version` before reading.

## Step 6 — hand it off

The pack is the artifact you give to:

- a writer or editor preparing a brief,
- an LLM coding/content assistant (paste the Markdown into the
  prompt),
- a reviewer comparing the live site to what the toolkit sees.

Every claim in the pack carries either a `classification_reason`, a
`source` field naming the provider, or a `sources` block listing the
file each fact came from. That auditability is the point: when an
LLM later writes a brief that cites the pack, you can trace each
claim back to a real file in your workspace.

## Re-running the pipeline

The pipeline is one-way and re-runnable. When upstream data changes —
your CMS gains a new page, a new sitemap entry appears, your keyword
data updates — re-run the affected step with `--write`. There is no
state to invalidate; each builder just rewrites its own artifact.

## What the toolkit will *not* do for you

The pack is the end of the line. The toolkit deliberately does not:

- write a draft article ("write me a 1000-word post about X"),
- crawl a live site,
- call any search vendor API in the core,
- publish anywhere — neither WordPress nor a CMS nor PyPI.

Those steps belong downstream. The toolkit's job is to make sure the
inputs to the next step are honest and stable.

## Where to go next

- [`README.md`](https://github.com/OtShelniko/site-context-pipeline/blob/main/README.md) — overview and command reference.
- [`docs/architecture.md`](./architecture.md) — how the modules fit
  together; the vendor-neutrality contract.
- [`docs/providers.md`](./providers.md) — the rules for keyword and
  search-performance providers, including how to add your own.
- [`docs/artifacts.md`](./artifacts.md) — the full schema reference
  for every file the pipeline touches.
- [`ROADMAP.md`](https://github.com/OtShelniko/site-context-pipeline/blob/main/ROADMAP.md) — what is planned for 0.2 and beyond.
- The [issue tracker](https://github.com/OtShelniko/site-context-pipeline/issues)
  is where roadmap work happens. Open issues with the `good first
  issue` label are a friendly entry point.
