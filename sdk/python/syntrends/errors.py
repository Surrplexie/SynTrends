"""SDK-level exceptions mapped from HTTP status codes."""

from __future__ import annotations


class SynTrendsAPIError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class AuthenticationError(SynTrendsAPIError):
    """401 — missing or invalid API key."""


class ForbiddenError(SynTrendsAPIError):
    """403 — a 3rdPS (read-only) key attempted a write."""


class NotFoundError(SynTrendsAPIError):
    """404 — unknown route (shouldn't normally happen with this client)."""


class RateLimitedError(SynTrendsAPIError):
    """429 — 3rdPS key exceeded its request budget."""
