"""Week-1 public-beta ops: always-on Fly + marketing portal CTAs."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WEB = REPO / "web"


def test_fly_testnet_toml_always_on():
    text = (REPO / "deploy" / "fly.testnet.toml").read_text(encoding="utf-8")
    assert "min_machines_running = 1" in text
    assert "auto_stop_machines = 'off'" in text
    assert "min_machines_running = 0" not in text
    assert "auto_stop_machines = 'stop'" not in text


def test_fly_helpers_require_park_confirm():
    ps1 = (REPO / "scripts" / "fly_testnet.ps1").read_text(encoding="utf-8")
    sh = (REPO / "scripts" / "fly_testnet.sh").read_text(encoding="utf-8")
    assert "park confirm" in ps1
    assert "park confirm" in sh
    assert "ensure" in ps1 and "ensure" in sh
    assert "Invoke-Ensure" in ps1
    assert "init" in ps1


def test_marketing_ctas_point_at_public_owners_portal():
    needle = "https://testnet.syntrends.com/owners/"
    hits = 0
    for sub in ("syntrends", "seepnews"):
        for path in (WEB / sub).glob("*.html"):
            text = path.read_text(encoding="utf-8")
            if needle in text:
                hits += 1
                assert "data-portal" in text
                assert "portal-link.js" in text
    assert hits >= 8, f"expected marketing pages to deep-link owners, got {hits}"


def test_portal_link_script_present():
    js = (WEB / "shared" / "portal-link.js").read_text(encoding="utf-8")
    assert "testnet.syntrends.com/owners/" in js
    assert "data-portal" in js
