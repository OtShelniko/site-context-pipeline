"""Tests for the configurable classifier rules.

The original classifier accepts a flat list of ``(page_type, pattern)``
rules. This module covers the extended schema:

* explicit per-rule ``priority``;
* per-rule ``exclude_patterns`` for negation;
* per-rule ``allow_urls`` for explicit forced matches;
* fully-qualified ``classification_reason`` strings;
* graceful behaviour on malformed config (skip the bad rule, keep
  going).

The legacy schema (``{"rules": [...]}`` with bare ``page_type`` /
``pattern`` keys) must keep working unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.inventory import build_inventory


def _write_classifier(workspace: Path, payload: dict) -> None:
    cfg_path = workspace / "clients" / "demo" / "config" / "classifier.json"
    cfg_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_urls(workspace: Path, urls: list[str]) -> Path:
    csv_path = workspace / "urls.csv"
    rows = ["url"] + urls
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return csv_path


def test_legacy_flat_rules_still_work(tmp_path: Path) -> None:
    """Legacy schema: bare list of {page_type, pattern} dicts."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    _write_classifier(
        tmp_path,
        {
            "rules": [
                {"page_type": "blog", "pattern": "*/blog/*"},
                {"page_type": "service", "pattern": "*/services/*"},
            ]
        },
    )
    csv = _write_urls(
        tmp_path,
        [
            "https://example.com/blog/post/",
            "https://example.com/services/local/",
            "https://example.com/random/",
        ],
    )
    result = build_inventory(paths, write=False, source=csv)
    by_url = {item["url"]: item for item in result["items"]}
    assert by_url["https://example.com/blog/post/"]["page_type"] == "blog"
    assert by_url["https://example.com/services/local/"]["page_type"] == "service"
    assert by_url["https://example.com/random/"]["page_type"] == "other"


