# Classifier rules

The inventory builder classifies every URL into one of six page types:
``home``, ``service``, ``blog``, ``category``, ``landing``, ``other``.
The result lands in ``data/content_inventory.json`` and drives
downstream artefacts (link graph opportunities, the context pack's
"pages by type" section, etc.).

The toolkit ships a built-in rule set that handles common URL shapes
(``/blog/``, ``/services/``, ``/category/``, ``/pricing``, …). When
your site uses a different convention, drop a
``clients/<id>/config/classifier.json`` into the workspace.

## Resolution order

For each URL, the classifier checks in this order:

1. **Explicit commercial URL list** — the URL appears in
   ``config/commercial_urls.json``. The page type becomes ``landing``;
   the reason becomes ``matched_commercial_url_list``.
2. **Home page** — the URL's path is ``/`` or empty. The page type
   becomes ``home``; the reason becomes ``matched_home_path``.
3. **Per-rule allow lists** — any rule with the URL in its
   ``allow_urls`` fires regardless of ``pattern``. The reason becomes
   ``matched_allow_url:<page_type>``.
4. **Pattern rules** — evaluated in priority order (lowest number
   first; ties broken by list order). A rule's ``exclude_patterns``
   block the match; the next rule then gets a chance. The reason
   becomes ``matched_pattern:<pattern>``.
5. **Fallback** — nothing matched. Page type ``other``, reason
   ``fallback_other``.

The reason string is part of the public artefact contract — write
audits and dashboards against it.

## Schema

### Minimal (legacy, still supported)

```json
{
  "rules": [
    { "page_type": "blog",    "pattern": "*/blog/*"     },
    { "page_type": "service", "pattern": "*/services/*" },
    { "page_type": "landing", "pattern": "*/pricing*"   }
  ]
}
```

First match wins. Identical to how the toolkit shipped before this
schema was extended.

### Extended

Every rule may carry the same two required fields plus three optional
fields:

| Field | Type | Default | Notes |
|---|---|---|---|
| `page_type` | string | required | One of `home`, `service`, `blog`, `category`, `landing`, `other`. Unknown values skip the rule with a warning. |
| `pattern` | string | required | Glob with `*` wildcards. Matched against the URL's path (lower-cased). |
| `priority` | int | `100` | Lower wins. Ties broken by the rule's position in the JSON list, so the order in your file still matters. |
| `exclude_patterns` | list of glob strings | `[]` | If any of these matches, the rule is skipped and the *next* rule (in priority order) gets a chance. |
| `allow_urls` | list of full URLs | `[]` | If the URL is on this list, the rule fires unconditionally — the pattern is ignored. Useful for one-off promotions of a specific URL. |

```json
{
  "rules": [
    {
      "page_type": "blog",
      "pattern": "*/blog/*",
      "priority": 10,
      "exclude_patterns": ["*/blog/archive/*"]
    },
    {
      "page_type": "category",
      "pattern": "*/blog/archive/*",
      "priority": 20
    },
    {
      "page_type": "service",
      "pattern": "*/services/*",
      "priority": 30,
      "allow_urls": [
        "https://example.com/special-bundle/"
      ]
    },
    {
      "page_type": "landing",
      "pattern": "*/pricing*",
      "priority": 40
    }
  ]
}
```

Reading this:

* All `/blog/...` URLs are blogs (priority 10), *except* those under
  `/blog/archive/` — those are caught by the next rule and become
  categories.
* All `/services/...` URLs are services. So is the one-off
  `/special-bundle/` URL, even though it does not look like a
  services URL — it is allow-listed.
* All `/pricing*` URLs are landings.

## How invalid input is handled

The toolkit prefers to keep going. Each invalid rule is skipped and
recorded in the inventory's ``warnings`` list:

| Symptom | Warning token |
|---|---|
| Rule entry is not a JSON object | `classifier_rule_not_object:index=N` |
| Rule missing `page_type` or `pattern` | `classifier_rule_missing_fields:index=N` |
| Rule has an unknown `page_type` | `classifier_rule_invalid_page_type:index=N,value=X` |
| Rule has a non-int `priority` | `classifier_rule_invalid_priority:index=N` |
| Rule has a non-list `exclude_patterns` | `classifier_rule_invalid_exclude_patterns:index=N` |
| Rule has a non-list `allow_urls` | `classifier_rule_invalid_allow_urls:index=N` |
| Whole file is not valid JSON | `classifier_json_invalid` (built-in defaults used) |
| File is JSON but `rules` is empty | `classifier_json_empty_using_defaults` |

These warnings appear inside the inventory's standard CLI payload so
they are visible in CI logs and easy to grep.

## When to use the extended schema

* **Negation** (`exclude_patterns`) — when a single broad pattern
  almost works but you have a sub-tree that needs different
  treatment. Example: blog posts are at `/blog/*`, but legacy
  archives at `/blog/archive/*` should be treated as categories.
* **Forced matches** (`allow_urls`) — when a single URL does not fit
  any pattern but you know it belongs to a specific type. Example: a
  high-priority landing page that lives at the site root.
* **Explicit priority** — when you mix narrow and broad rules and
  want the narrow ones to win regardless of file order. Example: a
  more specific `/services/local-delivery/*` rule with priority 10
  that beats a generic `/services/*` rule with priority 50.

If none of these apply, the legacy flat schema is fine — keep it.
