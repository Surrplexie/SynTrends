"""Environment-driven settings for staging/production/testnet deployments.

Demo scripts (`demo/run_web.py`, `demo/run_api.py`) call `create_app()` with
explicit keyword arguments and never touch this module. Real deployments
(Docker, Fly, etc.) set environment variables instead; `app_factory.py`
falls back to `Settings.from_env()` when no override is passed in.

Phase G adds ``SYNTRENDS_ENV=testnet`` for the public testnet: simulated
fiat faucet, stricter rate limits, scrypt owner passwords, and no
/demo/keys bootstrap.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return float(raw)


@dataclass(frozen=True)
class Settings:
    env: str = "development"
    database_url: str | None = None
    cors_origins: list[str] = field(default_factory=lambda: ["*"])

    kyc_provider: str = "demo"
    persona_api_key: str | None = None
    persona_webhook_secret: str | None = None
    persona_template_id: str | None = None
    persona_environment: str = "sandbox"

    # Phase G — testnet / rate limits
    network_name: str = "syntrends-local"
    protocol_version: str = "STP/1.0"
    faucet_enabled: bool = True
    faucet_amount: float = 5000.0
    faucet_cooldown_seconds: float = 3600.0
    thirdps_rate_limit_per_minute: int = 120
    agent_write_rate_limit_per_minute: int = 60
    owner_session_ttl_seconds: float = 86400.0 * 7
    thirdps_key_ttl_seconds: float = 365 * 24 * 3600.0
    thirdps_usd_per_ct: float = 0.001

    @property
    def thirdps_usd_per_weight(self) -> float:
        """Alias — invoices are Curation Tokens, not a separate weight unit."""
        return self.thirdps_usd_per_ct
    # Local ship/e2e only — never set on public Fly or staging without Persona.
    allow_demo_kyc_approve: bool = False
    # Public beta: require Persona credentials when KYC_PROVIDER=persona on testnet.
    require_real_kyc_on_testnet: bool = True

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_testnet(self) -> bool:
        return self.env == "testnet"

    @property
    def is_demo_env(self) -> bool:
        """True for local/dev/demo — where shortcuts like the KYC admin
        approve button and open `/demo/keys` bootstrap are safe to expose."""
        return self.env in ("development", "demo", "test")

    @property
    def demo_kyc_approve_allowed(self) -> bool:
        """Whether the unauthenticated demo KYC admin shortcut may run.

        Allowed on local ``development``/``demo``/``test`` always.
        Allowed on ``testnet`` only when ``ALLOW_DEMO_KYC_APPROVE=1`` (local ship).
        Never allowed in ``production``.
        """
        if self.is_production:
            return False
        if self.is_demo_env:
            return True
        return self.allow_demo_kyc_approve

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get("SYNTRENDS_ENV", "development").strip().lower()
        database_url = os.environ.get("DATABASE_URL", "").strip() or None
        cors_raw = os.environ.get("CORS_ORIGINS", "").strip()
        cors_origins = _split_csv(cors_raw) or (["*"] if env not in ("production", "testnet") else [])

        network_name = os.environ.get("NETWORK_NAME", "").strip()
        if not network_name:
            network_name = {
                "testnet": "syntrends-testnet-1",
                "production": "syntrends-mainnet-1",
            }.get(env, "syntrends-local")

        faucet_enabled = os.environ.get("FAUCET_ENABLED", "1" if env == "testnet" else "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        return cls(
            env=env,
            database_url=database_url,
            cors_origins=cors_origins,
            kyc_provider=os.environ.get("KYC_PROVIDER", "demo").strip().lower(),
            persona_api_key=os.environ.get("PERSONA_API_KEY", "").strip() or None,
            persona_webhook_secret=os.environ.get("PERSONA_WEBHOOK_SECRET", "").strip() or None,
            persona_template_id=os.environ.get("PERSONA_TEMPLATE_ID", "").strip() or None,
            persona_environment=os.environ.get("PERSONA_ENVIRONMENT", "sandbox").strip().lower(),
            network_name=network_name,
            protocol_version=os.environ.get("PROTOCOL_VERSION", "STP/1.0").strip(),
            faucet_enabled=faucet_enabled,
            faucet_amount=_float_env("FAUCET_AMOUNT", 5000.0),
            faucet_cooldown_seconds=_float_env("FAUCET_COOLDOWN_SECONDS", 3600.0),
            thirdps_rate_limit_per_minute=_int_env(
                "THIRDPS_RATE_LIMIT_PER_MINUTE",
                _int_env("LICENSE_RATE_LIMIT_PER_MINUTE", 120),
            ),
            agent_write_rate_limit_per_minute=_int_env("AGENT_WRITE_RATE_LIMIT_PER_MINUTE", 60),
            owner_session_ttl_seconds=_float_env("OWNER_SESSION_TTL_SECONDS", 86400.0 * 7),
            thirdps_key_ttl_seconds=_float_env("THIRDPS_KEY_TTL_SECONDS", 365 * 24 * 3600.0),
            thirdps_usd_per_ct=_float_env(
                "THIRDPS_USD_PER_CT",
                _float_env("THIRDPS_USD_PER_WEIGHT", 0.001),
            ),
            allow_demo_kyc_approve=os.environ.get("ALLOW_DEMO_KYC_APPROVE", "").strip().lower()
            in ("1", "true", "yes"),
            require_real_kyc_on_testnet=os.environ.get("REQUIRE_REAL_KYC_ON_TESTNET", "1")
            .strip()
            .lower()
            in ("1", "true", "yes"),
        )
