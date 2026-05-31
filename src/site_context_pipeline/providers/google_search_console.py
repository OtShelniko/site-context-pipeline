"""Google Search Console Search Analytics adapter (stub for 0.1).

Like the Google Ads stub, this is interface-only in 0.1. The live
implementation will use the
``searchconsole.searchanalytics().query()`` endpoint (see
https://developers.google.com/webmaster-tools/v1/searchanalytics).

Planned (future) behaviour
--------------------------

The adapter will accept a ``provider_config`` with:

* ``site_url``       — the verified property in Search Console
                       (``sc-domain:example.com`` or
                       ``https://www.example.com/``);
* ``credentials``    — path to a service-account JSON file *or*
                       OAuth refresh-token bundle;
* ``date_range``     — ``{"start": "...", "end": "..."}`` (ISO dates);
* ``dimensions``     — subset of ``["query", "page", "country", "device", "date"]``;
* ``filters``        — optional Search Analytics dimension filters.

Normalised output (per row):

* ``query``       — the search term;
* ``source_url``  — the page that received the impression;
* ``impressions``;
* ``clicks``;
* ``ctr``  (fraction in [0..1]);
* ``position`` — average position;
* ``geo``       — country if the request grouped by country;
* extra dimension values are preserved in ``raw``.

Required dependencies (when live mode lands)
--------------------------------------------

The live adapter will depend on Google's Python client libraries:

    pip install google-api-python-client google-auth-oauthlib

These will live behind an optional extra (``site-context-pipeline[gsc]``)
so the base package stays dependency-free.

Until then, the adapter returns a ``not_configured`` result and points
users at the local CSV import.
"""

from __future__ import annotations

from typing import Any

from ..schemas import ProviderResult
from .base import SearchPerformanceProvider, blocked_result


class GoogleSearchConsoleProvider(SearchPerformanceProvider):
    """Stub adapter. Always returns ``not_configured`` in 0.1."""

    provider_name = "google-search-console"

    def run(
        self,
        *,
        source: str | None = None,
        provider_config: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return blocked_result(
            self.provider_name,
            reason="not_configured",
            suggestion=(
                "Live Google Search Console access is not implemented in this "
                "release. For now, export the Performance report as CSV and "
                "import with --provider local-gsc-csv."
            ),
        )
