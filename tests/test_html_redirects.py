"""Trailing-slash redirects for human HTML mounts."""

from fastapi.testclient import TestClient

from api.app_factory import create_app
from api.config import Settings


def test_bare_html_paths_redirect_to_trailing_slash():
    settings = Settings(env="testnet", network_name="syntrends-testnet-1")
    app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    with TestClient(app) as client:
        for path, dest in (
            ("/owners", "/owners/"),
            ("/explorer", "/explorer/"),
            ("/seepnews", "/seepnews/"),
            ("/vendor", "/vendor/"),
        ):
            r = client.get(path, follow_redirects=False)
            assert r.status_code == 307, path
            assert r.headers["location"] == dest

        assert client.get("/owners/", follow_redirects=True).status_code == 200
        assert client.get("/explorer/", follow_redirects=True).status_code == 200


def test_explorer_hostname_root_redirects_to_explorer():
    settings = Settings(env="testnet", network_name="syntrends-testnet-1")
    app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    with TestClient(app) as client:
        r = client.get("/", headers={"host": "explorer.syntrends.com"}, follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == "/explorer/"
        page = client.get(
            "/explorer/",
            headers={"host": "explorer.syntrends.com"},
            follow_redirects=True,
        )
        assert page.status_code == 200
        assert "chain explorer" in page.text.lower()
