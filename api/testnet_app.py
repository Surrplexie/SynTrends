"""Phase G public testnet stack — KYC-gated keys, faucet, no /demo/keys."""

from .app_factory import create_app
from .config import Settings

settings = Settings.from_env()
app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
