# Security Policy

## Supported versions

The project is in early alpha (`0.x`). Only the latest minor version receives
security fixes.

## Reporting a vulnerability

Please **do not open a public issue** for security reports.

Send a private email to the maintainer listed on the project's GitHub page
with:

- A description of the issue.
- The steps to reproduce.
- The smallest possible test case.
- Your assessment of impact (data exposure, code execution, etc.).

You should expect an acknowledgement within five working days. We will
coordinate a fix and disclosure timeline with you.

## Threat model

This project is an **offline CLI** that reads local files and writes local
files. The 0.1 core has zero network dependencies. Things to keep in mind:

- **Untrusted input data.** Inventory CSV/JSON files are user-controlled. The
  toolkit treats them as data, never executes code from them, and never echoes
  them back as shell input. Reports of injection through input files are
  in scope.
- **Path handling.** All file writes happen under
  `clients/<client>/{data,output,logs}`. Reports of path traversal (e.g.
  `--client ../../etc`) are in scope.
- **Future network adapters.** When optional adapters (LLM, SERP, Wordstat)
  are added, they will read API keys from environment variables or local
  `.env` files. The keys must never be logged or written to artifacts.
  Reports of secret leakage are in scope.

## Out of scope

- Bugs in third-party services that this toolkit may eventually call.
- Misuse of the tool to scrape sites the user does not own. The CLI itself
  performs no crawling in 0.1.
