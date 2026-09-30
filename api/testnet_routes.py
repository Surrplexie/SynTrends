"""Public testnet routes — faucet, network status (Phase G)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from .agent_routes import get_key, get_service
from .auth import AuthError
from .agent_pause import AgentPauseError
from .service import FaucetError, RateLimitError, SynTrendsAPIService

router = APIRouter(tags=["testnet"])


@router.get("/status")
def network_status():
    """Public network status — block height, agents, uptime, faucet, persistence."""
    svc = get_service()
    return svc.status()


@router.get("/ready")
def ready():
    """Readiness probe — 200 if process + persistence OK; 503 if DB unreachable."""
    from fastapi.responses import JSONResponse

    svc = get_service()
    body, code = svc.readiness()
    return JSONResponse(body, status_code=code)


@router.get("/testnet/faucet")
def faucet_info():
    svc = get_service()
    return svc.faucet_info()


@router.post("/testnet/faucet")
def claim_faucet(token: Annotated[str, Depends(get_key)]):
    """Credit simulated testnet fiat to the agent bound to your API key.

    Rate-limited per agent_id by ``FAUCET_COOLDOWN_SECONDS`` (default 1 hour).
    Requires an agent key — get one from the owner portal after KYC."""
    svc = get_service()
    try:
        key = svc.authenticate(token, write=False)
        body = svc.claim_faucet(key)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AgentPauseError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FaucetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(body, media_type="text/plain; charset=utf-8")
