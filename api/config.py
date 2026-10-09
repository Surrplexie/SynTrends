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


def _truthy_env(name: str, default: str = "") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


# Real-dollar (or pretends-to-be) deployments. Faucet and /agent/deposit mint
# are impossible here even if FAUCET_ENABLED / ALLOW_SANDBOX_DEPOSIT are set.
LIVE_MONEY_ENVS = frozenset({"production", "mainnet", "live"})
DEMO_ENVS = frozenset({"development", "demo", "test"})


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
    # POST /agent/deposit mints balance. Default off except local demo envs.
    allow_sandbox_deposit: bool = False
    # Licensed partner inbound funding. Secret empty = route 404. Non-live
    # networks also need PARTNER_FUNDING_ENABLED=1 (do not set on public testnet).
    partner_funding_secret: str | None = None
    partner_funding_enabled: bool = False
    partner_max_credit: float = 100000.0

    @property
    def is_production(self) -> bool:
        return self.env in LIVE_MONEY_ENVS

    @property
    def is_testnet(self) -> bool:
        return self.env == "testnet"

    @property
    def is_live_money(self) -> bool:
        """Env names that must never mint simulated fiat."""
        return self.env in LIVE_MONEY_ENVS

    @property
    def is_demo_env(self) -> bool:
        """True for local/dev/demo — where shortcuts like the KYC admin
        approve button and open `/demo/keys` bootstrap are safe to expose."""
        return self.env in DEMO_ENVS

    @property
    def faucet_allowed(self) -> bool:
        """Simulated faucet. Never on live-money envs, even if FAUCET_ENABLED=1."""
        if self.is_live_money:
            return False
        return self.faucet_enabled

    @property
    def sandbox_deposit_allowed(self) -> bool:
        """POST /agent/deposit mints agent fiat. Local demo only.

        Public testnet uses the faucet. Live money will use owner funding
        (partner webhook) — not this route.
        """
        if self.is_live_money:
            return False
        if self.is_demo_env:
            return True
        return self.allow_sandbox_deposit

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

    @property
    def partner_funding_allowed(self) -> bool:
        """HMAC partner credit. Live: secret is enough. Elsewhere: explicit flag."""
        if not self.partner_funding_secret:
            return False
        if self.is_live_money:
            return True
        return self.partner_funding_enabled

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get("SYNTRENDS_ENV", "development").strip().lower()
        database_url = os.environ.get("DATABASE_URL", "").strip() or None
        cors_raw = os.environ.get("CORS_ORIGINS", "").strip()
        cors_origins = _split_csv(cors_raw) or (
            ["*"] if env not in ("production", "testnet", "mainnet", "live") else []
        )

        network_name = os.environ.get("NETWORK_NAME", "").strip()
        if not network_name:
            network_name = {
                "testnet": "syntrends-testnet-1",
                "production": "syntrends-mainnet-1",
                "mainnet": "syntrends-mainnet-1",
                "live": "syntrends-mainnet-1",
            }.get(env, "syntrends-local")

        if env in LIVE_MONEY_ENVS:
            faucet_enabled = False
        else:
            faucet_enabled = _truthy_env("FAUCET_ENABLED", "1" if env == "testnet" else "0")

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
            allow_demo_kyc_approve=_truthy_env("ALLOW_DEMO_KYC_APPROVE"),
            require_real_kyc_on_testnet=_truthy_env("REQUIRE_REAL_KYC_ON_TESTNET", "1"),
            allow_sandbox_deposit=_truthy_env("ALLOW_SANDBOX_DEPOSIT"),
            partner_funding_secret=os.environ.get("PARTNER_FUNDING_SECRET", "").strip() or None,
            partner_funding_enabled=_truthy_env("PARTNER_FUNDING_ENABLED"),
            partner_max_credit=_float_env("PARTNER_MAX_CREDIT", 100000.0),
        )
