#!/usr/bin/env python3
"""Phase N — public launch readiness checks.

    python scripts/launch_check.py
    python scripts/launch_check.py --base-url https://testnet.syntrends.com
    python scripts/launch_check.py --require-persona --require-packages

Exit 0 = gates look launchable (warnings allowed unless --strict / require flags).
Does not mutate DNS, secrets, or registries.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
URLS_PATH = REPO / "ops" / "public_urls.json"


def _load_urls() -> dict:
    return json.loads(URLS_PATH.read_text(encoding="utf-8"))


def _get_json(url: str, timeout: float = 30.0) -> tuple[int, dict | list | None, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "syntrends-launch-check/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            code = int(resp.status)
            try:
                return code, json.loads(body), body
            except json.JSONDecodeError:
                return code, None, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            data = json.loads(body) if body else None
        except json.JSONDecodeError:
            data = None
        return int(e.code), data, body
    except Exception as e:  # noqa: BLE001 — report as fail line
        return 0, None, str(e)


def _ok(msg: str) -> None:
    print(f"OK    {msg}")


def _warn(msg: str) -> None:
    print(f"WARN  {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL  {msg}", file=sys.stderr)


def _get_status(url: str, timeout: float = 30.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "syntrends-launch-check/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return int(e.code), body
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def check_http_surface(base: str) -> list[str]:
    failures: list[str] = []
    code, data, raw = _get_json(f"{base}/health")
    if code == 200 and isinstance(data, dict) and (data.get("status") == "ok" or data.get("ok") is True or "ok" in raw.lower()):
        _ok(f"/health HTTP {code}")
    elif code == 200:
        _ok(f"/health HTTP {code}")
    else:
        _fail(f"/health HTTP {code}: {raw[:200]}")
        failures.append("health")

    code, _, raw = _get_json(f"{base}/ready")
    if code == 200:
        _ok("/ready HTTP 200")
    else:
        _fail(f"/ready HTTP {code}: {raw[:200]}")
        failures.append("ready")

    code, st, raw = _get_json(f"{base}/status")
    if code != 200 or not isinstance(st, dict):
        _fail(f"/status HTTP {code}: {raw[:200]}")
        failures.append("status")
        return failures

    env = st.get("env")
    if env != "testnet":
        _fail(f"/status env={env!r} (want testnet)")
        failures.append("env")
    else:
        _ok(f"/status env=testnet network={st.get('network')} height={st.get('block_height')}")

    if st.get("ready") is False:
        _warn("/status ready=false")
    if st.get("persistence_ok") is False:
        _warn("/status persistence_ok=false")

    kyc = st.get("kyc_provider")
    if kyc:
        _ok(f"/status kyc_provider={kyc}")
    return failures


def check_html_surface(base: str) -> list[str]:
    """Owner portal + status dashboard must not 404 if DNS is live."""
    failures: list[str] = []
    for path in ("/owners/", "/status/", "/join.html", "/explorer/"):
        code, body = _get_status(f"{base}{path}")
        if code == 200:
            _ok(f"{path} HTTP 200")
        else:
            _fail(f"{path} HTTP {code}: {body[:160]}")
            failures.append(path.strip("/") or "html")
    return failures


def check_owners_config(base: str, require_persona: bool) -> list[str]:
    failures: list[str] = []
    code, cfg, raw = _get_json(f"{base}/owners/api/config")
    if code != 200 or not isinstance(cfg, dict):
        _fail(f"/owners/api/config HTTP {code}: {raw[:200]}")
        failures.append("owners_config")
        return failures

    kyc = cfg.get("kyc_provider")
    demo = cfg.get("demo_admin_approve_enabled")
    beta = cfg.get("public_beta")
    _ok(f"owners config kyc={kyc} demo_approve={demo} public_beta={beta}")

    if demo is True:
        _fail("demo_admin_approve_enabled=true on public launch URL")
        failures.append("demo_approve")
    if require_persona and kyc != "persona":
        _fail(f"kyc_provider={kyc!r} (want persona)")
        failures.append("persona")
    elif kyc != "persona":
        _warn(f"kyc_provider={kyc!r} — set Persona before inviting strangers")
    return failures


def check_packages(version: str, require: bool) -> list[str]:
    failures: list[str] = []
    # PyPI JSON API
    code, data, raw = _get_json(f"https://pypi.org/pypi/syntrends/json", timeout=20.0)
    if code == 200 and isinstance(data, dict):
        ver = data.get("info", {}).get("version")
        _ok(f"PyPI syntrends version={ver}")
        if version and ver != version:
            _warn(f"PyPI version {ver} != expected {version}")
    else:
        msg = f"PyPI syntrends not found (HTTP {code})"
        if require:
            _fail(msg)
            failures.append("pypi")
        else:
            _warn(msg + " — publish via docs/PUBLISH.md")

    # npm registry
    code, data, raw = _get_json("https://registry.npmjs.org/@syntrends/sdk", timeout=20.0)
    if code == 200 and isinstance(data, dict):
        ver = data.get("dist-tags", {}).get("latest") or (data.get("versions") or {}) and None
        if not ver and isinstance(data.get("versions"), dict):
            ver = sorted(data["versions"].keys())[-1] if data["versions"] else None
        _ok(f"npm @syntrends/sdk latest={ver}")
        if version and ver and ver != version:
            _warn(f"npm version {ver} != expected {version}")
    else:
        msg = f"npm @syntrends/sdk not found (HTTP {code})"
        if require:
            _fail(msg)
            failures.append("npm")
        else:
            _warn(msg + " — publish via docs/PUBLISH.md")
    return failures


def main() -> int:
    urls = _load_urls()
    primary = urls["public_testnet"]["primary"]
    fallback = urls["public_testnet"]["fallback"]
    expected_ver = urls.get("packages", {}).get("version", "0.1.0")

    p = argparse.ArgumentParser(description="Phase N public launch checks")
    p.add_argument(
        "--base-url",
        default=os.environ.get("SYNTRENDS_URL", "").rstrip("/") or None,
        help=f"Public testnet base (default SYNTRENDS_URL or {primary})",
    )
    p.add_argument("--require-persona", action="store_true", help="Fail unless KYC_PROVIDER=persona")
    p.add_argument("--require-packages", action="store_true", help="Fail unless PyPI+npm packages exist")
    p.add_argument("--skip-packages", action="store_true", help="Do not probe registries")
    p.add_argument("--also-fallback", action="store_true", help=f"Also probe {fallback}")
    p.add_argument(
        "--no-auto-fallback",
        action="store_true",
        help="Do not retry fallback if primary is unreachable",
    )
    args = p.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    base = (args.base_url or primary).rstrip("/")
    print("== launch_check ==")
    print(f"canonical primary: {primary}")

    # Auto-fallback when probing the default primary and it is unreachable.
    code, _, raw = _get_json(f"{base}/health")
    if (
        code == 0
        and not args.base_url
        and not args.no_auto_fallback
        and base.rstrip("/") == primary.rstrip("/")
    ):
        _warn(f"primary unreachable ({raw[:120]}); trying fallback {fallback}")
        base = fallback.rstrip("/")

    bases = [base]
    if args.also_fallback and fallback.rstrip("/") not in bases:
        bases.append(fallback.rstrip("/"))

    failures: list[str] = []
    for b in bases:
        print(f"\n-- {b} --")
        failures.extend(check_http_surface(b))
        failures.extend(check_html_surface(b))
        failures.extend(check_owners_config(b, args.require_persona))

    explorer = "https://explorer.syntrends.com/explorer/"
    print(f"\n-- {explorer} --")
    ex_code, ex_body = _get_status(explorer)
    if ex_code == 200:
        _ok("explorer.syntrends.com HTTP 200")
    else:
        _warn(
            f"explorer.syntrends.com HTTP {ex_code} — add DNS/CNAME + fly certs; "
            f"path explorer remains on {primary}/explorer/"
        )

    if not args.skip_packages:
        print("\n-- packages --")
        failures.extend(check_packages(expected_ver, args.require_packages))

    print()
    if failures:
        _fail(f"{len(failures)} gate(s) failed: {', '.join(failures)}")
        print("See docs/PUBLIC_LAUNCH.md", file=sys.stderr)
        return 1
    _ok("launch gates passed")
    print("Next: invite testers (docs/INVITE_TEMPLATE.md) + tag testnet-v1.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
