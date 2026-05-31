"""Unit tests for the local SERP-evidence CSV provider.

The provider:

* reads a hand-curated CSV with columns ``query``, ``rank``, ``title``,
  ``url``, ``snippet``, ``page_type``;
* tolerates header aliases (``position`` for ``rank``, ``snippet_text``
  for ``snippet``, etc.) and case-insensitive matching with
  spaces/underscores/dashes treated as equivalent;
* coerces ``rank`` / ``position`` to integers (``"1.0"`` → ``1``);
* emits ``SearchEvidence`` rows with ``source = "local-serp-csv"`` and
  preserves any unrecognised columns inside ``raw``;
* never makes a network call;
* returns a structured ``ProviderResult``;
* raises ``ProviderConfigurationError`` for missing files / missing
  ``query`` column.

Total: 12 tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from site_context_pipeline.providers import (
    ProviderConfigurationError,
    available_providers,
    get_search_evidence_provider,
)
from site_context_pipeline.providers.local_search_evidence_csv import (
    LocalSearchEvidenceCsvProvider,
)

FIXTURES_CSV = Path(__file__).parent.parent / "examples" / "demo-client" / "input" / "search_evidence.csv"


def test_demo_csv_imports() -> None:
    provider = LocalSearchEvidenceCsvProvider()
    result = provider.run(source=str(FIXTURES_CSV))
    assert result.ok is True
    assert result.provider == "local-serp-csv"
    items = result.items
    assert len(items) == 8

    first = items[0]
    assert first["query"] == "local delivery planning"
    assert first["rank"] == 1
    assert first["title"] == "Plan a Local Delivery Run"
    assert first["url"] == "https://competitor-a.example/blog/local-delivery"
    assert first["snippet"] == "How to plan local delivery routes"
    assert first["page_type"] == "article"
    assert first["source"] == "local-serp-csv"


def test_metadata_is_populated() -> None:
    provider = LocalSearchEvidenceCsvProvider()
    result = provider.run(source=str(FIXTURES_CSV))
    md = result.metadata
    assert md["row_count"] == 8
    assert md["items_count"] == 8
    assert md["distinct_queries"] == 3
    assert md["source_path"].endswith("search_evidence.csv")


def test_alias_columns_position_and_snippet_text(tmp_path: Path) -> None:
    csv_path = tmp_path / "evidence.csv"
    csv_path.write_text(
        "Query,Position,Title,URL,Snippet Text,Page Type\n"
        "x query,1,A,https://a.example/,first,article\n",
        encoding="utf-8",
    )
    provider = LocalSearchEvidenceCsvProvider()
    result = provider.run(source=str(csv_path))
    assert result.ok is True
    item = result.items[0]
    assert item["query"] == "x query"
    assert item["rank"] == 1
    assert item["title"] == "A"
    assert item["snippet"] == "first"


def test_rank_with_decimal_string_is_coerced(tmp_path: Path) -> None:
    csv_path = tmp_path / "evidence.csv"
    csv_path.write_text(
        "query,rank,url\nfoo,1.0,https://a.example/\nbar,2,https://b.example/\n",
        encoding="utf-8",
    )
    provider = LocalSearchEvidenceCsvProvider()
    result = provider.run(source=str(csv_path))
    assert [item["rank"] for item in result.items] == [1, 2]


def test_unrecognised_columns_preserved_in_raw(tmp_path: Path) -> None:
    csv_path = tmp_path / "evidence.csv"
    csv_path.write_text(
        "query,rank,url,domain,is_paid\n"
        "x,1,https://a.example/,competitor-a.example,false\n",
        encoding="utf-8",
    )
    provider = LocalSearchEvidenceCsvProvider()
    result = provider.run(source=str(csv_path))
    item = result.items[0]
    assert item["raw"]["domain"] == "competitor-a.example"
    assert item["raw"]["is_paid"] == "false"


def test_skips_rows_without_query(tmp_path: Path) -> None:
    csv_path = tmp_path / "evidence.csv"
    csv_path.write_text(
        "query,rank,url\n"
        "foo,1,https://a.example/\n"
        ",2,https://b.example/\n",
        encoding="utf-8",
    )
    provider = LocalSearchEvidenceCsvProvider()
    result = provider.run(source=str(csv_path))
    assert len(result.items) == 1
    assert any("skipped_rows_without_query:1" in w for w in result.warnings)


def test_missing_source_raises() -> None:
    with pytest.raises(ProviderConfigurationError):
        LocalSearchEvidenceCsvProvider().run(source=None)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ProviderConfigurationError):
        LocalSearchEvidenceCsvProvider().run(source=str(tmp_path / "nope.csv"))


def test_csv_without_query_column_raises(tmp_path: Path) -> None:
    csv_path = tmp_path / "evidence.csv"
    csv_path.write_text("foo,bar\nx,y\n", encoding="utf-8")
    with pytest.raises(ProviderConfigurationError):
        LocalSearchEvidenceCsvProvider().run(source=str(csv_path))


def test_provider_result_serialises_to_json() -> None:
    provider = LocalSearchEvidenceCsvProvider()
    result = provider.run(source=str(FIXTURES_CSV))
    encoded = json.dumps(result.to_dict())
    decoded = json.loads(encoded)
    assert decoded["provider"] == "local-serp-csv"
    assert isinstance(decoded["items"], list) and decoded["items"]


def test_registry_lists_search_evidence_provider() -> None:
    listing = available_providers()
    names = {entry["name"] for entry in listing.get("search_evidence", [])}
    assert "local-serp-csv" in names


def test_get_search_evidence_provider_round_trips() -> None:
    provider = get_search_evidence_provider("local-serp-csv")
    assert provider.provider_name == "local-serp-csv"
    with pytest.raises(ProviderConfigurationError):
        get_search_evidence_provider("does-not-exist")
