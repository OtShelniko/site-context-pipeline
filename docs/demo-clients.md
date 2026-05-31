# Demo clients

The toolkit ships two synthetic demo workspaces under `examples/`. They
exist to exercise the full pipeline end-to-end without any real client
data, and to act as concrete starting points for new users.

Both demos are completely synthetic. None of the URLs resolve; none of
the keyword volumes or Search-Console rows correspond to any real
business; none of the company or product names are real.

## `examples/demo-client/` — small services site

The original demo. A fictional delivery company "Example Co" with:

- 8 pages on `example.com`
- 6 internal links
- Mix of home, services, blog posts, and a pricing page
- 6 keyword rows and 6 Search-Console rows
- 3 hand-curated SERP-evidence queries
- A short `project.md` describing the imaginary business

This demo is the one used in the
[Tutorial](tutorial.md), in `tests/conftest.py`, and in every
README quickstart snippet.

Use this demo when you want to see the simplest path through the
pipeline.

## `examples/demo-ecommerce/` — coffee-equipment storefront

The second demo, added in 0.4. A fictional coffee-equipment retailer
"Shop Example" with:

- 14 pages on `shop.example.com`
- 15 internal links
- A deeper IA: home → category → subcategory → product, plus a small
  blog supporting the storefront, plus `cart` / `checkout` / `about` /
  `shipping`
- 7 keyword rows weighted toward purchase intent ("buy", "best",
  "shop")
- 7 Search-Console rows including high-CTR purchase queries and
  weak-CTR informational ones
- 4 hand-curated SERP queries showing the mix of categories,
  articles, and price-comparison tools competitors rank with
- A `config/classifier.json` showing **priority**, `allow_urls`, and
  pattern overrides — the e-commerce classifier ruleset

Use this demo when you want to see how the toolkit handles:

- product vs category disambiguation,
- promotion of specific category URLs to `landing` via
  `commercial_urls.json`,
- a `*/cart/*` rule that uses `allow_urls` to keep specific URLs in
  scope while everything else under `cart` is demoted to `other`.

After running every CLI verb against this demo, the resulting pack
shows the kind of opportunities every storefront has: category pages
with weak internal support from blog content, product pages
inheriting only one inlink, blog posts that already rank for
informational queries but receive no inlinks from product or
category pages.

## Running either demo end-to-end

Both demos use the same CLI commands. Substitute `<demo>` with
`demo-client` or `demo-ecommerce`:

```bash
# Initialise a separate workspace per demo so they don't collide.
site-context-pipeline init --client <demo> --write

# Inventory + link graph.
site-context-pipeline build-inventory  --client <demo> \
    --source examples/<demo>/input/urls.csv  --write
site-context-pipeline build-link-graph --client <demo> \
    --source examples/<demo>/input/links.csv --write

# Optional: keyword + GSC + SERP evidence.
site-context-pipeline import-keywords           --client <demo> \
    --provider local-csv      --source examples/<demo>/input/keyword_metrics.csv --write
site-context-pipeline import-search-performance --client <demo> \
    --provider local-gsc-csv  --source examples/<demo>/input/search_console.csv --write
site-context-pipeline import-search-evidence    --client <demo> \
    --provider local-serp-csv --source examples/<demo>/input/search_evidence.csv --write

# Aggregate.
site-context-pipeline build-context-pack --client <demo> --write

# Inspect.
site-context-pipeline inspect --client <demo>
```

After the last command, `clients/<demo>/output/agent_context_pack.md`
holds the human-readable digest and `agent_context_pack.json` holds
the machine-readable twin. `output/content_opportunities.md` is the
shortlist of editorial gaps the pipeline detected.

## Adding a third demo

If you have an interesting niche (multilingual, B2B service catalog,
SaaS knowledge base, marketplace) and want to contribute a demo:

1. Create `examples/demo-<niche>/` mirroring the layout of the two
   existing demos.
2. Keep every URL under a clearly-fictional domain
   (`shop.example.com`, `docs.example.org`, `mkt.example.net`, etc.).
3. Keep keyword rows synthetic. Do not paste in real volumes from
   any tool.
4. Add a short `project.md` explaining the imagined site.
5. Open a PR with the new demo and a paragraph here explaining what
   the demo exercises.

The smaller the demo, the better — both shipped demos are under 20
pages each, and that is plenty to exercise every code path.
