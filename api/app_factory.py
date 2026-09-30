"""FastAPI application factory — agent API with optional Phase D/E/F web stack."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import agent_routes
from .config import Settings
from .explorer_routes import router as explorer_router
from .owner_routes import router as owner_router
from .persistence import Persistence
from .service import SynTrendsAPIService
from .testnet_routes import router as testnet_router

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = REPO_ROOT / "web"

_service: SynTrendsAPIService | None = None


def get_service() -> SynTrendsAPIService:
    assert _service is not None
    return _service


def create_app(
    *,
    require_owner_kyc: bool = False,
    mount_web: bool = False,
    database_url: str | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """Build the FastAPI app. `settings` (or env vars via `Settings.from_env()`)
    control production-shape concerns: DB backend, CORS allowlist, and which
    KYC provider issues agent keys. `database_url` remains a convenience
    override for demo scripts and tests."""
    global _service

    resolved_settings = settings or Settings.from_env()
    if database_url is not None:
        resolved_settings = replace(resolved_settings, database_url=database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _service
        db_url = resolved_settings.database_url if mount_web else None
        persistence = Persistence(db_url) if db_url else None
        _service = SynTrendsAPIService(
            require_owner_kyc=require_owner_kyc,
            persistence=persistence,
            settings=resolved_settings,
        )
        keys = _service.load_or_seed()
        app.state.demo_keys = keys
        agent_routes.configure_service(get_service)
        yield
        _service = None

    version = "0.4.0" if mount_web else "0.2.0"
    app = FastAPI(
        title="SynTrends" if mount_web else "SynTrends Agent API",
        description="Agent API + human onboarding web + persistence + KYC provider (Phase F).",
        version=version,
        lifespan=lifespan,
    )

    if mount_web:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=resolved_settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(agent_routes.router)
    app.include_router(testnet_router)
    if mount_web:
        app.include_router(owner_router)
        app.include_router(explorer_router)
        _add_html_trailing_slash_redirects(app)
        _mount_human_sites(app)

    return app


def _add_html_trailing_slash_redirects(app: FastAPI) -> None:
    """Static site mounts require a trailing slash; bare paths 404 without this."""
    for path in ("/owners", "/explorer", "/seepnews", "/vendor"):
        dest = f"{path}/"

        def _redirect(_dest: str = dest) -> RedirectResponse:
            return RedirectResponse(url=_dest, status_code=307)

        app.add_api_route(path, _redirect, methods=["GET"], include_in_schema=False)


def _mount_human_sites(app: FastAPI) -> None:
    shared = WEB_ROOT / "shared"
    if shared.is_dir():
        app.mount("/shared", StaticFiles(directory=shared), name="shared")

    for mount_path, subdir in (
        ("/seepnews", "seepnews"),
        ("/owners", "owners"),
        ("/explorer", "explorer"),
        ("/vendor", "vendor"),
        ("/status", "status"),
    ):
        directory = WEB_ROOT / subdir
        if directory.is_dir():
            app.mount(mount_path, StaticFiles(directory=directory, html=True), name=f"{subdir}_site")

    syntrends_dir = WEB_ROOT / "syntrends"
    if syntrends_dir.is_dir():
        app.mount("/", StaticFiles(directory=syntrends_dir, html=True), name="syntrends_site")


app = create_app(require_owner_kyc=False, mount_web=False)
