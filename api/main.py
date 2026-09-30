"""SynTrends Phase B HTTP API — re-exports the default agent-only app."""

from .app_factory import app, create_app, get_service

__all__ = ["app", "create_app", "get_service"]
