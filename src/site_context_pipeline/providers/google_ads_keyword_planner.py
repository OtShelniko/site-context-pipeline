"""Google Ads Keyword Planner adapter.

Optional live adapter for the Google Ads
`KeywordPlanIdeaService.GenerateKeywordIdeas` endpoint
(https://developers.google.com/google-ads/api/docs/keyword-planning/generate-keyword-ideas).

Design rules (see docs/providers.md → "Provider safety rules"):

* The `google-ads` SDK is **never** imported at module load. It is
  imported lazily inside ``_load_client`` so the base package installs
  and runs with zero runtime dependencies.
* Credentials come from ``provider_config`` (typically loaded from a
  gitignored ``<client>/config/google_ads.json`` or environment
  variables). They are never logged, never serialised into an artifact.
* When config or the optional dependency is missing, ``run`` returns a
  structured ``not_configured`` / ``missing_dependency`` result via
  ``blocked_result`` — it never raises for that case.
* ``ProviderConfigurationError`` is raised only for *malformed* config
  (present but structurally wrong).

Install the optional extra to use live mode::

    pip install "site-context-pipeline[google-ads]"

Required ``provider_config`` keys (live mode)::

    {
      "customer_id":      "1234567890",
      "developer_token":  "…",
      "client_id":        "…",
      "client_secret":    "…",
      "refresh_token":    "…",
      "seeds":            ["seed phrase", "another seed"],
      "geo_target_constants": ["geoTargetConstants/2840"],  # optional
      "language_constant":    "languageConstants/1000"        # optional
    }
"""

from __future__ import annotations

from typing import Any

from ..schemas import KeywordMetric, ProviderResult
from .base import (
    KeywordProvider,
    ProviderConfigurationError,
    blocked_result,
    items_as_dicts,
)

# Config keys that must be present (and non-empty) for live mode.
_REQUIRED_CONFIG_KEYS = (
    "customer_id",
    "developer_token",
    "client_id",
    "client_secret",
    "refresh_token",
)

# Google Ads competition enum → our free-form string. The API returns an
# enum; we keep the human-readable label.
_COMPETITION_LABELS = {
    0: None,        # UNSPECIFIED
    1: None,        # UNKNOWN
    2: "LOW",
    3: "MEDIUM",
    4: "HIGH",
}


class GoogleAdsKeywordPlannerProvider(KeywordProvider):
    """Live Google Ads Keyword Planner adapter (opt-in via the extra)."""

    provider_name = "google-ads"

    def run(
        self,
        *,
        source: str | None = None,
        provider_config: dict[str, Any] | None = None,
    ) -> ProviderResult:
        # No config at all → behave exactly like the old stub so existing
        # CLI consumers keep getting a clean, actionable message.
        if not provider_config:
            return blocked_result(
                self.provider_name,
                reason="not_configured",
                suggestion=(
                    "Google Ads Keyword Planner needs credentials. Pass them with "
                    "--config <client>/config/google_ads.json, or export keyword "
                    "ideas as CSV and import with --provider local-csv. "
                    "Install live support with: pip install "
                    '"site-context-pipeline[google-ads]".'
                ),
            )

        # Config present but malformed → this is a real error.
        missing = validate_config(provider_config)
        if missing:
            raise ProviderConfigurationError(
                f"google-ads provider_config missing required keys: {', '.join(missing)}"
            )

        # Config looks complete. Try to load the SDK lazily.
        try:
            client = self._load_client(provider_config)
        except _MissingDependencyError:
            return blocked_result(
                self.provider_name,
                reason="missing_dependency",
                suggestion=(
                    "The google-ads SDK is not installed. Install it with: "
                    'pip install "site-context-pipeline[google-ads]".'
                ),
            )

        seeds = _coerce_seeds(provider_config.get("seeds"))
        if not seeds and not provider_config.get("page_url"):
            raise ProviderConfigurationError(
                "google-ads provider_config needs a non-empty 'seeds' list "
                "or a 'page_url' to generate ideas from."
            )

        rows = self._generate_ideas(client, provider_config, seeds)
        items = [r for r in (map_idea_to_metric(raw) for raw in rows) if r is not None]
        return ProviderResult(
            ok=True,
            provider=self.provider_name,
            dry_run=True,  # the CLI flips this when --write is set
            items=items_as_dicts(items),
            warnings=[],
            errors=[],
            metadata={
                "customer_id": _redact(provider_config.get("customer_id")),
                "seeds_count": len(seeds),
                "items_count": len(items),
            },
        )

    # -- seams (isolated so tests can stub them without a network) ------

    def _load_client(self, provider_config: dict[str, Any]) -> Any:
        """Lazily build a ``GoogleAdsClient``.

        Imported here, never at module scope, so the base package has no
        dependency on the SDK. Raises ``_MissingDependencyError`` when the
        extra is not installed.
        """
        try:
            from google.ads.googleads.client import GoogleAdsClient
        except ImportError as exc:  # pragma: no cover - exercised via _load_client stub
            raise _MissingDependencyError from exc

        credentials = {
            "developer_token": provider_config["developer_token"],
            "client_id": provider_config["client_id"],
            "client_secret": provider_config["client_secret"],
            "refresh_token": provider_config["refresh_token"],
            "use_proto_plus": True,
        }
        if provider_config.get("login_customer_id"):
            credentials["login_customer_id"] = str(provider_config["login_customer_id"])
        return GoogleAdsClient.load_from_dict(credentials)

    def _generate_ideas(
        self, client: Any, provider_config: dict[str, Any], seeds: list[str]
    ) -> list[Any]:  # pragma: no cover - requires live SDK/credentials
        """Call ``KeywordPlanIdeaService`` and return the raw result rows.

        Kept tiny and free of mapping logic so the only untestable part is
        the network call itself. Everything that shapes the output lives
        in ``map_idea_to_metric`` / ``validate_config``, which are unit
        tested directly.
        """
        service = client.get_service("KeywordPlanIdeaService")
        request = client.get_type("GenerateKeywordIdeasRequest")
        request.customer_id = str(provider_config["customer_id"])
        if provider_config.get("language_constant"):
            request.language = provider_config["language_constant"]
        for geo in provider_config.get("geo_target_constants") or []:
            request.geo_target_constants.append(geo)
        if seeds:
            request.keyword_seed.keywords.extend(seeds)
        if provider_config.get("page_url"):
            request.url_seed.url = provider_config["page_url"]
        response = service.generate_keyword_ideas(request=request)
        return list(response)


