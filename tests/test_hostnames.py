from fastapi.testclient import TestClient

from api.app_factory import create_app
from api.config import Settings
from api.hostnames import is_explorer_host, root_redirect_for_host


def test_explorer_hosts():
    assert is_explorer_host("explorer.syntrends.com")
    assert is_explorer_host("EXPLORER.syntrends.com:443")
    assert is_explorer_host("www.explorer.syntrends.com")
    assert is_explorer_host("explorer.testnet.syntrends.com")
    assert not is_explorer_host("testnet.syntrends.com")
    assert not is_explorer_host("syntrends.com")
    assert not is_explorer_host(None)


def test_root_redirect_map():
    assert root_redirect_for_host("owners.testnet.syntrends.com") == "/owners/"
    assert root_redirect_for_host("api.testnet.syntrends.com") == "/.well-known/syntrends"
    assert root_redirect_for_host("status.testnet.syntrends.com") == "/status/"
    assert root_redirect_for_host("explorer.testnet.syntrends.com") == "/explorer/"
    assert root_redirect_for_host("testnet.syntrends.com") is None


def test_split_hostname_roots_redirect():
    settings = Settings(env="testnet", network_name="syntrends-testnet-1")
    app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    with TestClient(app) as client:
        cases = (
            ("explorer.syntrends.com", "/explorer/"),
            ("explorer.testnet.syntrends.com", "/explorer/"),
            ("owners.testnet.syntrends.com", "/owners/"),
            ("status.testnet.syntrends.com", "/status/"),
            ("api.testnet.syntrends.com", "/.well-known/syntrends"),
        )
        for host, dest in cases:
            r = client.get("/", headers={"host": host}, follow_redirects=False)
            assert r.status_code == 307, host
            assert r.headers["location"] == dest, host
        home = client.get("/", headers={"host": "testnet.syntrends.com"}, follow_redirects=False)
        assert home.status_code == 200
