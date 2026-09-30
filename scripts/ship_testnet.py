"""One-command local public testnet: seed → start server → run full E2E.

    python scripts/ship_testnet.py
    python scripts/ship_testnet.py --fresh   # wipe DB and re-seed genesis

Requires: pip install -r requirements.txt

For Docker production deploy see docs/TESTNET.md and deploy/testnet/.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"
DB_PATH = DATA_DIR / "testnet_live.db"
DEFAULT_PORT = int(os.environ.get("PORT", "8091"))
BASE_URL = f"http://127.0.0.1:{DEFAULT_PORT}"


def _env(port: int) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("SYNTRENDS_ENV", "testnet")
    env.setdefault("NETWORK_NAME", "syntrends-testnet-1")
    env.setdefault("HOST", "127.0.0.1")
    env.setdefault("PORT", str(port))
    env.setdefault("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")
    env.setdefault("FAUCET_ENABLED", "1")
    env.setdefault("FAUCET_AMOUNT", "5000")
    env.setdefault("FAUCET_COOLDOWN_SECONDS", "2")  # short for repeated e2e runs
    env.setdefault("KYC_PROVIDER", "demo")
    # Local ship only — public Fly/testnet must NOT set this (Persona webhook instead).
    env.setdefault("ALLOW_DEMO_KYC_APPROVE", "1")
    env.setdefault("REQUIRE_REAL_KYC_ON_TESTNET", "0")
    env.setdefault("CORS_ORIGINS", f"http://127.0.0.1:{port},http://localhost:{port}")
    return env


def seed(fresh: bool) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if fresh and DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Removed {DB_PATH}")
    if fresh or not DB_PATH.exists():
        print("Seeding testnet genesis + trade history…")
        subprocess.check_call(
            [sys.executable, "-m", "demo.seed_testnet", "--output", f"sqlite:///{DB_PATH.as_posix()}"],
            cwd=REPO,
            env=_env(DEFAULT_PORT),
        )
    else:
        print(f"Using existing DB: {DB_PATH}")


def wait_for_health(base_url: str, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url.rstrip('/')}/health", timeout=2.0)
            if r.status_code != 200:
                last = RuntimeError(f"health status {r.status_code}")
                time.sleep(0.4)
                continue
            st = httpx.get(f"{base_url.rstrip('/')}/status", timeout=2.0)
            if st.status_code == 200 and st.json().get("env") == "testnet":
                return
            last = RuntimeError(f"not testnet yet (env={st.json().get('env') if st.status_code == 200 else st.status_code})")
        except Exception as exc:
            last = exc
        time.sleep(0.4)
    raise RuntimeError(f"testnet server did not become ready at {base_url}: {last}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ship local public testnet and run E2E")
    parser.add_argument("--fresh", action="store_true", help="Delete DB and re-seed genesis")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-e2e", action="store_true", help="Start server only (blocking)")
    parser.add_argument("--stop-after-e2e", action="store_true", help="Exit after E2E (for CI)")
    parser.add_argument("--seed-only", action="store_true", help="Seed DB and exit")
    args = parser.parse_args()

    port = args.port
    base = f"http://127.0.0.1:{port}"
    env = _env(port)

    seed(args.fresh)
    if args.seed_only:
        print(f"Seeded → {DB_PATH}")
        return

    print(f"\nStarting testnet on {base} …")
    proc = subprocess.Popen(
        [sys.executable, "-m", "demo.run_testnet"],
        cwd=REPO,
        env=env,
    )

    try:
        wait_for_health(base)
        print(f"Server healthy at {base}")
        print(f"  Owner portal:  {base}/owners/   (or {base}/owners)")
        print(f"  Status page:   {base}/status/   (JSON API: {base}/status)")
        print(f"  Explorer:      {base}/explorer/")
        print(f"  Faucet info:   {base}/testnet/faucet")
        print(f"  Note: GET /demo/keys returns 404 on testnet — that is intentional.")

        if args.no_e2e:
            print("\nServer running (Ctrl+C to stop).")
            proc.wait()
            return

        print("\nRunning full E2E testnet loop…")
        e2e = subprocess.run(
            [sys.executable, "-m", "demo.e2e_testnet"],
            cwd=REPO,
            env={**env, "SYNTRENDS_URL": base, "E2E_WAIT_SECONDS": "5"},
        )
        if e2e.returncode != 0:
            sys.exit(e2e.returncode)

        print("\n" + "=" * 72)
        print("PUBLIC TESTNET READY (local)")
        print("=" * 72)
        print(f"  Owner portal:  {base}/owners/")
        print(f"  Status:        {base}/status/")
        print(f"  Deploy to VPS: docs/TESTNET.md + deploy/testnet/")
        print(f"  Deploy to Fly: deploy/fly.testnet.toml")

        if args.stop_after_e2e:
            print("\nE2E complete — stopping server.")
            return

        print(f"\n  Server still up at {base} — Ctrl+C to stop.")
        proc.wait()
    except KeyboardInterrupt:
        print("\nStopping testnet…")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
