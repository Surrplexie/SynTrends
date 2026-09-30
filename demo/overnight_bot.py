"""Overnight agent bot — polls a live testnet/API and trades slowly for hours.

Start the testnet in one terminal (omit ``--fresh`` to keep the same chain)::

    python scripts/ship_testnet.py --no-e2e --port 8099

Single agent::

    $env:SYNTRENDS_URL = "http://127.0.0.1:8099"
    $env:SYNTRENDS_API_KEY = "st_agent_..."
    $env:SYNTRENDS_AGENT_ID = "xyz"
    python -m demo.overnight_bot --hours 4

Multiple agents on the **same** chain — register each in the owner portal, then::

    python -m demo.run_overnight_bots --config demo/overnight_agents.example.json --hours 4

Uses poll mode (default) instead of SSE so disconnects do not kill the run.
Rate limits and faucet cooldowns are handled with backoff; transient HTTP
errors are retried until the duration elapses.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from chain.stp import ParsedError
from demo.agents._bootstrap import accept_platform_terms
from syntrends.client import DEFAULT_BASE_URL, SynTrendsClient
from syntrends.errors import AuthenticationError, RateLimitedError, SynTrendsAPIError
from syntrends.state import MarketView, TickerSnapshot

DEFAULT_TICKER = "GEM"
DEFAULT_BUY_AMOUNT = 25.0
DEFAULT_MIN_FIAT = 50.0
DEFAULT_INTERVAL_S = 90.0
DEFAULT_JITTER_S = 15.0
DEFAULT_SELL_AFTER_BUYS = 8
DEFAULT_SELL_FRACTION = 0.25
MIN_SELL_COINS = 0.0001
MAX_BACKOFF_S = 300.0
STATUS_LOG_EVERY_S = 600.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@dataclass
class RunStats:
    started_at: float = field(default_factory=time.monotonic)
    cycles: int = 0
    buys_ok: int = 0
    sells_ok: int = 0
    skips_frozen: int = 0
    skips_balance: int = 0
    errors: int = 0
    rate_limits: int = 0
    reconnects: int = 0

    def summary(self) -> str:
        elapsed_h = (time.monotonic() - self.started_at) / 3600
        return (
            f"cycles={self.cycles} buys={self.buys_ok} sells={self.sells_ok} "
            f"errors={self.errors} rate_limits={self.rate_limits} "
            f"reconnects={self.reconnects} elapsed={elapsed_h:.2f}h"
        )


class OvernightBot:
    """Conservative poll loop: snapshot → optional small trade → sleep."""

    def __init__(
        self,
        client: SynTrendsClient,
        agent_id: str,
        *,
        ticker: str = DEFAULT_TICKER,
        buy_amount: float = DEFAULT_BUY_AMOUNT,
        min_fiat: float = DEFAULT_MIN_FIAT,
        interval_s: float = DEFAULT_INTERVAL_S,
        jitter_s: float = DEFAULT_JITTER_S,
        sell_after_buys: int = DEFAULT_SELL_AFTER_BUYS,
        sell_fraction: float = DEFAULT_SELL_FRACTION,
    ) -> None:
        self.client = client
        self.agent_id = agent_id
        self.ticker = ticker
        self.buy_amount = buy_amount
        self.min_fiat = min_fiat
        self.interval_s = interval_s
        self.jitter_s = jitter_s
        self.sell_after_buys = max(1, sell_after_buys)
        self.sell_fraction = sell_fraction
        self.view = MarketView()
        self.stats = RunStats()
        self._buys_since_sell = 0
        self._last_status_log = 0.0
        self._backoff_s = 0.0

    def log(self, msg: str) -> None:
        print(f"[{_utc_now()}] [{self.agent_id}] {msg}", flush=True)

    def _health_check(self) -> dict:
        resp = self.client._client.get("/status")
        resp.raise_for_status()
        return resp.json()

    def _try_faucet(self) -> None:
        try:
            resp = self.client._client.post("/testnet/faucet", headers=self.client._headers())
            if resp.status_code == 200:
                self.view.apply_many(parse_stream_safe(resp.text))
                self.log("faucet credited simulated fiat")
                return
            detail = resp.text
            try:
                detail = resp.json().get("detail", detail)
            except Exception:
                pass
            if resp.status_code == 429 or "cooldown" in detail.lower():
                self.log(f"faucet skipped (cooldown): {detail}")
            else:
                self.log(f"faucet skipped: HTTP {resp.status_code} {detail}")
        except httpx.HTTPError as exc:
            self.log(f"faucet skipped (network): {exc}")

    def bootstrap(self) -> None:
        status = self._health_check()
        self.log(
            f"connected — blocks={status.get('blocks')} agents={status.get('agents')} "
            f"faucet={status.get('faucet_enabled')}"
        )
        try:
            accept_platform_terms(self.client)
            self.log("platform terms accepted")
        except SynTrendsAPIError as exc:
            self.log(f"terms already accepted or skipped: {exc.detail}")

        self._try_faucet()
        try:
            self.view.apply_many(self.client.snapshot_records())
        except AuthenticationError as exc:
            raise SystemExit(
                f"\nInvalid API key for agent '{self.agent_id}'.\n"
                f"Get a real key from https://testnet.syntrends.com/owners/ "
                f"(Connect agent → copy key; agent_id must match exactly).\n"
                f"Detail: {exc.detail}\n"
            ) from exc
        t = self.view.tickers.get(self.ticker)
        if t:
            self.log(f"bootstrap ${self.ticker} @ {t.price:.6f} freeze={t.freeze}")
        self._log_balances("bootstrap")

    def _log_balances(self, prefix: str) -> None:
        fiat = self.view.fiat_balance(self.agent_id)
        coin = self.view.coin_balance(self.agent_id, self.ticker)
        self.log(f"{prefix} balances fiat={fiat:.2f} {self.ticker}={coin:.6f}")

    def _sleep_interval(self) -> None:
        delay = self.interval_s + random.uniform(-self.jitter_s, self.jitter_s)
        if self._backoff_s > 0:
            delay = max(delay, self._backoff_s)
        time.sleep(max(5.0, delay))
        self._backoff_s = max(0.0, self._backoff_s * 0.5)

    def _handle_error(self, exc: Exception) -> None:
        self.stats.errors += 1
        if isinstance(exc, RateLimitedError):
            self.stats.rate_limits += 1
            self._backoff_s = min(MAX_BACKOFF_S, max(60.0, self._backoff_s * 2 or 60.0))
            self.log(f"rate limited — backing off {self._backoff_s:.0f}s")
        elif isinstance(exc, httpx.HTTPError):
            self.stats.reconnects += 1
            self._backoff_s = min(MAX_BACKOFF_S, max(30.0, self._backoff_s * 2 or 30.0))
            self.log(f"network error — retry in {self._backoff_s:.0f}s: {exc}")
        else:
            self._backoff_s = min(MAX_BACKOFF_S, max(15.0, self._backoff_s * 2 or 15.0))
            self.log(f"error — retry in {self._backoff_s:.0f}s: {exc}")

    def _maybe_log_status(self) -> None:
        now = time.monotonic()
        if now - self._last_status_log < STATUS_LOG_EVERY_S:
            return
        self._last_status_log = now
        try:
            status = self._health_check()
            blocks = status.get("blocks", "?")
        except Exception:
            blocks = "?"
        fiat = self.view.fiat_balance(self.agent_id)
        coin = self.view.coin_balance(self.agent_id, self.ticker)
        self.log(
            f"heartbeat blocks={blocks} fiat={fiat:.2f} {self.ticker}={coin:.6f} | {self.stats.summary()}"
        )

    def _refresh_view(self) -> TickerSnapshot | None:
        self.view.apply_many(self.client.snapshot_records())
        return self.view.tickers.get(self.ticker)

    def _apply_trade_result(self, result: list) -> list[ParsedError]:
        self.view.apply_many(result)
        return [r for r in result if isinstance(r, ParsedError)]

    def _try_sell(self, ticker: TickerSnapshot, coin: float, reason: str) -> bool:
        sell_amount = min(coin * self.sell_fraction, coin)
        if sell_amount < MIN_SELL_COINS:
            return False
        result = self.client.sell(ticker=self.ticker, coin_amount=sell_amount)
        errors = self._apply_trade_result(result)
        if errors:
            self.log(f"sell rejected ({reason}): {errors[0].msg}")
            return False
        self.stats.sells_ok += 1
        self._buys_since_sell = 0
        self.log(f"sold {sell_amount:.6f} {self.ticker} @ {ticker.price:.6f} ({reason})")
        return True

    def _maybe_trade(self, ticker: TickerSnapshot) -> None:
        if ticker.freeze == "frozen":
            self.stats.skips_frozen += 1
            return

        fiat = self.view.fiat_balance(self.agent_id)
        coin = self.view.coin_balance(self.agent_id, self.ticker)

        if (
            self._buys_since_sell >= self.sell_after_buys
            and coin >= MIN_SELL_COINS
        ):
            if self._try_sell(ticker, coin, f"after {self.sell_after_buys} buys"):
                return

        if fiat < self.min_fiat:
            self.stats.skips_balance += 1
            self._try_faucet()
            return

        if fiat >= self.buy_amount:
            result = self.client.buy(ticker=self.ticker, fiat_amount=self.buy_amount)
            errors = self._apply_trade_result(result)
            if errors:
                self.log(f"buy rejected: {errors[0].msg}")
            else:
                self.stats.buys_ok += 1
                self._buys_since_sell += 1
                self.log(f"bought ${self.buy_amount:.2f} {self.ticker} @ {ticker.price:.6f}")

    def run_until(self, deadline: float) -> None:
        self.bootstrap()
        while time.monotonic() < deadline:
            self.stats.cycles += 1
            try:
                ticker = self._refresh_view()
                if ticker:
                    self._maybe_trade(ticker)
                self._maybe_log_status()
            except (SynTrendsAPIError, httpx.HTTPError) as exc:
                self._handle_error(exc)
            except Exception as exc:
                self._handle_error(exc)
            self._sleep_interval()
        self.log(f"finished — {self.stats.summary()}")


def parse_stream_safe(text: str) -> list:
    from chain.stp import parse_stream

    return parse_stream(text)


def _env_or_die(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"Missing required env var {name}", file=sys.stderr)
        sys.exit(2)
    return value


def build_bot(
    *,
    base_url: str,
    api_key: str,
    agent_id: str,
    ticker: str = DEFAULT_TICKER,
    buy_amount: float = DEFAULT_BUY_AMOUNT,
    interval_s: float = DEFAULT_INTERVAL_S,
    sell_after_buys: int = DEFAULT_SELL_AFTER_BUYS,
    sell_fraction: float = DEFAULT_SELL_FRACTION,
    timeout: float = 30.0,
) -> tuple[OvernightBot, SynTrendsClient]:
    client = SynTrendsClient(base_url=base_url, api_key=api_key, timeout=timeout)
    bot = OvernightBot(
        client,
        agent_id,
        ticker=ticker,
        buy_amount=buy_amount,
        interval_s=interval_s,
        sell_after_buys=sell_after_buys,
        sell_fraction=sell_fraction,
    )
    return bot, client


def main() -> None:
    parser = argparse.ArgumentParser(description="SynTrends overnight poll bot")
    parser.add_argument("--base-url", default=os.environ.get("SYNTRENDS_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("SYNTRENDS_API_KEY", ""))
    parser.add_argument("--agent-id", default=os.environ.get("SYNTRENDS_AGENT_ID", ""))
    parser.add_argument("--hours", type=float, default=float(os.environ.get("SYNTRENDS_HOURS", "4")))
    parser.add_argument("--ticker", default=os.environ.get("SYNTRENDS_TICKER", DEFAULT_TICKER))
    parser.add_argument("--buy-amount", type=float, default=float(os.environ.get("SYNTRENDS_BUY_AMOUNT", DEFAULT_BUY_AMOUNT)))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("SYNTRENDS_INTERVAL", DEFAULT_INTERVAL_S)))
    parser.add_argument(
        "--sell-after-buys",
        type=int,
        default=int(os.environ.get("SYNTRENDS_SELL_AFTER_BUYS", DEFAULT_SELL_AFTER_BUYS)),
    )
    parser.add_argument(
        "--sell-fraction",
        type=float,
        default=float(os.environ.get("SYNTRENDS_SELL_FRACTION", DEFAULT_SELL_FRACTION)),
    )
    args = parser.parse_args()

    api_key = args.api_key.strip() or _env_or_die("SYNTRENDS_API_KEY")
    agent_id = args.agent_id.strip() or _env_or_die("SYNTRENDS_AGENT_ID")
    if args.hours <= 0:
        print("--hours must be positive", file=sys.stderr)
        sys.exit(2)

    deadline = time.monotonic() + args.hours * 3600
    bot, client = build_bot(
        base_url=args.base_url,
        api_key=api_key,
        agent_id=agent_id,
        ticker=args.ticker,
        buy_amount=args.buy_amount,
        interval_s=args.interval,
        sell_after_buys=args.sell_after_buys,
        sell_fraction=args.sell_fraction,
    )
    print(
        f"[{_utc_now()}] overnight bot starting — url={args.base_url} agent={agent_id} "
        f"hours={args.hours} ticker={args.ticker} interval~{args.interval}s "
        f"sell_after={args.sell_after_buys} sell_frac={args.sell_fraction}",
        flush=True,
    )
    try:
        bot.run_until(deadline)
    except KeyboardInterrupt:
        bot.log(f"interrupted — {bot.stats.summary()}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
