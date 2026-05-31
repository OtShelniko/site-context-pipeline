# Bootstrap GitHub UI items that cannot live in the repo.
#
# Prereqs:
#   1. `gh` CLI installed (https://cli.github.com).
#   2. Authenticated with WRITE scopes:
#         gh auth refresh -h github.com -s repo,write:org
#      The default `gh auth login` flow may issue a read-only fine-grained
#      token; that one can list things but cannot create releases, issues,
#      or labels and cannot edit the repo description.
#   3. Run from the repository root:
#         powershell -ExecutionPolicy Bypass -File .github\bootstrap-github.ps1
#
# What this does (idempotent — safe to re-run):
#   - sets the repo description, homepage, and topics,
#   - ensures the standard labels exist,
#   - opens the v0.1 follow-up issues (skips ones that already exist),
#   - creates the v0.1.0 git tag and the GitHub release.
#
# It does NOT push code, does NOT touch the working tree, and does NOT
# enable any GitHub feature you have not already enabled.

$ErrorActionPreference = 'Stop'

$repo = 'OtShelniko/site-context-pipeline'
$description = 'Offline-first CLI for building structured site context packs for human-reviewed LLM-assisted content workflows.'
$homepage = "https://github.com/$repo"
$topics = @(
    'python',
    'cli',
    'llm',
    'seo',
    'content-workflow',
    'context-engineering',
    'search-console',
    'open-source'
)

function Invoke-GhSafe {
    param(
        [Parameter(Mandatory)] [string] $Label,
        [Parameter(Mandatory)] [scriptblock] $Action
    )
    try {
        & $Action
        return $true
    } catch {
        Write-Host "    skipped ($Label): $($_.Exception.Message.Trim())" -ForegroundColor Yellow
        return $false
    }
}

# ---------------------------------------------------------------------------
# Repo metadata
# ---------------------------------------------------------------------------

Write-Host '==> Setting repo description, homepage, and topics' -ForegroundColor Cyan
$null = Invoke-GhSafe 'description/homepage' { gh repo edit $repo --description $description --homepage $homepage 2>&1 | Out-Null }
$null = Invoke-GhSafe 'topics' { gh repo edit $repo --add-topic ($topics -join ',') 2>&1 | Out-Null }

# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

$labels = @(
    @{ name = 'good first issue'; color = '7057ff'; description = 'Good for newcomers' },
    @{ name = 'help wanted';      color = '008672'; description = 'Extra attention is needed' },
    @{ name = 'roadmap';          color = '0e8a16'; description = 'Tracked in ROADMAP.md' },
    @{ name = 'provider';         color = '5319e7'; description = 'New or improved provider adapter' },
    @{ name = 'enhancement';      color = 'a2eeef'; description = 'New feature or request' },
    @{ name = 'bug';              color = 'd73a4a'; description = 'Something is not working' },
    @{ name = 'documentation';    color = '0075ca'; description = 'Improvements or additions to docs' }
)

Write-Host '==> Ensuring labels exist' -ForegroundColor Cyan

# Read all labels once so we don't fight with shell-quoting per-name.
$existingLabelsJson = ''
try {
    $existingLabelsJson = gh label list --repo $repo --json name --limit 200 2>&1 | Out-String
} catch {
    Write-Host "    could not list labels: $($_.Exception.Message.Trim())" -ForegroundColor Yellow
}
$existingNames = @()
if ($existingLabelsJson) {
    try {
        $existingNames = ($existingLabelsJson | ConvertFrom-Json).name
    } catch {
        $existingNames = @()
    }
}

foreach ($label in $labels) {
    $alreadyThere = $existingNames -contains $label.name
    if ($alreadyThere) {
        $ok = Invoke-GhSafe "edit '$($label.name)'" {
            gh label edit $label.name --repo $repo --color $label.color --description $label.description 2>&1 | Out-Null
        }
        if ($ok) { Write-Host "    updated: $($label.name)" }
    } else {
        $ok = Invoke-GhSafe "create '$($label.name)'" {
            gh label create $label.name --repo $repo --color $label.color --description $label.description 2>&1 | Out-Null
        }
        if ($ok) { Write-Host "    created: $($label.name)" }
    }
}

# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

