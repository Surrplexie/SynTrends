"""Cash chip — 1:1 ledger credit, not an AICoin.

Agent wallets already store a single fiat number. That number *is* $syntrends:
an internal chip (KIND=chip), not a listed coin, not AMM-tradable.

Live money will still be this unit (partner USD in ↔ chip). Testnet faucet
mints the same chip with no monetary value.
"""

from __future__ import annotations

# STP UNIT= on ST/W fiat lines and ST/A deposits.
CASH_UNIT = "SYNTRENDS"
CASH_DISPLAY = "$syntrends"
CASH_KIND = "chip"

# Cannot be launched or bought as AICoins. USD aliases reserved so nobody
# lists "the dollar" as a freeze/ceil market.
RESERVED_AICOIN_TICKERS = frozenset({
    "SYNTRENDS",
    "SYN",
    "FIAT",
    "CASH",
    "USD",
    "USDC",
    "USDT",
    "EUR",
    "GBP",
})


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().lstrip("$").upper()


def is_reserved_cash_ticker(ticker: str) -> bool:
    return normalize_ticker(ticker) in RESERVED_AICOIN_TICKERS


def reserved_ticker_error(ticker: str) -> str:
    t = normalize_ticker(ticker)
    return (
        f"{t} is the {CASH_DISPLAY} cash chip (1:1 ledger UNIT={CASH_UNIT} "
        f"KIND={CASH_KIND}), not an AICoin; cannot launch or trade it as a ticker"
    )
