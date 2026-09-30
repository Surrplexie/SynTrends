"""Phase D unified stack: human .com sites + owner portal + agent API."""

from .app_factory import create_app

app = create_app(require_owner_kyc=True, mount_web=True)