$issues = @(
    @{
        title = 'Add sitemap XML importer'
        labels = @('enhancement', 'roadmap', 'help wanted', 'good first issue')
        body = @'
Add a `sitemap_xml` importer so users do not have to hand-craft `urls.csv`.

**Goal**

Read one or more local `sitemap.xml` files (and sitemap-index files) and
produce the same row shape `build-inventory` accepts today.

**Scope**

- New module `src/site_context_pipeline/importers/sitemap_xml.py`.
- Pure stdlib (`xml.etree.ElementTree`). No new runtime dependency.
- New CLI flag: `site-context-pipeline build-inventory --source <path> --format sitemap`.
- Synthetic fixture under `tests/fixtures/sitemap_*.xml`.
- Unit tests for: single sitemap, sitemap index pointing at multiple
  child sitemaps, malformed XML, empty sitemap.

**Out of scope**

- HTTP fetching of remote sitemaps. The 0.x core stays offline.

See `ROADMAP.md` (0.2) for context.
'@
    },
    @{
        title = 'Add Screaming Frog CSV importer'
        labels = @('enhancement', 'roadmap', 'help wanted')
        body = @'
Accept Screaming Frog's canonical exports without a manual reshape step.

**Goal**

Read `internal_*.csv` (URL inventory) and `*_inlinks.csv` /
`*_outlinks.csv` (edge data) directly into the toolkit's existing
`content_inventory.json` / `internal_link_graph.json` shapes.

**Scope**

- New module `src/site_context_pipeline/importers/screaming_frog.py`.
- New `--format screaming-frog` flag on `build-inventory` and
  `build-link-graph`.
- Synthetic CSV fixtures under `tests/fixtures/screaming_frog/`.
- Unit tests for column-alias detection (Screaming Frog renames columns
  between major versions).

See `ROADMAP.md` (0.2) for context.
'@
    },
    @{
        title = 'Add search evidence CSV provider'
        labels = @('enhancement', 'roadmap', 'provider', 'help wanted')
        body = @'
Add the first `SearchEvidenceProvider` so users can capture top-N organic
results for a query without scraping.

**Goal**

A `local-serp-csv` provider that reads a hand-curated CSV with columns
`query`, `rank`, `title`, `url`, `snippet`, `page_type` and emits
`SearchEvidence` rows into `data/search_evidence.json`.

**Scope**

- Finalise the abstract base in `providers/base.py`
  (the row schema is already in `schemas.py`).
- New provider module `providers/local_serp_csv.py`.
- New CLI verb `import-search-evidence`.
- Update `context_pack.py` to surface a "What competitors do" summary
  when the artifact exists. No scraping. Strictly local.
- Tests covering empty input, mixed page types, and the offline-only
  invariant.

See `ROADMAP.md` (0.3) for context.
'@
    },
    @{
        title = 'Improve configurable classifier rules'
        labels = @('enhancement', 'roadmap', 'help wanted')
        body = @'
Promote the built-in URL pattern list to a fully data-driven config so
clients with unusual URL structures do not need to fork.

**Goal**

`config/classifier.json` should support:

- ordered rules with explicit priorities,
- negation patterns (skip URLs matching X even if rule Y would have fired),
- explicit URL allow/deny lists per page type,
- stable, audit-friendly `classification_reason` strings.

**Scope**

- Extend `inventory.py::classify_url` to read merged rules from
  defaults + per-client config.
- Document the schema in `docs/classifier.md` (new file).
- Tests covering each rule kind plus precedence between explicit URLs
  and patterns.

**Out of scope**

- Machine-learning-based classification. Rules stay deterministic.

See `ROADMAP.md` (0.2) for context.
'@
    },
    @{
        title = 'Add deterministic QA module'
        labels = @('enhancement', 'roadmap', 'help wanted')
        body = @'
Add an offline content-QA module that checks Markdown drafts against the
site context pack — no LLM involvement.

**Goal**

A new CLI verb `qa-draft --draft <path>` that reads a Markdown article
plus the existing `agent_context_pack.json` and reports red/orange/green
findings on:

- keyphrase distribution,
- main keyword in H1,
- internal-link sanity (anchors not equal to the keyphrase, all links
  resolve to URLs in the inventory),
- slug shape,
- heading hierarchy (single H1, no H4 jumps),
- missing `alt` text.

**Scope**

- New module `src/site_context_pipeline/qa.py`.
- Output: structured JSON on stdout plus an optional
  `output/qa_reports/<draft>.qa.json`.
- 10-15 fixture drafts under `tests/fixtures/qa/`, each red on exactly
  one rule.

**Out of scope**

- Calling an LLM to "fix" anything. The QA module reports; it does not
  rewrite.

See `ROADMAP.md` (0.3) for context.
'@
    }
)

Write-Host '==> Opening roadmap issues' -ForegroundColor Cyan

$existingTitlesJson = ''
try {
    $existingTitlesJson = gh issue list --repo $repo --state all --limit 200 --json number,title 2>&1 | Out-String
} catch {
    Write-Host "    could not list issues: $($_.Exception.Message.Trim())" -ForegroundColor Yellow
}
$existingTitles = @()
if ($existingTitlesJson) {
    try {
        $existingTitles = ($existingTitlesJson | ConvertFrom-Json).title
    } catch {
        $existingTitles = @()
    }
}

foreach ($issue in $issues) {
    if ($existingTitles -contains $issue.title) {
        Write-Host "    skipped (already exists): $($issue.title)"
        continue
    }
    $bodyFile = New-TemporaryFile
    Set-Content -Path $bodyFile -Value $issue.body -Encoding utf8
    $labelArgs = @()
    foreach ($label in $issue.labels) {
        $labelArgs += '--label'
        $labelArgs += $label
    }
    $ok = Invoke-GhSafe "create '$($issue.title)'" {
        gh issue create --repo $repo --title $issue.title --body-file $bodyFile @labelArgs 2>&1 | Out-Null
    }
    Remove-Item $bodyFile
    if ($ok) { Write-Host "    created: $($issue.title)" }
}

# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------

Write-Host '==> Ensuring v0.1.0 tag and release exist' -ForegroundColor Cyan

$tagExists = git tag -l v0.1.0
if (-not $tagExists) {
    git tag -a v0.1.0 -m 'site-context-pipeline 0.1.0'
    git push origin v0.1.0
    Write-Host '    tag v0.1.0 created and pushed'
} else {
    Write-Host '    tag v0.1.0 already exists'
}

$releaseCheck = gh release view v0.1.0 --repo $repo 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host '    release v0.1.0 already exists'
} else {
    $ok = Invoke-GhSafe 'release v0.1.0' {
        gh release create v0.1.0 `
            --repo $repo `
            --title 'v0.1.0 — initial public release' `
            --notes-file '.github/RELEASE_NOTES_v0.1.0.md' `
            --latest 2>&1 | Out-Null
    }
    if ($ok) { Write-Host '    release v0.1.0 created' }
}

Write-Host ''
Write-Host 'Done. Verify on GitHub:' -ForegroundColor Green
Write-Host "  https://github.com/$repo"
Write-Host "  https://github.com/$repo/issues"
Write-Host "  https://github.com/$repo/releases"
