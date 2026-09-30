"""Reference Python SDK for the SynTrends Agent API (STP/1.0 over HTTP).

Install::

    pip install syntrends

Usage::

    from syntrends import SynTrendsClient

    client = SynTrendsClient(
        base_url="https://testnet.syntrends.com",
        api_key="st_agent_...",
    )
    view = client.snapshot_view()
    print(view.price("GEM"))
"""

from .client import DEFAULT_BASE_URL, SynTrendsClient
from .errors import (
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    SynTrendsAPIError,
)
from .state import MarketView, TickerSnapshot

__version__ = "0.1.0"

__all__ = [
    "SynTrendsClient",
    "DEFAULT_BASE_URL",
    "MarketView",
    "TickerSnapshot",
    "SynTrendsAPIError",
    "AuthenticationError",
    "ForbiddenError",
    "NotFoundError",
    "RateLimitedError",
    "__version__",
]
