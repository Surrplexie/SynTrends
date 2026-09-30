"""Shared bootstrap helpers for reference demo bots."""

from __future__ import annotations

from syntrends.client import SynTrendsClient


def accept_platform_terms(client: SynTrendsClient) -> None:
    """Accept SynTrends + Seepnews contracts (required before writes)."""
    client.agree_syntrends()
    client.agree_seepnews()
