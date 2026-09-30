"""E2E script helpers — in-process check_pause smoke."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app_factory import create_app, get_service
from api.config import Settings
from demo.e2e_testnet import run_e2e


@pytest.fixture
def testnet_http():
    settings = Settings(
        env="testnet",
        network_name="syntrends-testnet-1",
        faucet_enabled=True,
        faucet_cooldown_seconds=1.0,
        allow_demo_kyc_approve=True,
        require_real_kyc_on_testnet=False,
    )
    app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    with TestClient(app) as client:
        get_service().seed_testnet()
        yield client


def test_run_e2e_check_pause_in_process(testnet_http):
    """Full owner loop + pause/resume against in-process testnet (CI logic parity)."""
    result = run_e2e("http://testserver", check_pause=True, http=testnet_http)
    assert result["api_key"].startswith("st_agent_")
    assert result["agent_id"].startswith("agent-e2e-")
