"""Optional provider adapters for keyword and search-evidence data.

The core pipeline (inventory, link graph, context pack) is provider-free.
Providers are how *external* data — keyword volume, search performance,
SERP rows — gets normalised into local artifacts that the core pipeline
can read.

Design rules:

1. Providers are optional. The base package never imports a provider's
   third-party dependency at the top level. If a vendor SDK is needed,
   it is imported lazily inside the provider's ``run`` method.
2. Providers must work offline. Local-CSV providers are first-class.
   Live API providers are stubs in 0.x and return a structured
   ``not_configured`` result instead of raising.
3. Providers do not mutate the workspace directly. They return a
   ``ProviderResult``; the CLI is the only thing that writes to disk.
"""

from .base import (
    KeywordProvider,
    ProviderConfigurationError,
    ProviderError,
    ProviderNotConfiguredError,
    SearchPerformanceProvider,
)
from .registry import (
    KEYWORD_PROVIDERS,
    SEARCH_PERFORMANCE_PROVIDERS,
    available_providers,
    get_keyword_provider,
    get_search_performance_provider,
)

__all__ = [
    "KEYWORD_PROVIDERS",
    "SEARCH_PERFORMANCE_PROVIDERS",
    "KeywordProvider",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderNotConfiguredError",
    "SearchPerformanceProvider",
    "available_providers",
    "get_keyword_provider",
    "get_search_performance_provider",
]
