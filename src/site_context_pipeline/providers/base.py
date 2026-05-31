"""Provider base classes and shared error types.

A provider is a small adapter that normalises one external data source
into the toolkit's generic ``KeywordMetric`` / ``SearchEvidence`` rows.
There are three families:

* **Keyword providers** — return ``KeywordMetric`` rows. Source can be a
  local CSV (Google Ads export, hand-curated research) or a future API
  adapter (Google Ads Keyword Planner, Yandex Wordstat, DataForSEO,
  SerpApi, etc.).
* **Search performance providers** — return ``KeywordMetric`` rows whose
  fields lean on ``impressions`` / ``clicks`` / ``ctr`` / ``position``.
  Source is typically a Google Search Console export or its API.
* **Search evidence providers** — return ``SearchEvidence`` rows (rank,
  title, snippet, URL). Out of scope for the 0.1 base package; the
  interface is here so future adapters slot in cleanly.

The toolkit never bakes in a vendor name. ``provider_name`` is just a
short slug used in CLI output and the ``source`` field of every emitted
row, so users can trace which adapter produced which row.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..schemas import KeywordMetric, ProviderResult, SearchEvidence


class ProviderError(Exception):
    """Base class for any provider-related failure that should surface as
    an error rather than silently empty results."""


class ProviderConfigurationError(ProviderError):
    """Raised when the user-supplied ``provider_config`` is structurally
    wrong (missing required keys, wrong types, unparseable file)."""


class ProviderNotConfiguredError(ProviderError):
    """Raised by adapters whose live mode is not yet implemented or whose
    credentials/optional dependencies are missing.

    CLI commands convert this into a structured ``ProviderResult`` with
    ``ok=False`` so the user gets a JSON payload they can act on instead
    of a stack trace.
    """


# ---------------------------------------------------------------------------
# Keyword providers
# ---------------------------------------------------------------------------


class KeywordProvider(ABC):
    """Anything that emits ``KeywordMetric`` rows.

    Concrete providers should:

    * declare a stable, lowercase ``provider_name`` (e.g. ``local-csv``,
      ``google-ads``);
    * implement ``run`` so it never raises for "well-formed but blocked"
      situations (missing credentials, missing optional dependency).
      Return a ``ProviderResult`` with ``ok=False`` and an explanatory
      warning instead;
    * raise ``ProviderConfigurationError`` only for genuinely malformed
      input (CSV not found, JSON not a list, etc.).
    """

    provider_name: str = "abstract"

    @abstractmethod
    def run(
        self,
        *,
        source: str | None = None,
        provider_config: dict[str, Any] | None = None,
    ) -> ProviderResult:
        """Return a ``ProviderResult`` whose ``items`` are ``KeywordMetric``
        instances (or their dict equivalents)."""


# ---------------------------------------------------------------------------
# Search performance providers (impressions / clicks / CTR / position)
# ---------------------------------------------------------------------------


class SearchPerformanceProvider(ABC):
    """Anything that emits per-query performance data.

    Conceptually a sibling of ``KeywordProvider``: same ``KeywordMetric``
    payload, but the data flavour is "what the site already serves" rather
    than "what people search for in general."
    """

    provider_name: str = "abstract"

    @abstractmethod
    def run(
        self,
        *,
        source: str | None = None,
        provider_config: dict[str, Any] | None = None,
    ) -> ProviderResult:
        ...


# ---------------------------------------------------------------------------
# Helpers used by adapters
# ---------------------------------------------------------------------------


def empty_result(provider_name: str, *, dry_run: bool, warnings: list[str]) -> ProviderResult:
    """Convenience constructor for "ran cleanly, no rows" outcomes."""
    return ProviderResult(
        ok=True,
        provider=provider_name,
        dry_run=dry_run,
        items=[],
        warnings=warnings,
        errors=[],
        metadata={},
    )


def blocked_result(
    provider_name: str,
    *,
    reason: str,
    suggestion: str | None = None,
    dry_run: bool = True,
) -> ProviderResult:
    """Build the canonical "this provider can't run yet" payload.

    ``reason`` is a stable machine-readable token (e.g.
    ``not_configured``, ``missing_dependency``); ``suggestion`` is human
    text the CLI surfaces to the user.
    """
    warnings = [reason]
    if suggestion:
        warnings.append(suggestion)
    return ProviderResult(
        ok=False,
        provider=provider_name,
        dry_run=dry_run,
        items=[],
        warnings=warnings,
        errors=[reason],
        metadata={"blocked_reason": reason, "suggestion": suggestion},
    )


def items_as_dicts(items: list[KeywordMetric] | list[SearchEvidence]) -> list[dict[str, Any]]:
    """Normalise typed items to JSON-serialisable dicts."""
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            out.append(item)
        else:
            from dataclasses import asdict

            out.append(asdict(item))
    return out
