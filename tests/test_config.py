"""Tests for api/config.py — env-driven Settings used by staging/production."""

from __future__ import annotations

from api.config import Settings


def test_defaults_are_permissive_for_local_dev():
    settings = Settings()
    assert settings.env == "development"
    assert settings.is_production is False
    assert settings.is_demo_env is True
    assert settings.demo_kyc_approve_allowed is True
    assert settings.cors_origins == ["*"]
    assert settings.kyc_provider == "demo"


def test_public_testnet_disallows_demo_kyc_by_default():
    settings = Settings(env="testnet")
    assert settings.is_testnet is True
    assert settings.demo_kyc_approve_allowed is False
    assert settings.require_real_kyc_on_testnet is True


def test_from_env_allow_demo_kyc_approve(monkeypatch):
    monkeypatch.setenv("SYNTRENDS_ENV", "testnet")
    monkeypatch.setenv("ALLOW_DEMO_KYC_APPROVE", "1")
    settings = Settings.from_env()
    assert settings.allow_demo_kyc_approve is True
    assert settings.demo_kyc_approve_allowed is True


def test_from_env_reads_all_fields(monkeypatch):
    monkeypatch.setenv("SYNTRENDS_ENV", "staging")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    monkeypatch.setenv("KYC_PROVIDER", "PERSONA")
    monkeypatch.setenv("PERSONA_API_KEY", "key_1")
    monkeypatch.setenv("PERSONA_WEBHOOK_SECRET", "whsec_1")
    monkeypatch.setenv("PERSONA_TEMPLATE_ID", "itmpl_1")
    monkeypatch.setenv("PERSONA_ENVIRONMENT", "production")

    settings = Settings.from_env()
    assert settings.env == "staging"
    assert settings.database_url == "postgresql://u:p@host/db"
    assert settings.cors_origins == ["https://a.example", "https://b.example"]
    assert settings.kyc_provider == "persona"
    assert settings.persona_api_key == "key_1"
    assert settings.persona_webhook_secret == "whsec_1"
    assert settings.persona_template_id == "itmpl_1"
    assert settings.persona_environment == "production"


def test_from_env_production_defaults_cors_to_empty_allowlist(monkeypatch):
    monkeypatch.setenv("SYNTRENDS_ENV", "production")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings.from_env()
    assert settings.is_production is True
    assert settings.cors_origins == []


def test_from_env_testnet_enables_faucet(monkeypatch):
    monkeypatch.setenv("SYNTRENDS_ENV", "testnet")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings.from_env()
    assert settings.is_testnet is True
    assert settings.faucet_enabled is True
    assert settings.faucet_allowed is True
    assert settings.sandbox_deposit_allowed is False
    assert settings.network_name == "syntrends-testnet-1"
    assert settings.cors_origins == []


def test_live_money_ignores_faucet_and_sandbox_deposit_flags(monkeypatch):
    monkeypatch.setenv("SYNTRENDS_ENV", "production")
    monkeypatch.setenv("FAUCET_ENABLED", "1")
    monkeypatch.setenv("ALLOW_SANDBOX_DEPOSIT", "1")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings.from_env()
    assert settings.is_live_money is True
    assert settings.is_production is True
    assert settings.faucet_enabled is False
    assert settings.faucet_allowed is False
    assert settings.sandbox_deposit_allowed is False


def test_mainnet_alias_is_live_money(monkeypatch):
    monkeypatch.setenv("SYNTRENDS_ENV", "mainnet")
    monkeypatch.setenv("FAUCET_ENABLED", "true")
    settings = Settings.from_env()
    assert settings.is_live_money is True
    assert settings.faucet_allowed is False
    assert settings.sandbox_deposit_allowed is False


def test_constructed_production_settings_cannot_enable_faucet():
    settings = Settings(env="production", faucet_enabled=True, allow_sandbox_deposit=True)
    assert settings.faucet_allowed is False
    assert settings.sandbox_deposit_allowed is False


def test_demo_env_allows_sandbox_deposit():
    settings = Settings()
    assert settings.is_demo_env is True
    assert settings.sandbox_deposit_allowed is True


def test_from_env_missing_database_url_is_none(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings.from_env()
    assert settings.database_url is None