class _MissingDependencyError(RuntimeError):
    """Internal marker: the optional google-ads SDK is not installed."""


# ---------------------------------------------------------------------------
# Pure helpers — fully unit tested, no network, no SDK.
# ---------------------------------------------------------------------------


def validate_config(provider_config: dict[str, Any]) -> list[str]:
    """Return the list of required keys that are missing or blank.

    An empty list means the credential block is structurally complete.
    """
    missing: list[str] = []
    for key in _REQUIRED_CONFIG_KEYS:
        value = provider_config.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(key)
    return missing


def _coerce_seeds(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for v in value:
            if v is None:
                continue
            text = str(v).strip()
            if text:
                out.append(text)
        return out
    return []


def _redact(value: Any) -> str | None:
    """Mask all but the last 4 chars of an identifier for metadata.

    Customer IDs are not secrets, but masking keeps artifacts tidy and
    avoids surprises if a config key is mis-set to something sensitive.
    """
    if value in (None, ""):
        return None
    text = str(value)
    if len(text) <= 4:
        return "*" * len(text)
    return "*" * (len(text) - 4) + text[-4:]


def map_idea_to_metric(raw: Any) -> KeywordMetric | None:
    """Map one Google Ads keyword idea to a ``KeywordMetric``.

    ``raw`` is a ``GenerateKeywordIdeaResult`` (proto-plus) in live mode,
    but this function only relies on attribute access, so tests pass a
    light stand-in object with the same shape. Returns ``None`` when the
    idea has no usable text.
    """
    text = getattr(raw, "text", None)
    if not text or not str(text).strip():
        return None

    metrics = getattr(raw, "keyword_idea_metrics", None)
    avg_searches = _opt_int(getattr(metrics, "avg_monthly_searches", None))
    competition = _competition_label(getattr(metrics, "competition", None))

    return KeywordMetric(
        query=str(text).strip(),
        source="google-ads",
        avg_monthly_searches=avg_searches,
        competition=competition,
        raw=_safe_raw(metrics),
    )


def _competition_label(value: Any) -> str | None:
    """Translate a Google Ads competition enum value to a label.

    Accepts an int enum, an object with a ``.value`` (proto-plus enum),
    or a string the caller already resolved.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    raw_value = getattr(value, "value", value)
    try:
        return _COMPETITION_LABELS.get(int(raw_value))
    except (TypeError, ValueError):
        return None


def _opt_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_raw(metrics: Any) -> dict[str, Any]:
    """Capture a few extra metric fields for forensics, never credentials."""
    if metrics is None:
        return {}
    out: dict[str, Any] = {}
    low = getattr(metrics, "low_top_of_page_bid_micros", None)
    high = getattr(metrics, "high_top_of_page_bid_micros", None)
    if low not in (None, ""):
        out["low_top_of_page_bid_micros"] = _opt_int(low)
    if high not in (None, ""):
        out["high_top_of_page_bid_micros"] = _opt_int(high)
    return out
