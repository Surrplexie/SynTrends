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