def test_explicit_priority_overrides_list_order(tmp_path: Path) -> None:
    """A rule with lower numeric priority fires first even if it appears
    later in the JSON list."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    _write_classifier(
        tmp_path,
        {
            "rules": [
                # Listed first but priority 50 — should lose to priority 10.
                {"page_type": "service", "pattern": "*/blog/*", "priority": 50},
                {"page_type": "blog", "pattern": "*/blog/*", "priority": 10},
            ]
        },
    )
    csv = _write_urls(tmp_path, ["https://example.com/blog/post/"])
    result = build_inventory(paths, write=False, source=csv)
    assert result["items"][0]["page_type"] == "blog"


def test_exclude_patterns_block_a_rule(tmp_path: Path) -> None:
    """A rule that matches /blog/* but excludes /blog/archive/* lets
    archive pages fall through to the next rule (or 'other')."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    _write_classifier(
        tmp_path,
        {
            "rules": [
                {
                    "page_type": "blog",
                    "pattern": "*/blog/*",
                    "exclude_patterns": ["*/blog/archive/*"],
                }
            ]
        },
    )
    csv = _write_urls(
        tmp_path,
        [
            "https://example.com/blog/post/",
            "https://example.com/blog/archive/2024/",
        ],
    )
    result = build_inventory(paths, write=False, source=csv)
    by_url = {item["url"]: item for item in result["items"]}
    assert by_url["https://example.com/blog/post/"]["page_type"] == "blog"
    assert by_url["https://example.com/blog/archive/2024/"]["page_type"] == "other"


def test_allow_urls_forces_match_even_against_pattern(tmp_path: Path) -> None:
    """A rule with `allow_urls` always fires for those URLs, regardless
    of `pattern`. The `classification_reason` says so."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    _write_classifier(
        tmp_path,
        {
            "rules": [
                {
                    "page_type": "service",
                    "pattern": "*/services/*",
                    "allow_urls": ["https://example.com/special-page/"],
                }
            ]
        },
    )
    csv = _write_urls(
        tmp_path,
        [
            "https://example.com/services/local/",
            "https://example.com/special-page/",
        ],
    )
    result = build_inventory(paths, write=False, source=csv)
    by_url = {item["url"]: item for item in result["items"]}
    assert by_url["https://example.com/services/local/"]["page_type"] == "service"
    special = by_url["https://example.com/special-page/"]
    assert special["page_type"] == "service"
    assert "matched_allow_url" in special["classification_reason"]


def test_classification_reason_includes_pattern(tmp_path: Path) -> None:
    """The reason string must let an auditor tell which pattern fired
    (so they can change it later without guessing)."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    _write_classifier(
        tmp_path,
        {"rules": [{"page_type": "blog", "pattern": "*/blog/*"}]},
    )
    csv = _write_urls(tmp_path, ["https://example.com/blog/post/"])
    result = build_inventory(paths, write=False, source=csv)
    reason = result["items"][0]["classification_reason"]
    assert reason == "matched_pattern:*/blog/*"


def test_multiple_priorities_with_ties_preserve_list_order(tmp_path: Path) -> None:
    """When two rules share the same priority, the one that appears
    earlier in the list wins. Predictable order matters for audits."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    _write_classifier(
        tmp_path,
        {
            "rules": [
                {"page_type": "category", "pattern": "*/x/*", "priority": 10},
                {"page_type": "service", "pattern": "*/x/*", "priority": 10},
            ]
        },
    )
    csv = _write_urls(tmp_path, ["https://example.com/x/y/"])
    result = build_inventory(paths, write=False, source=csv)
    assert result["items"][0]["page_type"] == "category"


def test_negation_then_fallback_to_pattern(tmp_path: Path) -> None:
    """If rule A excludes a URL and rule B matches it, the URL gets
    rule B's page_type."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    _write_classifier(
        tmp_path,
        {
            "rules": [
                {
                    "page_type": "blog",
                    "pattern": "*/blog/*",
                    "exclude_patterns": ["*/blog/archive/*"],
                    "priority": 10,
                },
                {
                    "page_type": "category",
                    "pattern": "*/blog/archive/*",
                    "priority": 20,
                },
            ]
        },
    )
    csv = _write_urls(
        tmp_path,
        [
            "https://example.com/blog/post/",
            "https://example.com/blog/archive/2024/",
        ],
    )
    result = build_inventory(paths, write=False, source=csv)
    by_url = {item["url"]: item for item in result["items"]}
    assert by_url["https://example.com/blog/post/"]["page_type"] == "blog"
    assert by_url["https://example.com/blog/archive/2024/"]["page_type"] == "category"


def test_unknown_page_type_is_skipped_with_warning(tmp_path: Path) -> None:
    """A misspelled page_type does not crash the build; the rule is
    skipped with a warning so the rest of the rule set still works."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    _write_classifier(
        tmp_path,
        {
            "rules": [
                {"page_type": "blogg", "pattern": "*/blog/*"},  # typo
                {"page_type": "service", "pattern": "*/services/*"},
            ]
        },
    )
    csv = _write_urls(
        tmp_path,
        [
            "https://example.com/blog/post/",
            "https://example.com/services/local/",
        ],
    )
    result = build_inventory(paths, write=False, source=csv)
    by_url = {item["url"]: item for item in result["items"]}
    # The bad rule is skipped, so the blog URL falls through to 'other'.
    assert by_url["https://example.com/blog/post/"]["page_type"] == "other"
    assert by_url["https://example.com/services/local/"]["page_type"] == "service"
    # The warning surfaces somewhere in the inventory output.
    assert any("classifier_rule_invalid_page_type" in w for w in result["warnings"])


def test_invalid_classifier_json_falls_back_to_defaults(tmp_path: Path) -> None:
    """If the file exists but is not a JSON object, we keep going with
    the built-in rules and emit a warning."""
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    (paths.config / "classifier.json").write_text("not json", encoding="utf-8")
    csv = _write_urls(tmp_path, ["https://example.com/blog/post/"])
    result = build_inventory(paths, write=False, source=csv)
    # Built-in pattern catches /blog/.
    assert result["items"][0]["page_type"] == "blog"
    assert any("classifier_json_invalid" in w for w in result["warnings"])


def test_empty_rules_falls_back_to_defaults(tmp_path: Path) -> None:
    paths = get_client_paths("demo", workspace=tmp_path)
    init_client(paths, write=True)
    _write_classifier(tmp_path, {"rules": []})
    csv = _write_urls(tmp_path, ["https://example.com/blog/post/"])
    result = build_inventory(paths, write=False, source=csv)
    # Built-in pattern catches /blog/ because the user supplied no rules.
    assert result["items"][0]["page_type"] == "blog"
    assert any("classifier_json_empty_using_defaults" in w for w in result["warnings"])
