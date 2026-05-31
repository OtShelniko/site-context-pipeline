"""Targeted edge-case tests for the lower-covered modules.

These exercise the error and fallback branches that the happy-path
end-to-end tests skip: missing/unsupported sources, malformed config,
classifier-rule validation warnings, and the small coercion helpers.
Each test is deliberately narrow so a coverage regression points
straight at the offending branch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from site_context_pipeline.clients import get_client_paths, init_client
from site_context_pipeline.inventory import (
    ClassifierRule,
    _coerce_url,
    _int_or_none,
    _load_classifier_rules,
    _read_source,
    _string_or_none,
    build_inventory,
)
from site_context_pipeline.link_graph import (
    _int_or_zero,
    _normalise_optional,
    build_link_graph,
)
from site_context_pipeline.link_graph import (
    _read_source as _read_link_source,
)
from site_context_pipeline.providers.base import ProviderConfigurationError
from site_context_pipeline.providers.local_search_console_csv import (
    LocalSearchConsoleCsvProvider,
)

# ---------------------------------------------------------------------------
# inventory._read_source — format selection and error branches
# ---------------------------------------------------------------------------


def test_inventory_read_source_missing_path_returns_warning() -> None:
    rows, fmt, warnings = _read_source(None, None)
    assert rows == []
    assert fmt == "missing"
    assert warnings == ["no_source_provided_and_default_urls_csv_not_found"]


def test_inventory_read_source_nonexistent_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.csv"
    rows, fmt, warnings = _read_source(missing, None)
    assert rows == []
    assert fmt == "missing"
    assert warnings == [f"source_not_found:{missing}"]


def test_inventory_read_source_unsupported_extension(tmp_path: Path) -> None:
    weird = tmp_path / "data.txt"
    weird.write_text("nope", encoding="utf-8")
    rows, fmt, warnings = _read_source(weird, None)
    assert rows == []
    assert fmt == "unknown"
    assert warnings == ["unsupported_source_extension:.txt"]


def test_inventory_read_source_unsupported_explicit_format(tmp_path: Path) -> None:
    some = tmp_path / "data.csv"
    some.write_text("url\nhttps://example.com/\n", encoding="utf-8")
    rows, fmt, warnings = _read_source(some, "parquet")
    assert rows == []
    assert fmt == "unknown"
    assert warnings == ["unsupported_source_format:parquet"]


def test_inventory_read_source_json_non_list_is_empty(tmp_path: Path) -> None:
    blob = tmp_path / "data.json"
    blob.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    rows, fmt, warnings = _read_source(blob, "json")
    assert rows == []
    assert fmt == "json"


def test_inventory_read_source_json_skips_non_dict_entries(tmp_path: Path) -> None:
    blob = tmp_path / "data.json"
    blob.write_text(
        json.dumps([{"url": "https://example.com/a"}, "garbage", 42]),
        encoding="utf-8",
    )
    rows, fmt, _ = _read_source(blob, "json")
    assert fmt == "json"
    assert [r["url"] for r in rows] == ["https://example.com/a"]


# ---------------------------------------------------------------------------
# link_graph._read_source — error branches
# ---------------------------------------------------------------------------


def test_link_source_missing_path() -> None:
    rows, fmt, warnings = _read_link_source(None, None)
    assert rows == []
    assert fmt == "missing"
    assert warnings == []


def test_link_source_nonexistent_file(tmp_path: Path) -> None:
    missing = tmp_path / "links.csv"
    rows, fmt, warnings = _read_link_source(missing, None)
    assert rows == []
    assert fmt == "missing"
    assert warnings == [f"links_source_not_found:{missing}"]


def test_link_source_unsupported_extension(tmp_path: Path) -> None:
    weird = tmp_path / "links.yaml"
    weird.write_text("nope", encoding="utf-8")
    rows, fmt, warnings = _read_link_source(weird, None)
    assert rows == []
    assert fmt == "unknown"
    assert warnings == ["unsupported_links_extension:.yaml"]


def test_link_source_unsupported_explicit_format(tmp_path: Path) -> None:
    some = tmp_path / "links.csv"
    some.write_text("source_url,target_url\n", encoding="utf-8")
    rows, fmt, warnings = _read_link_source(some, "graphml")
    assert rows == []
    assert fmt == "unknown"
    assert warnings == ["unsupported_links_format:graphml"]


def test_link_source_json_non_list_is_empty(tmp_path: Path) -> None:
    blob = tmp_path / "links.json"
    blob.write_text(json.dumps({"edges": []}), encoding="utf-8")
    rows, fmt, _ = _read_link_source(blob, "json")
    assert rows == []
    assert fmt == "json"


# ---------------------------------------------------------------------------
# classifier-rule loader — validation warning branches
# ---------------------------------------------------------------------------


def _client_with_classifier(tmp_path: Path, payload: object) -> object:
    paths = get_client_paths("c", workspace=tmp_path)
    init_client(paths, write=True)
    (paths.config / "classifier.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return paths


def test_classifier_missing_file_uses_defaults(tmp_path: Path) -> None:
    paths = get_client_paths("c", workspace=tmp_path)
    init_client(paths, write=True)
    (paths.config / "classifier.json").unlink(missing_ok=True)
    rules, source, warnings = _load_classifier_rules(paths)
    assert rules  # defaults
    assert source is None
    assert warnings == []


def test_classifier_invalid_json_uses_defaults(tmp_path: Path) -> None:
    paths = get_client_paths("c", workspace=tmp_path)
    init_client(paths, write=True)
    (paths.config / "classifier.json").write_text("{ not json", encoding="utf-8")
    rules, source, warnings = _load_classifier_rules(paths)
    assert rules
    assert source == "classifier_json_invalid"
    assert "classifier_json_invalid" in warnings


def test_classifier_non_dict_top_level_uses_defaults(tmp_path: Path) -> None:
    paths = _client_with_classifier(tmp_path, ["not", "a", "dict"])
    rules, source, warnings = _load_classifier_rules(paths)
    assert rules
    assert source == "classifier_json_invalid"


def test_classifier_rule_not_object_warns(tmp_path: Path) -> None:
    paths = _client_with_classifier(tmp_path, {"rules": ["nope"]})
    _, _, warnings = _load_classifier_rules(paths)
    assert any(w.startswith("classifier_rule_not_object") for w in warnings)


def test_classifier_rule_missing_fields_warns(tmp_path: Path) -> None:
    paths = _client_with_classifier(tmp_path, {"rules": [{"page_type": "blog"}]})
    _, _, warnings = _load_classifier_rules(paths)
    assert any(w.startswith("classifier_rule_missing_fields") for w in warnings)


def test_classifier_rule_invalid_page_type_warns(tmp_path: Path) -> None:
    paths = _client_with_classifier(
        tmp_path, {"rules": [{"page_type": "spaceship", "pattern": "*/x/*"}]}
    )
    _, _, warnings = _load_classifier_rules(paths)
    assert any(w.startswith("classifier_rule_invalid_page_type") for w in warnings)


def test_classifier_rule_invalid_priority_falls_back(tmp_path: Path) -> None:
    paths = _client_with_classifier(
        tmp_path,
        {"rules": [{"page_type": "blog", "pattern": "*/b/*", "priority": "high"}]},
    )
    rules, _, warnings = _load_classifier_rules(paths)
    assert any(w.startswith("classifier_rule_invalid_priority") for w in warnings)
    assert rules  # the rule is still kept with the fallback priority


def test_classifier_rule_invalid_exclude_and_allow_warn(tmp_path: Path) -> None:
    paths = _client_with_classifier(
        tmp_path,
        {
            "rules": [
                {
                    "page_type": "blog",
                    "pattern": "*/b/*",
                    "exclude_patterns": "not-a-list",
                    "allow_urls": "not-a-list",
                }
            ]
        },
    )
    _, _, warnings = _load_classifier_rules(paths)
    assert any(w.startswith("classifier_rule_invalid_exclude_patterns") for w in warnings)
    assert any(w.startswith("classifier_rule_invalid_allow_urls") for w in warnings)


def test_classifier_empty_rules_falls_back_to_defaults(tmp_path: Path) -> None:
    paths = _client_with_classifier(tmp_path, {"rules": []})
    rules, source, warnings = _load_classifier_rules(paths)
    assert rules  # defaults
    assert source == "classifier_json_empty_using_defaults"
    assert "classifier_json_empty_using_defaults" in warnings


# ---------------------------------------------------------------------------
# small coercion helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("ftp://example.com/", None),
        ("not a url", None),
        ("https://example.com/x", "https://example.com/x"),
        ("  http://example.com/y  ", "http://example.com/y"),
    ],
)
def test_coerce_url(value: object, expected: object) -> None:
    assert _coerce_url(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("", None), ("  ", None), (" hi ", "hi"), (123, "123")],
)
def test_string_or_none(value: object, expected: object) -> None:
    assert _string_or_none(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("", None), ("42", 42), ("3.9", 3), ("nan", None), ("xx", None)],
)
def test_int_or_none(value: object, expected: object) -> None:
    assert _int_or_none(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0), ("", 0), ("-5", 0), ("7", 7), (3.8, 3), ("garbage", 0), (object(), 0)],
)
def test_int_or_zero(value: object, expected: int) -> None:
    assert _int_or_zero(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("relative/path", None),
        ("https://EXAMPLE.com/A//b#frag", "https://example.com/A/b"),
    ],
)
def test_normalise_optional(value: object, expected: object) -> None:
    assert _normalise_optional(value) == expected


# ---------------------------------------------------------------------------
# local-gsc-csv provider error + skip branches
# ---------------------------------------------------------------------------


def test_gsc_provider_requires_source() -> None:
    with pytest.raises(ProviderConfigurationError):
        LocalSearchConsoleCsvProvider().run(source=None)


def test_gsc_provider_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ProviderConfigurationError):
        LocalSearchConsoleCsvProvider().run(source=str(tmp_path / "nope.csv"))


def test_gsc_provider_skips_rows_without_query(tmp_path: Path) -> None:
    csv_path = tmp_path / "gsc.csv"
    csv_path.write_text(
        "query,clicks,impressions\n"
        "real query,5,100\n"
        ",9,200\n",  # blank query → skipped
        encoding="utf-8",
    )
    result = LocalSearchConsoleCsvProvider().run(source=str(csv_path))
    assert result.ok is True
    assert len(result.items) == 1
    assert any(w.startswith("skipped_rows_without_query") for w in result.warnings)


# ---------------------------------------------------------------------------
# build_inventory surfaces source warnings end-to-end
# ---------------------------------------------------------------------------


def test_build_inventory_unsupported_source_surfaces_warning(tmp_path: Path) -> None:
    paths = get_client_paths("c", workspace=tmp_path)
    init_client(paths, write=True)
    weird = tmp_path / "src.txt"
    weird.write_text("x", encoding="utf-8")
    result = build_inventory(paths, write=False, source=weird)
    assert any("unsupported_source_extension" in w for w in result["warnings"])


def test_build_link_graph_unsupported_source_surfaces_warning(tmp_path: Path) -> None:
    paths = get_client_paths("c", workspace=tmp_path)
    init_client(paths, write=True)
    weird = tmp_path / "links.yaml"
    weird.write_text("x", encoding="utf-8")
    result = build_link_graph(paths, write=False, source=weird)
    assert any("unsupported_links_extension" in w for w in result["warnings"])


def test_classifier_rule_dataclass_defaults() -> None:
    rule = ClassifierRule(page_type="blog", pattern="*/blog/*")
    assert rule.priority == 100
    assert rule.exclude_patterns == ()
    assert rule.allow_urls == frozenset()


# ---------------------------------------------------------------------------
# build_link_graph — JSON edges, self-loops, fallback counts, robustness
# ---------------------------------------------------------------------------


def _seed_inventory(paths: object, items: list[dict]) -> None:
    (paths.data / "content_inventory.json").write_text(
        json.dumps(items), encoding="utf-8"
    )


def test_link_graph_reads_json_edges_and_counts_blog_inlinks(tmp_path: Path) -> None:
    paths = get_client_paths("c", workspace=tmp_path)
    init_client(paths, write=True)
    _seed_inventory(
        paths,
        [
            {"url": "https://example.com/svc/", "page_type": "service"},
            {"url": "https://example.com/blog/a/", "page_type": "blog"},
            "not-a-dict-entry",  # exercises the non-dict skip branch
        ],
    )
    edges = tmp_path / "edges.json"
    edges.write_text(
        json.dumps(
            [
                {
                    "source_url": "https://example.com/blog/a/",
                    "target_url": "https://example.com/svc/",
                    "anchor_text": "service",
                },
                # self-loop is dropped
                {
                    "source_url": "https://example.com/svc/",
                    "target_url": "https://example.com/svc/",
                },
                "garbage-non-dict",
            ]
        ),
        encoding="utf-8",
    )
    result = build_link_graph(paths, write=True, source=edges, source_format="json")
    assert result["source_format"] == "json"
    nodes = {n["url"]: n for n in result["graph"]["nodes"]}
    svc = nodes["https://example.com/svc/"]
    # One inlink, from a blog → blog_inlink_count == 1, commercial target.
    assert svc["inlink_count"] == 1
    assert svc["blog_inlink_count"] == 1
    assert svc["is_commercial_target"] is True
    # The self-loop produced no edge.
    assert result["edges_count"] == 1


def test_link_graph_uses_inventory_fallback_counts_without_edges(tmp_path: Path) -> None:
    paths = get_client_paths("c", workspace=tmp_path)
    init_client(paths, write=True)
    _seed_inventory(
        paths,
        [
            {
                "url": "https://example.com/p/",
                "page_type": "blog",
                "inlinks_count": 0,
                "outlinks_count": 4,
            }
        ],
    )
    result = build_link_graph(paths, write=True, source=None)
    assert "no_edges_in_input_using_inventory_counts_only" in result["warnings"]
    node = result["graph"]["nodes"][0]
    # No explicit edges → fallback to the inventory-reported counts.
    assert node["outlink_count"] == 4
    # A blog with <=1 inlink shows up in the orphan list.
    assert result["blog_pages_low_inlinks_count"] == 1
