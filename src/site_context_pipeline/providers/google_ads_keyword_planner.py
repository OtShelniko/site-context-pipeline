"""Google Ads Keyword Planner adapter (stub for 0.1).

This is the **interface** the live adapter will expose, not the live
adapter itself. In 0.1 the adapter never makes a network call, never
imports the `google-ads` SDK, and never reads credentials. It returns a
structured ``not_configured`` result so the CLI can show a clean message
without crashing.

Why a stub? Because:

1. Adding `google-ads` as a base dependency would make the package heavy
   for users who only need local CSV imports.
2. Tests must not require real Google Cloud credentials.
3. The Google Ads API has its own rate-limit, billing, and OAuth flow —
   doing it well deserves a separate release.

Planned (future) behaviour
--------------------------

When live mode lands, the adapter will use ``KeywordPlanIdeaService``
(see https://developers.google.com/google-ads/api/docs/keyword-planning).
Supported seed types:

* keyword seed (a list of seed phrases),
* URL seed (a landing page URL),
* keyword + URL seed,
* site seed (the whole site).

Normalised output (per row):

* ``query``                — the suggested keyword text;
* ``avg_monthly_searches`` — Google Ads `avg_monthly_searches`;
* ``competition``          — Google Ads `competition` enum (LOW/MEDIUM/HIGH);
* ``geo``                  — the geo target the request was scoped to
                              (Google ``GeoTargetConstant`` resource name);
* ``language``             — the language target (Google
                              ``LanguageConstant`` resource name).

``raw`` will preserve the original API row for forensics. The toolkit
will never store API credentials inside any artifact.

Required ``provider_config`` (planned)
--------------------------------------

* ``customer_id``           — Google Ads customer ID.
* ``developer_token``       — Google Ads developer token.
* ``refresh_token``         — OAuth refresh token.
* ``client_id`` / ``client_secret`` — OAuth client credentials.
* ``geo_target_constants``  — list, e.g. ``["geoTargetConstants/2840"]``.
* ``language_constant``     — e.g. ``"languageConstants/1000"``.
* ``seeds``                 — keyword seeds, URL seeds, or both.

These will be supplied via environment variables and/or
``<client>/config/google_ads.json``. Credentials must never be logged or
serialised into the toolkit's artifacts.
"""

from __future__ import annotations

from typing import Any

from ..schemas import ProviderResult
from .base import KeywordProvider, blocked_result


class GoogleAdsKeywordPlannerProvider(KeywordProvider):
    """Stub adapter. Always returns a ``not_configured`` result in 0.1."""

    provider_name = "google-ads"

    def run(
        self,
        *,
        source: str | None = None,
        provider_config: dict[str, Any] | None = None,
    ) -> ProviderResult:
        # In 0.1 we do not even probe for the optional dependency or
        # credentials — that decision belongs to the live release. The
        # message stays stable so CLI consumers can switch on it.
        return blocked_result(
            self.provider_name,
            reason="not_configured",
            suggestion=(
                "Live Google Ads Keyword Planner access is not implemented in this "
                "release. For now, export keyword ideas as CSV and import with "
                "--provider local-csv."
            ),
        )
