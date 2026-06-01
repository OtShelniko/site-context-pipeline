"""Google Search Console Search Analytics adapter.

Optional live adapter for the Search Console
`searchanalytics.query` endpoint
(https://developers.google.com/webmaster-tools/v1/searchanalytics/query).

Design rules (see docs/providers.md → "Provider safety rules"):

* Google's client libraries are **never** imported at module load. They
  are imported lazily inside ``_load_service`` so the base package
  installs and runs with zero runtime dependencies.
* Credentials come from ``provider_config`` (typically a gitignored
  service-account JSON path, or an OAuth bundle). They are never logged,
  never serialised into an artifact.
* When config or the optional dependency is missing, ``run`` returns a
  structured ``not_configured`` / ``missing_dependency`` result via
  ``blocked_result`` — it never raises for that case.
* ``ProviderConfigurationError`` is raised only for *malformed* config.

Install the optional extra to use live mode::

    pip install "site-context-pipeline[gsc]"

Required ``provider_config`` keys (live mode)::

    {
      "site_url":          "sc-domain:example.com",   # or a URL prefix
      "credentials_path":  "clients/<id>/config/gsc_service_account.json",
      "start_date":        "2026-04-01",
      "end_date":          "2026-04-30",
      "dimensions":        ["query", "page"],          # optional
      "row_limit":         1000                         # optional, default 1000
    }
"""

from __future__ import annotations

from typing import Any

from ..schemas import KeywordMetric, ProviderResult
from .base import (
    ProviderConfigurationError,
    SearchPerformanceProvider,
    blocked_result,
    items_as_dicts,
)

_REQUIRED_CONFIG_KEYS = (
    "site_url",
    "credentials_path",
    "start_date",
    "end_date",
)

_DEFAULT_DIMENSIONS = ("query", "page")
_VALID_DIMENSIONS = frozenset(
    {"query", "page", "country", "device", "date", "searchAppearance"}
)
_DEFAULT_ROW_LIMIT = 1000
_MAX_ROW_LIMIT = 25000  # Search Analytics hard cap per request.


class GoogleSearchConsoleProvider(SearchPerformanceProvider):
    """Live Google Search Console adapter (opt-in via the extra)."""

    provider_name = "google-search-console"

    def run(
        self,
        *,
        source: str | None = None,
        provider_config: dict[str, Any] | None = None,
    ) -> ProviderResult:
        # No config at all → behave like the old stub so existing CLI
        # consumers keep getting a clean, actionable message.
        if not provider_config:
            return blocked_result(
                self.provider_name,
                reason="not_configured",
                suggestion=(
                    "Google Search Console needs a verified property and "
                    "credentials. Pass them with --config "
                    "<client>/config/google_search_console.json, or export the "
                    "Performance report as CSV and import with --provider "
                    "local-gsc-csv. Install live support with: pip install "
                    '"site-context-pipeline[gsc]".'
                ),
            )

        missing = validate_config(provider_config)
        if missing:
            raise ProviderConfigurationError(
                "google-search-console provider_config missing required keys: "
                f"{', '.join(missing)}"
            )

        dimensions = resolve_dimensions(provider_config.get("dimensions"))
        if dimensions is None:
            raise ProviderConfigurationError(
                "google-search-console 'dimensions' must be a subset of "
                f"{sorted(_VALID_DIMENSIONS)} and include 'query'."
            )
        row_limit = resolve_row_limit(provider_config.get("row_limit"))

        try:
            service = self._load_service(provider_config)
        except _MissingDependencyError:
            return blocked_result(
                self.provider_name,
                reason="missing_dependency",
                suggestion=(
                    "The Google API client libraries are not installed. Install "
                    'them with: pip install "site-context-pipeline[gsc]".'
                ),
            )

        raw_rows = self._query(service, provider_config, dimensions, row_limit)
        items = [
            r
            for r in (map_row_to_metric(raw, dimensions) for raw in raw_rows)
            if r is not None
        ]
        return ProviderResult(
            ok=True,
            provider=self.provider_name,
            dry_run=True,  # the CLI flips this when --write is set
            items=items_as_dicts(items),
            warnings=[],
            errors=[],
            metadata={
                "site_url": provider_config.get("site_url"),
                "date_range": {
                    "start": provider_config.get("start_date"),
                    "end": provider_config.get("end_date"),
                },
                "dimensions": list(dimensions),
                "row_limit": row_limit,
                "items_count": len(items),
            },
        )

    # -- seams (isolated so tests can stub them without a network) ------

    def _load_service(self, provider_config: dict[str, Any]) -> Any:
        """Lazily build a Search Console API service handle.

        Imported here, never at module scope. Raises
        ``_MissingDependencyError`` when the extra is not installed.
        """
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover - exercised via _load_service stub
            raise _MissingDependencyError from exc

        credentials = Credentials.from_service_account_file(
            provider_config["credentials_path"],
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        )
        return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)

    def _query(
        self,
        service: Any,
        provider_config: dict[str, Any],
        dimensions: tuple[str, ...],
        row_limit: int,
    ) -> list[dict[str, Any]]:  # pragma: no cover - requires live SDK/credentials
        """Call Search Analytics and return the raw ``rows`` list.

        Kept free of mapping logic so the only untestable part is the
        network call. Everything that shapes the output lives in
        ``map_row_to_metric`` / ``validate_config`` / ``resolve_*``,
        which are unit tested directly.
        """
        body = {
            "startDate": provider_config["start_date"],
            "endDate": provider_config["end_date"],
            "dimensions": list(dimensions),
            "rowLimit": row_limit,
        }
        response = (
            service.searchanalytics()
            .query(siteUrl=provider_config["site_url"], body=body)
            .execute()
        )
        return list(response.get("rows") or [])


