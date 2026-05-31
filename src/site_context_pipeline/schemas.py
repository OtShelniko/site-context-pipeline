"""Typed dataclasses for the public artifact schema.

These are the *shape* contracts of the JSON files this tool emits. The CLI
serialises plain dictionaries built from these dataclasses so that the public
JSON schema stays human-readable and easy to consume from any language.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PageType = Literal[
    "home",
    "service",
    "blog",
    "category",
    "landing",
    "other",
]

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class InventoryItem:
    """One normalised page in the site inventory."""

    url: str
    path: str
    page_type: PageType
    classification_reason: str
    title: str | None = None
    h1: str | None = None
    status_code: int | None = None
    word_count: int | None = None
    inlinks_count: int | None = None
    outlinks_count: int | None = None
    source: str = "csv"


@dataclass(frozen=True)
class LinkNode:
    url: str
    page_type: PageType
    inlink_count: int = 0
    outlink_count: int = 0
    blog_inlink_count: int = 0
    is_commercial_target: bool = False


@dataclass(frozen=True)
class LinkEdge:
    source_url: str
    target_url: str
    anchor_text: str | None = None


@dataclass(frozen=True)
class CommandResult:
    """Uniform return value for every CLI subcommand."""

    ok: bool
    command: str
    client: str
    dry_run: bool
    write_performed: bool = False
    planned_writes: list[str] = field(default_factory=list)
    written_files: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Provider-agnostic data models for keyword and search-evidence imports.
#
# These are deliberately generic: every field is optional except the query
# string itself. A local CSV import, a Google Search Console export, a
# Google Ads Keyword Planner export, or any future adapter (Yandex
# Wordstat, DataForSEO, SerpApi, manual research notes) should fit into
# the same shape.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KeywordMetric:
    """One keyword-level row of demand or performance data.

    The same dataclass covers both demand-side data (e.g. average monthly
    searches from a planner tool) and performance-side data (e.g. clicks
    and impressions for a query already serving traffic). Providers fill
    in only the fields they actually have; the rest stay ``None``.

    ``locale``, ``geo``, and ``language`` are kept as separate strings so
    callers can mix data from different markets without losing
    provenance. Use whatever convention fits your data — common values:

    * ``locale``  — ``en-US``, ``ru-RU`` (BCP 47).
    * ``geo``     — ``US``, ``RU``, ``EU``, ``Moscow``.
    * ``language``— ``en``, ``ru`` (ISO 639-1).
    """

    query: str
    source: str
    locale: str | None = None
    geo: str | None = None
    language: str | None = None
    avg_monthly_searches: int | None = None
    impressions: int | None = None
    clicks: int | None = None
    ctr: float | None = None
    position: float | None = None
    competition: str | None = None
    source_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchEvidence:
    """One row of search-result evidence for a query.

    Fits both organic SERP rows (for future search-evidence providers) and
    locally-curated research notes ("for query X, we found this competitor
    page"). The toolkit never fetches pages from third parties in 0.x;
    evidence is imported from local files only.
    """

    query: str
    source: str
    title: str | None = None
    url: str | None = None
    snippet: str | None = None
    rank: int | None = None
    page_type: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResult:
    """Uniform return value for every provider call.

    ``items`` carries either ``KeywordMetric`` or ``SearchEvidence``
    instances (or their dict equivalents) depending on the provider. The
    shape is identical so the CLI can render every provider's output the
    same way.

    Providers that cannot run because credentials or optional dependencies
    are missing must still return a ``ProviderResult`` with ``ok=False``,
    ``items=[]``, and a clear ``warnings`` entry — never raise unless the
    inputs are malformed.
    """

    ok: bool
    provider: str
    dry_run: bool
    items: list[Any] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def keyword_metric_to_dict(item: KeywordMetric) -> dict[str, Any]:
    return asdict(item)


def search_evidence_to_dict(item: SearchEvidence) -> dict[str, Any]:
    return asdict(item)
