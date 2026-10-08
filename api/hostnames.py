"""Public hostnames. Explorer is the official chain view (not marketing .com)."""

from __future__ import annotations

# Same Fly app as testnet until mainnet exists. DNS + certs are per hostname.
EXPLORER_HOSTS = frozenset({
    "explorer.syntrends.com",
    "explorer.testnet.syntrends.com",
})

EXPLORER_CANONICAL = "https://explorer.syntrends.com"
EXPLORER_TESTNET_PATH = "https://testnet.syntrends.com/explorer/"


def is_explorer_host(host: str | None) -> bool:
    if not host:
        return False
    name = host.split(":", 1)[0].strip().lower()
    if name.startswith("www."):
        name = name[4:]
    return name in EXPLORER_HOSTS
