"""End-to-end public testnet verification — full owner → agent → faucet → trade loop.

Run against a live testnet server (local or deployed):

    SYNTRENDS_URL=https://testnet.syntrends.com python -m demo.e2e_testnet
    python -m demo.e2e_testnet --base-url https://testnet.syntrends.com
    python -m demo.e2e_testnet --base-url https://syntrends-testnet.fly.dev --check-pause
    bash scripts/ci_fly_e2e.sh   # wake Fly + wait + full E2E (CI parity)

Exit code 0 = all checks passed.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid

import httpx

from chain.stp import ParsedError, ParsedTrade, parse_stream
from sdk.python.syntrends.client import SynTrendsClient

DEFAULT_BASE = os.environ.get("SYNTRENDS_URL", "http://127.0.0.1:8091")
FLY_TESTNET_HINT = "https://testnet.syntrends.com"
ATTESTATION = "I agree."


def _persona_webhook_payload(owner_id: str) -> bytes:
    import json

    return json.dumps({
        "data": {
            "attributes": {
                "name": "inquiry.approved",
                "payload": {
                    "data": {
                        "type": "inquiry",
                        "id": "inq_e2e",
                        "attributes": {"status": "approved", "reference-id": owner_id},
                    }
                },
            }
        }
    }).encode("utf-8")


def _persona_sign(secret: str, body: bytes) -> str:
    import hashlib
    import hmac

    ts = int(time.time())
    signed_payload = f"{ts}.{body.decode('utf-8')}"
    sig = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _approve_via_persona_webhook(
    http: httpx.Client,
    owner_id: str,
    owner_headers: dict[str, str],
) -> None:
    """Simulate Persona inquiry.approved for CI/public-beta E2E.

    Requires PERSONA_WEBHOOK_SECRET to match the server (Fly secret / local env).
    """
    secret = os.environ.get("PERSONA_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise CheckFailed(
            "KYC provider is Persona but PERSONA_WEBHOOK_SECRET is unset — "
            "cannot complete automated E2E without a signed webhook"
        )
    start = http.post("/owners/api/kyc/start", headers=owner_headers)
    if start.status_code != 200:
        raise CheckFailed(f"kyc start failed: {start.status_code} {start.text}")
    body = _persona_webhook_payload(owner_id)
    sig = _persona_sign(secret, body)
    resp = http.post(
        "/owners/api/kyc/webhook",
        content=body,
        headers={"Content-Type": "application/json", "persona-signature": sig},
    )
    if resp.status_code != 200:
        raise CheckFailed(f"persona webhook failed: {resp.status_code} {resp.text}")
    if resp.json().get("decision") != "approved":
        raise CheckFailed(f"persona webhook unexpected decision: {resp.text}")


class CheckFailed(Exception):
    pass


def _ok(label: str) -> None:
    print(f"  OK  {label}")


def _step(title: str) -> None:
    print(f"\n== {title} ==")


def run_e2e(
    base_url: str = DEFAULT_BASE,
    *,
    admin_kyc: bool = True,
    check_pause: bool = False,
    http: httpx.Client | None = None,
) -> dict[str, str]:
    """Run the full testnet onboarding + trade loop. Returns agent key + agent_id."""
    base = base_url.rstrip("/")
    email = f"e2e-{uuid.uuid4().hex[:10]}@testnet.local"
    agent_id = f"agent-e2e-{uuid.uuid4().hex[:8]}"

    owns_http = http is None
    if http is None:
        http = httpx.Client(base_url=base, timeout=30.0)

    try:
        api_key = _run_e2e_inner(
            http,
            base,
            email=email,
            agent_id=agent_id,
            admin_kyc=admin_kyc,
            check_pause=check_pause,
        )
    finally:
        if owns_http:
            http.close()

    print(f"\nAll E2E checks passed against {base}")
    print(f"  owner email: {email}")
    print(f"  agent_id:    {agent_id}")
    print(f"  api_key:     {api_key[:28]}...")
    return {"email": email, "agent_id": agent_id, "api_key": api_key}


def _run_e2e_inner(
    http: httpx.Client,
    base: str,
    *,
    email: str,
    agent_id: str,
    admin_kyc: bool,
    check_pause: bool,
) -> str:
    _step("Network liveness")
    health = http.get("/health")
    if health.status_code != 200:
        raise CheckFailed(f"/health returned {health.status_code}")
    _ok("/health")

    status = http.get("/status").json()
    if status.get("env") != "testnet":
        raise CheckFailed(f"expected env=testnet, got {status.get('env')!r}")
    if not status.get("faucet_enabled"):
        raise CheckFailed("faucet should be enabled on testnet")
    _ok(f"status env={status['env']} network={status['network']} blocks={status.get('block_height')}")

    if http.get("/demo/keys").status_code != 404:
        raise CheckFailed("/demo/keys must be 404 on testnet")
    _ok("/demo/keys blocked")

    faucet_info = http.get("/testnet/faucet").json()
    if not faucet_info.get("enabled"):
        raise CheckFailed("GET /testnet/faucet says disabled")
    _ok(f"faucet amount={faucet_info['amount']}")

    _step("Owner portal — register + agreements + KYC")
    reg = http.post("/owners/api/register", json={"email": email, "password": "testnet-e2e-pass1"})
    if reg.status_code != 200:
        raise CheckFailed(f"register failed: {reg.status_code} {reg.text}")
    owner_token = reg.json()["session_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    for path, body in (
        ("/owners/api/agreements/accept", None),
        ("/owners/api/syntrendrules/accept", {"attestation": ATTESTATION}),
        ("/owners/api/seeprules/accept", {"attestation": ATTESTATION}),
    ):
        r = http.post(path, headers=owner_headers, json=body)
        if r.status_code != 200:
            raise CheckFailed(f"{path} failed: {r.status_code} {r.text}")
    _ok("owner agreements + syntrendrules + seeprules")

    kyc = http.post(
        "/owners/api/kyc/submit",
        headers=owner_headers,
        json={"full_name": "E2E Tester", "country": "US", "attestation": True},
    )
    if kyc.status_code != 200:
        raise CheckFailed(f"kyc submit failed: {kyc.status_code} {kyc.text}")
    owner_id = http.get("/owners/api/me", headers=owner_headers).json()["owner_id"]

    if admin_kyc:
        portal_cfg = http.get("/owners/api/config").json()
        if portal_cfg.get("demo_admin_approve_enabled"):
            approve = http.post("/owners/api/kyc/approve", json={"owner_id": owner_id})
            if approve.status_code != 200:
                raise CheckFailed(f"kyc approve failed: {approve.status_code} {approve.text}")
            _ok(f"KYC approved (demo provider) owner_id={owner_id}")
        elif portal_cfg.get("kyc_provider") == "persona":
            _approve_via_persona_webhook(http, owner_id, owner_headers)
            _ok(f"KYC approved (Persona webhook) owner_id={owner_id}")
        else:
            raise CheckFailed(
                "demo KYC approve is disabled and no Persona webhook secret — "
                "set ALLOW_DEMO_KYC_APPROVE=1 for local ship, or PERSONA_WEBHOOK_SECRET for public beta E2E"
            )
    else:
        raise CheckFailed("admin_kyc=False not supported in automated e2e")

    connect = http.post(
        "/owners/api/agents/connect",
        headers=owner_headers,
        json={"agent_id": agent_id},
    )
    if connect.status_code != 200:
        raise CheckFailed(f"agent connect failed: {connect.status_code} {connect.text}")
    api_key = connect.json()["api_key"]
    if not api_key.startswith("st_agent_"):
        raise CheckFailed(f"unexpected api_key prefix: {api_key[:20]}")
    _ok(f"agent key issued for {agent_id}")

    if check_pause:
        _step("Owner pause / resume")
        pause = http.post(
            "/owners/api/agents/pause",
            headers=owner_headers,
            json={"agent_id": agent_id},
        )
        if pause.status_code != 200 or not pause.json().get("paused"):
            raise CheckFailed(f"pause failed: {pause.status_code} {pause.text}")
        _ok(f"paused {agent_id}")

        client_pre = SynTrendsClient(base_url=base, api_key=api_key, client=http)
        client_pre.agree_syntrends()
        client_pre.agree_seepnews()

        faucet_paused = http.post("/testnet/faucet", headers={"Authorization": f"Bearer {api_key}"})
        if faucet_paused.status_code != 403:
            raise CheckFailed(f"faucet should 403 when paused, got {faucet_paused.status_code}")
        _ok("faucet blocked while paused")

        buy_paused = client_pre.buy(ticker="GEM", fiat_amount=10.0)
        pause_errors = [r for r in buy_paused if isinstance(r, ParsedError)]
        if not pause_errors or "PAUSED" not in pause_errors[0].code.upper():
            raise CheckFailed(f"buy should return AGENT_PAUSED, got {buy_paused}")
        _ok("trade blocked while paused")

        resume = http.post(
            "/owners/api/agents/resume",
            headers=owner_headers,
            json={"agent_id": agent_id, "gradual_seconds": 0},
        )
        if resume.status_code != 200 or resume.json().get("writes_blocked"):
            raise CheckFailed(f"resume failed: {resume.status_code} {resume.text}")
        _ok(f"resumed {agent_id}")

    _step("Agent — contracts, faucet, snapshot, trade")
    client = SynTrendsClient(base_url=base, api_key=api_key, client=http)
    client.agree_syntrends()
    client.agree_seepnews()
    _ok("agent accepted syntrendrules + seeprules")

    faucet = http.post("/testnet/faucet", headers={"Authorization": f"Bearer {api_key}"})
    if faucet.status_code != 200:
        raise CheckFailed(f"faucet failed: {faucet.status_code} {faucet.text}")
    if "ST/" not in faucet.text and "FIAT" not in faucet.text:
        raise CheckFailed("faucet response missing STP deposit lines")
    _ok("faucet credited simulated fiat")

    view = client.snapshot_view()
    if "GEM" not in view.tickers:
        raise CheckFailed("snapshot missing $GEM ticker (run seed_testnet first)")
    _ok(f"snapshot GEM price={view.price('GEM'):.6f} freeze={view.tickers['GEM'].freeze}")

    buy_records = client.buy(ticker="GEM", fiat_amount=100.0)
    errors = [r for r in buy_records if isinstance(r, ParsedError)]
    if errors:
        raise CheckFailed(f"buy rejected: {errors[0].msg}")
    trades = [r for r in buy_records if isinstance(r, ParsedTrade)]
    if not trades:
        raise CheckFailed("buy returned no ParsedTrade records")
    _ok(f"trade BUY {trades[0].coins:.4f} coins @ ${trades[0].price_after:.6f}")

    post_records = client.post_seepnews(
        "System",
        "E2E testnet smoke post — simulated only.",
        mentions=["GEM"],
        hashtags=["testnet", "e2e", "syntrends"],
    )
    if not post_records:
        raise CheckFailed("seepnews post returned no records")
    _ok("seepnews System post accepted")

    _step("Human-facing pages")
    status_html = http.get("/status/")
    if status_html.status_code != 200 or "Network Status" not in status_html.text:
        raise CheckFailed("/status/ HTML dashboard missing")
    _ok("/status/ dashboard")

    owners_html = http.get("/owners/")
    if owners_html.status_code != 200:
        raise CheckFailed("/owners/ not served")
    _ok("/owners/ portal")

    client.close()

    return api_key


def main() -> None:
    parser = argparse.ArgumentParser(description="SynTrends public testnet E2E")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE,
        help=f"Testnet base URL (default: SYNTRENDS_URL or {DEFAULT_BASE})",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=float(os.environ.get("E2E_WAIT_SECONDS", "30")),
        help="Retry window when server is unreachable (cold start)",
    )
    parser.add_argument(
        "--check-pause",
        action="store_true",
        default=os.environ.get("E2E_CHECK_PAUSE", "").strip() in ("1", "true", "yes"),
        help="Verify owner pause/resume blocks and restores agent writes",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    print(f"E2E target: {base}")
    if args.check_pause:
        print("E2E mode: includes owner pause/resume check")

    deadline = time.time() + args.wait_seconds
    last_err: Exception | None = None

    while time.time() < deadline:
        try:
            run_e2e(base, check_pause=args.check_pause)
            return
        except (httpx.ConnectError, httpx.ReadTimeout) as exc:
            last_err = exc
            time.sleep(0.5)
        except CheckFailed as exc:
            print(f"\nE2E FAILED: {exc}", file=sys.stderr)
            sys.exit(1)

    hint = ""
    if base.startswith("http://127.0.0.1") or base.startswith("http://localhost"):
        hint = (
            f"\nHint: no local server on {base}. For Fly testnet run:\n"
            f"  python -m demo.e2e_testnet --base-url {FLY_TESTNET_HINT}\n"
            f"  # or: $env:SYNTRENDS_URL = \"{FLY_TESTNET_HINT}\"; python -m demo.e2e_testnet"
        )
    print(f"\nE2E FAILED: server not reachable at {base}: {last_err}{hint}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
