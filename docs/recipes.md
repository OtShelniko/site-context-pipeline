# Recipes

A short collection of end-to-end recipes — concrete workflows that show
how the toolkit fits into real content and SEO work. Every recipe runs
offline against the synthetic `examples/demo-client/` fixtures unless
noted. None of them call out to an LLM or to a vendor API; the
deterministic pack is the prerequisite, the LLM step is yours.

> Each recipe is roughly five to twenty lines of CLI plus a paragraph
> of context. None of them require code changes; they're combinations
> of the existing CLI verbs.

## Recipe 1: Onboard a new site in 30 minutes

When a new site lands on your desk and you need to understand it
before promising any deliverables.

```bash
# 0. Make sure you have a sitemap or a Screaming Frog export.
#    The toolkit reads either; pick whichever is faster to obtain.

# 1. Spin up the workspace.
site-context-pipeline init --client newsite --write

# 2. Point the inventory at the sitemap.
site-context-pipeline build-inventory \
    --client newsite \
    --source path/to/sitemap.xml \
    --format sitemap \
    --write

# 3. (optional) Layer in a Screaming Frog export to fill in titles,
#    H1s, status codes, and word counts on every URL.
#    Run only if you have it; the CSV alone is enough to start.
site-context-pipeline build-inventory \
    --client newsite \
    --source path/to/internal_html.csv \
    --format screaming-frog \
    --write

# 4. Pull internal links from the same Screaming Frog export.
site-context-pipeline build-link-graph \
    --client newsite \
    --source path/to/all_inlinks.csv \
    --format screaming-frog \
    --write

# 5. Build the pack.
site-context-pipeline build-context-pack --client newsite --write

# 6. Read the digest by eye.
cat clients/newsite/output/agent_context_pack.md
```

What you learn from `agent_context_pack.md` in the first read:

- the actual page-type mix (commercial vs blog vs landing) — usually
  surprising;
- which commercial pages get zero internal support from blog content;
- which blog posts are orphaned;
- which pattern rules misfire (`fallback_other` count is a useful
  smell).

Bring this to the kickoff call. You're starting the engagement with
facts, not assumptions.

## Recipe 2: Quarterly content audit

Run every quarter to catch drift: old posts losing inlinks, new
commercial pages launched without supporting content, classification
rules that no longer fit the site.

```bash
# Refresh the inventory and link graph from the latest sitemap and
# Screaming Frog export.
site-context-pipeline build-inventory \
    --client acme \
    --source latest/sitemap.xml \
    --format sitemap \
    --write

site-context-pipeline build-link-graph \
    --client acme \
    --source latest/all_inlinks.csv \
    --format screaming-frog \
    --write

# Refresh the demand and performance signals.
site-context-pipeline import-keywords \
    --client acme \
    --provider local-csv \
    --source latest/keyword_export.csv \
    --write

site-context-pipeline import-search-performance \
    --client acme \
    --provider local-gsc-csv \
    --source latest/gsc_export.csv \
    --write

# Rebuild the pack.
site-context-pipeline build-context-pack --client acme --write
```

Then look at three sections of `agent_context_pack.md`:

1. **Pages with rankings but weak internal support** — every entry
   here is a quick win. Add a few well-placed inlinks before chasing
   any new content.
2. **Commercial pages with no inlinks from blog posts** — these need
   editorial coverage, not more service-page edits.
3. **Pages with impressions but weak CTR** — these are title and meta
   problems, not content problems. Hand them to whoever owns metadata.

Diff the pack against last quarter's pack to see what moved. Because
the pack is deterministic, a Git diff between two `agent_context_pack.json`
files is meaningful — every changed field is real movement.

## Recipe 3: Find blog posts that should be services

Sometimes a blog post quietly becomes the best-performing entry point
for a commercial query. The toolkit makes that visible:

```bash
# Build everything as in Recipe 2.
site-context-pipeline build-inventory      --client acme --source ... --write
site-context-pipeline build-link-graph     --client acme --source ... --write
site-context-pipeline import-keywords      --client acme --provider local-csv \
    --source latest/keyword_export.csv --write
site-context-pipeline import-search-performance --client acme --provider local-gsc-csv \
    --source latest/gsc_export.csv --write
site-context-pipeline build-context-pack --client acme --write
```

Read `output/agent_context_pack.md` and look for the
**Pages with rankings but weak internal support** section. Cross-reference
the URLs with **Top keyword opportunities**. A blog post that:

- ranks for a high-volume commercial query, and
- gets few or no inlinks from the rest of the site

is a candidate for promotion to a landing or service page. The pack
gives you the evidence; the editorial decision is yours.

## Recipe 4: Pre-rebrand link-graph snapshot

Before a domain migration, slug rewrite, or large IA change, capture
a deterministic snapshot of the link graph so you can compare after.

