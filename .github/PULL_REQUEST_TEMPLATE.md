<!--
Thank you for contributing! A few quick checks before you submit.
-->

## Summary

<!-- One or two sentences. What changes, and why? -->

## Type of change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] New provider adapter (must follow `docs/providers.md` safety rules)
- [ ] Documentation only
- [ ] Tests / CI / tooling

## Checklist

- [ ] No real client data, real domains, real keyword lists, or API keys in
      this PR. Synthetic `example.com` data only.
- [ ] No new runtime dependencies in the base install. Optional adapters
      use `[project.optional-dependencies]`.
- [ ] Tests run **offline**. No live network calls; no credentials needed.
- [ ] Added tests for new behavior (if applicable).
- [ ] Updated `README.md`, `docs/`, or `ROADMAP.md` if user-visible.
- [ ] `ruff check .` passes locally.
- [ ] `pytest` passes locally.
- [ ] If artifact JSON shape changed, bumped `schema_version` and noted
      it in `CHANGELOG.md`.

## Related issues

<!-- e.g. "Closes #12" -->
