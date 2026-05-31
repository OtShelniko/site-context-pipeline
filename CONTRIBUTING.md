# Contributing to site-context-pipeline

Thanks for your interest. This project values small, well-scoped contributions
that keep the toolkit honest: a structured site-context pipeline, not an
auto-publish SEO bot.

## Ground rules

1. **No client data.** Pull requests must not include real domains, real
   keyword lists, real briefs, scraped HTML, API keys, or business identifiers.
   Use the synthetic demo client (`examples/demo-client/`) for fixtures.
2. **No silent network calls.** The 0.1 core is standard-library only and
   stays offline. Network adapters (Wordstat, SERP, LLMs, image APIs) belong
   behind explicit opt-in flags and optional extras, in separate modules with
   clear interfaces.
3. **Tests for new behavior.** If you add a classifier rule, an artifact
   field, or a CLI flag, add a unit test under `tests/`. Tests must run with
   no internet access.
4. **Backwards-compatible JSON schemas.** `data/*.json` and
   `output/agent_context_pack.json` are public contracts. Add fields, do not
   rename or remove them. Bump `schema_version` when shape changes.

## Local setup

```bash
python -m venv .venv
. .venv/Scripts/activate     # Windows
# . .venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"
```

## Running checks

```bash
ruff check .
pytest
```

CI runs the same commands on Python 3.11.

## Filing issues

When reporting a bug, please include:

- Python version and OS.
- The exact command you ran.
- The shape of your input data (URL count, columns present). Do not paste
  real client data — synthesize a minimal failing example.
- The relevant snippet of the JSON output, with sensitive values redacted.

## Pull requests

- Keep the diff focused. One feature or fix per PR.
- Update `README.md` if you add or change a CLI command or artifact field.
- If a change deserves a roadmap item, edit the Roadmap section in
  `README.md` rather than adding new top-level documents.
