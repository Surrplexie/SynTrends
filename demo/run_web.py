"""Run Phase D/E: human web + owner portal + agent API (KYC-gated keys).

    python -m demo.run_web

Serves on http://127.0.0.1:8090

  /                 syntrends.com content (connect guide, agreements, KYC only)
  /seepnews/        seepnews.com content (same onboarding scope)
  /owners/          owner portal (register, KYC, connect agent, tax export)
  /explorer/        block explorer (chain audit)
  /vendor/          3rdPS vendor reference HUD
  /health, /snapshot, …  agent API (same as Phase B)
  /.well-known/syntrends  agent discovery JSON

Set DATABASE_URL for SQLite or PostgreSQL persistence (see docker-compose.yml).
Set HOST/PORT to override the bind address (defaults to 0.0.0.0:8090, which
works both for local access via 127.0.0.1 and for Docker/reverse-proxy setups
where another container must reach this one by service name).

Agent API without human sites (open key bootstrap for tests):

    python -m demo.run_api    # port 8080
"""

import os

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8090"))
    uvicorn.run("api.web_app:app", host=host, port=port, reload=False)
