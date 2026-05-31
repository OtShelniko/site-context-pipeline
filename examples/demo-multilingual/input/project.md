# Project notes — demo-multilingual

A third synthetic example for the test suite and documentation. The
fictional SaaS product "TaskFlow" publishes its documentation and
marketing pages in three languages on a fictional `docs.example.org`
domain.

This demo exercises an information architecture the English-only
demos do not: locale-prefixed URL trees (`/en/`, `/de/`, `/fr/`),
the same logical page type expressed through localized slugs
(`pricing` ≡ `preise` ≡ `tarifs`; `guides` ≡ `anleitungen`), and
keyword/Search-Console rows that span three markets with distinct
`geo`, `language`, and `locale` values.

The toolkit's core is deliberately language-neutral: it classifies
on URL structure and carries `geo` / `language` / `locale` straight
through to the keyword artifact without interpreting them. This demo
shows that a single workspace can hold a multi-market site without
the pipeline needing to "understand" any particular language.

These notes are reproduced verbatim in the agent context pack. Keep
this file short and factual.

- Audience: ops and engineering teams evaluating task-automation
  tooling in the US, German, and French markets.
- Tone: neutral, documentation-style, no marketing superlatives.
- Out of scope: machine translation quality, hreflang validation
  (the toolkit reports structure, not translation correctness).
