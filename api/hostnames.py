"""Public hostnames. Same Fly app as testnet until mainnet exists.

DNS + certs are per hostname. Path routes still work on testnet.syntrends.com.
These Host checks only send `/` to the right mount (Caddy split remains the
hard edge for Docker).
"""

from __future__ import annotations

EXPLORER_HOSTS = frozenset({
    "explorer.syntrends.com",
    "explorer.testnet.syntrends.com",
})

OWNERS_HOSTS = frozenset({
    "owners.syntrends.com",
    "owners.testnet.syntrends.com",
})

API_HOSTS = frozenset({
    "api.syntrends.com",
    "api.testnet.syntrends.com",
})

STATUS_HOSTS = frozenset({
    "status.syntrends.com",
    "status.testnet.syntrends.com",
})

EXPLORER_CANONICAL = "https://explorer.syntrends.com"
EXPLORER_TESTNET_PATH = "https://testnet.syntrends.com/explorer/"
OWNERS_CANONICAL = "https://testnet.syntrends.com/owners/"
API_CANONICAL = "https://testnet.syntrends.com"


def normalize_host(host: str | None) -> str:
    if not host:
        return ""
    name = host.split(":", 1)[0].strip().lower()
    if name.startswith("www."):
        name = name[4:]
    return name


def is_explorer_host(host: str | None) -> bool:
    return normalize_host(host) in EXPLORER_HOSTS


def is_owners_host(host: str | None) -> bool:
    return normalize_host(host) in OWNERS_HOSTS


def is_api_host(host: str | None) -> bool:
    return normalize_host(host) in API_HOSTS


def is_status_host(host: str | None) -> bool:
    return normalize_host(host) in STATUS_HOSTS


def root_redirect_for_host(host: str | None) -> str | None:
    """Where `/` should 307 on a split hostname. None = leave marketing/testnet home."""
    if is_explorer_host(host):
        return "/explorer/"
    if is_owners_host(host):
        return "/owners/"
    if is_status_host(host):
        return "/status/"
    if is_api_host(host):
        return "/.well-known/syntrends"
    return None