class _MissingDependencyError(RuntimeError):
    """Internal marker: the optional gsc client libraries are not installed."""


# ---------------------------------------------------------------------------
# Pure helpers — fully unit tested, no network, no SDK.
# ---------------------------------------------------------------------------


def validate_config(provider_config: dict[str, Any]) -> list[str]:
    """Return the list of required keys that are missing or blank."""
    missing: list[str] = []
    for key in _REQUIRED_CONFIG_KEYS:
        value = provider_config.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(key)
    return missing


def resolve_dimensions(value: Any) -> tuple[str, ...] | None:
    """Normalise the ``dimensions`` config into a validated tuple.

    Returns ``None`` when the value is invalid (unknown dimension, or
    missing the required ``query`` dimension). ``None``/absent falls back
    to the default ``("query", "page")``.
    """
    if value is None:
        return _DEFAULT_DIMENSIONS
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return None
    dims = [str(v).strip() for v in value if str(v).strip()]
    if not dims:
        return _DEFAULT_DIMENSIONS
    if any(d not in _VALID_DIMENSIONS for d in dims):
        return None
    if "query" not in dims:
        return None
    return tuple(dims)


def resolve_row_limit(value: Any) -> int:
    """Clamp the requested row limit into ``[1, 25000]``; default 1000."""
    if value in (None, ""):
        return _DEFAULT_ROW_LIMIT
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_ROW_LIMIT
    if limit < 1:
        return _DEFAULT_ROW_LIMIT
    return min(limit, _MAX_ROW_LIMIT)


def map_row_to_metric(raw: Any, dimensions: tuple[str, ...]) -> KeywordMetric | None:
    """Map one Search Analytics row to a ``KeywordMetric``.

    A Search Analytics row looks like::

        {"keys": ["task automation", "https://…/page/"],
         "clicks": 88, "impressions": 3400, "ctr": 0.0259, "position": 9.1}

    ``keys`` aligns positionally with ``dimensions``. Returns ``None``
    when there is no ``query`` key value.
    """
    if not isinstance(raw, dict):
        return None
    keys = raw.get("keys") or []
    by_dim = dict(zip(dimensions, keys, strict=False))

    query = by_dim.get("query")
    if not query or not str(query).strip():
        return None

    extra: dict[str, Any] = {}
    for dim in ("device", "date", "searchAppearance"):
        if dim in by_dim and by_dim[dim] not in (None, ""):
            extra[dim] = by_dim[dim]

    return KeywordMetric(
        query=str(query).strip(),
        source="google-search-console",
        geo=_string_or_none(by_dim.get("country")),
        source_url=_string_or_none(by_dim.get("page")),
        impressions=_opt_int(raw.get("impressions")),
        clicks=_opt_int(raw.get("clicks")),
        ctr=_opt_ratio(raw.get("ctr")),
        position=_opt_float(raw.get("position")),
        raw=extra,
    )


def _string_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _opt_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return int(number)


def _opt_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _opt_ratio(value: Any) -> float | None:
    """GSC already reports CTR as a fraction in [0..1]; just coerce."""
    number = _opt_float(value)
    if number is None:
        return None
    return round(number, 6)
