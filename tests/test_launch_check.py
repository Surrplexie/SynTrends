"""Unit tests for Phase N launch URL map + launch_check helpers."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_public_urls_json_shape():
    data = json.loads((REPO / "ops" / "public_urls.json").read_text(encoding="utf-8"))
    assert data["phase"] == "N"
    assert data["public_testnet"]["primary"].startswith("https://testnet.syntrends.com")
    assert "syntrends-testnet.fly.dev" in data["public_testnet"]["fallback"]
    assert "testnet.syntrends.com" in data["cors_origins_csv"]
    assert data["packages"]["version"] == "0.1.0"
    assert data["public_testnet"]["persona_webhook"].endswith("/owners/api/kyc/webhook")


def test_launch_check_module_imports():
    import importlib.util

    path = REPO / "scripts" / "launch_check.py"
    spec = importlib.util.spec_from_file_location("launch_check", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    urls = mod._load_urls()
    assert urls["fly_app"] == "syntrends-testnet"
    assert hasattr(mod, "check_html_surface")
