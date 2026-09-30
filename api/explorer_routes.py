"""Block explorer JSON API (Phase E) — chain audit view, not a market HUD."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .agent_routes import get_service

router = APIRouter(prefix="/explorer/api", tags=["explorer"])


@router.get("/summary")
def explorer_summary():
    svc = get_service()
    chain = svc.demo.chain
    return {
        "blocks": len(chain.chain),
        "pending_txs": len(chain.pending),
        "valid": chain.is_valid(),
        "agents": len(svc.demo.agents),
    }


@router.get("/blocks")
def list_blocks(limit: int = Query(default=20, ge=1, le=200)):
    svc = get_service()
    blocks = svc.demo.chain.chain[-limit:]
    return [
        {
            "index": b.index,
            "hash": b.hash,
            "previous_hash": b.previous_hash,
            "timestamp": b.timestamp,
            "tx_count": len(b.transactions),
            "nonce": b.nonce,
        }
        for b in reversed(blocks)
    ]


@router.get("/blocks/{index}")
def get_block(index: int):
    svc = get_service()
    for block in svc.demo.chain.chain:
        if block.index == index:
            return {
                "index": block.index,
                "hash": block.hash,
                "previous_hash": block.previous_hash,
                "timestamp": block.timestamp,
                "nonce": block.nonce,
                "transactions": [t.to_dict() for t in block.transactions],
            }
    raise HTTPException(status_code=404, detail="block not found")
