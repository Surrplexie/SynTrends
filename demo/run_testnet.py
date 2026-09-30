"""Run the SynTrends public testnet (Phase G).

    SYNTRENDS_ENV=testnet python -m demo.run_testnet

Set DATABASE_URL for Postgres/SQLite persistence. Seed genesis history:

    SYNTRENDS_ENV=testnet python -m demo.seed_testnet

Serves on http://0.0.0.0:8090 (override with HOST/PORT):

  /status              network status JSON + /status/ HTML dashboard
  /testnet/faucet      simulated fiat faucet (agent key required)
  /owners/             owner portal (register → KYC → agent key)
  /explorer/           block explorer
  /snapshot, /stream/* agent API (STP/1.0)

No /demo/keys — agents must onboard through the owner portal.
"""

import os

import uvicorn

if __name__ == "__main__":
    os.environ.setdefault("SYNTRENDS_ENV", "testnet")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8090"))
    uvicorn.run("api.testnet_app:app", host=host, port=port, reload=False)