```bash
# Snapshot before.
site-context-pipeline build-inventory --client acme --source pre/sitemap.xml --format sitemap --write
site-context-pipeline build-link-graph --client acme --source pre/all_inlinks.csv --format screaming-frog --write
git add clients/acme/data clients/acme/output
git commit -m "snapshot: pre-rebrand inventory + link graph"

# Do the rebrand.

# Snapshot after.
site-context-pipeline build-inventory --client acme --source post/sitemap.xml --format sitemap --write
site-context-pipeline build-link-graph --client acme --source post/all_inlinks.csv --format screaming-frog --write
git diff --stat clients/acme/data
git diff clients/acme/output/content_opportunities.md
```

What you're looking for:

- pages that **lost inlinks** in the move (broken or dropped links);
- pages that **changed page_type** (a blog that became a service or
  vice versa — the classifier reason in the inventory tells you why);
- new entries in `commercial_pages_low_blog_inlinks` that were
  supported before.

Because every artifact carries a `sources` map, anyone reviewing the
diff can trace each fact back to the input file that produced it.

## Recipe 5: Gate every draft with deterministic QA in CI

Wire the QA module into your CI so a Markdown draft is mechanically
checked before a human review starts.

```yaml
# .github/workflows/qa.yml in your content repo (not this one)
name: Draft QA
on:
  pull_request:
    paths: ["drafts/**.md"]

jobs:
  qa:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install site-context-pipeline
      - name: QA every changed draft
        run: |
          for f in $(git diff --name-only origin/main HEAD -- 'drafts/**.md'); do
            site-context-pipeline qa-draft --client acme --draft "$f" --write
          done
```

The CLI exits non-zero on any **red** finding (heading hierarchy,
keyphrase density, missing alt text, broken internal link, slug
shape) and writes a structured JSON report to
`<client>/output/qa_reports/<slug>.qa.json`. CI fails fast before a
human spends time reviewing prose.

## Recipe 6: Hand the pack to an LLM and demand citations

Once the pack is built, you can use it as a stable, machine-readable
input to any LLM-assisted content step. The trick is to demand
citations against the pack's own fields.

```text
You are an editor. Read the agent context pack below and produce a
brief for one new article. Constraints:

- Pick a query from `opportunities.top_keywords` that is not already
  covered by an existing page in `pages.blog`.
- Cite at least two existing pages by URL from the pack's `pages.*`
  arrays. Do not invent URLs.
- For every claim in the brief, point to a `sources.*` key the claim
  comes from.
- If a claim cannot be sourced from the pack, mark it as
  `unsourced` and explain what you would need to verify it.

[paste contents of clients/acme/output/agent_context_pack.json here]
```

Validate the LLM output structurally with the
[`agent_context_pack` JSON Schema](schemas.md) — refuse any draft
that drifts from the contract.

## Recipe 7: Compare two clients quickly

Working on multiple sites in the same niche? The deterministic format
makes side-by-side comparison cheap.

```bash
# Build packs for both.
site-context-pipeline build-context-pack --client siteA --write
site-context-pipeline build-context-pack --client siteB --write

# Diff just the summary blocks.
python -c "import json; \
    a=json.load(open('clients/siteA/output/agent_context_pack.json'))['summary']; \
    b=json.load(open('clients/siteB/output/agent_context_pack.json'))['summary']; \
    print('A:', json.dumps(a, indent=2)); \
    print('B:', json.dumps(b, indent=2))"
```

You can immediately see which site is heavier on blog vs commercial,
which has more orphans, which has more weak-CTR queries.

## Recipe 8: Audit classifier coverage

When `fallback_other` shows up in the inventory more than 5 % of
URLs, your classifier rules are out of date. Find the offending URLs
and patch the rules:

```bash
# Show every URL the classifier could not place.
python -c "import json; \
    inv=json.load(open('clients/acme/data/content_inventory.json')); \
    print('\n'.join(p['url'] for p in inv if p['page_type'] == 'other'))"
```

Patterns are easier to spot than to imagine. Patch
`config/classifier.json` with a new rule (see
[Classifier](classifier.md) for the schema), rerun
`build-inventory`, and watch the `classification.reasons` block
shrink the `fallback_other` count.

## Recipe 9: Run inside a private Docker image

For agencies that want a single tool image to use across clients,
the toolkit's offline-only design makes the Dockerfile trivial.

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir site-context-pipeline
WORKDIR /work
ENTRYPOINT ["site-context-pipeline"]
```

Mount your client workspace at `/work` and run any verb:

```bash
docker run --rm -v $PWD:/work scp:latest \
    build-context-pack --client acme --write
```

No credentials, no API keys, no network access required. The base
image is small because the wheel has zero runtime dependencies.

## Where to go next

- [Tutorial](tutorial.md) — the long-form walk-through that
  introduces every concept these recipes assume.
- [Classifier](classifier.md) — write your own classification rules.
- [QA](qa.md) — full reference of the deterministic QA checks.
- [JSON Schemas](schemas.md) — validate downstream consumers
  against the pack's contract.
- [Roadmap](roadmap.md) — what's coming in 0.4 (live API adapters
  behind extras).
