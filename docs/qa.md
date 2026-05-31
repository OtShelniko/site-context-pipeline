# Content QA

The `qa-draft` command runs a deterministic, offline check over a
Markdown article and reports red/orange/green findings. There is no
LLM involvement: every check is regex + standard library, and the
result is reproducible.

This is a pre-publish gate, not a writing tool. The toolkit reports
problems; fixing them is the writer's job.

## Usage

```bash
site-context-pipeline qa-draft \
    --client demo \
    --draft path/to/article.md
```

The command reads `clients/<id>/data/content_inventory.json` (when it
exists) so internal-link checks know which URLs are part of the site.
With `--write`, the report is also persisted to
`clients/<id>/output/qa_reports/<slug>.qa.json`.

Exit code is `0` when no red findings exist, `1` otherwise — useful
for CI gates.

### Required inputs

The QA module needs a keyphrase. It looks in three places, in this
order:

1. `--keyphrase ...` flag.
2. `keyphrase:` in YAML frontmatter at the top of the draft.
3. `main_keyword:` in YAML frontmatter (legacy alias).

If none of these is set, the command exits with a clean error rather
than running with a blank keyphrase.

### Optional inputs

* `--slug ...` — overrides `slug:` in frontmatter. Used for the slug
  / keyphrase overlap check.

## Checks shipped in 0.x

| Name | Triggers red when |
|---|---|
| `single_h1` | Draft has zero or more than one `# H1` heading. |
| `heading_hierarchy` | Heading levels jump by more than one (e.g. H1 → H4). |
| `keyphrase_in_h1` | The H1 does not contain the keyphrase. |
| `keyphrase_density` | Keyphrase appears 0 times in the body (1–2 times = orange). |
| `intro_length` | Intro (text under H1, before first H2) is empty or near-empty (< 5 words). 5–29 words = orange; ≥ 30 = green. |
| `competing_anchors` | Any internal link uses the keyphrase as exact anchor text. |
| `image_alt` | Any image has empty alt text. |
| `links_resolve` | An internal link points at a URL not in the inventory (only when an inventory is loaded). |
| `slug_keyphrase` | Slug shares no token with the keyphrase. |

Each finding carries a `details` dict with diagnostic data so the
operator can see *why* the check fired.

## Output shape

```json
{
  "keyphrase": "how to plan delivery",
  "slug": "how-to-plan-delivery",
  "overall_level": "green",
  "findings": [
    {
      "name": "single_h1",
      "level": "green",
      "message": "Exactly one H1 heading.",
      "details": { "count": 1 }
    },
    {
      "name": "keyphrase_in_h1",
      "level": "green",
      "message": "H1 contains the keyphrase.",
      "details": { "h1": "How to plan delivery", "keyphrase": "how to plan delivery" }
    },
    ...
  ]
}
```

The schema is stable across releases — add new fields, do not rename
or remove existing ones. CI can grep for finding names and `level`
values to gate publishing.

## Library API

If you want to embed the QA module in a custom workflow, call the
two pure functions directly:

```python
from site_context_pipeline.qa import analyse_draft, analyse_draft_file

report = analyse_draft_file(
    "drafts/article.md",
    inventory_urls={
        "https://example.com/services/",
        "https://example.com/services/local-delivery/",
    },
)
print(report.overall_level, len(report.findings))

# Or feed a string directly:
report = analyse_draft(
    "# Hello\n\nbody",
    keyphrase="hello",
    inventory_urls=set(),
)
```

`QAReport.to_dict()` produces the same JSON-serialisable shape the
CLI prints.

## What the QA module will *not* do

- It will not fix any finding for you. The toolkit reports; the
  writer (or a downstream LLM the operator chooses to wire up)
  rewrites.
- It will not check facts. Whether a sentence is *true* is out of
  scope — the QA module checks structural and SEO-craft signals only.
- It will not call any vendor API. Every rule is local.

## Adding a new rule

1. Implement a function `_check_<name>(...)` in `qa.py` that returns
   a `QAFinding`.
2. Call it from `analyse_draft` and append the result to `findings`.
3. Add a fixture under `tests/fixtures/qa/` whose filename advertises
   the rule (`red_<name>.md` for a red trigger, `orange_<name>.md`
   for orange).
4. Add a test in `tests/test_qa.py` that asserts the finding's
   level for that fixture.
5. Document the rule in this file and bump the table above.
