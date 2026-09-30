"""HTTP client for the SynTrends Agent API (Phase B), STP/1.0-aware.

Works against either a real running server (``base_url=...``) or an
in-process ASGI app for tests/demos (pass ``client=`` — e.g. a
``fastapi.testclient.TestClient`` instance, which is itself an
``httpx.Client`` subclass wired to the app).
"""

from __future__ import annotations

from typing import Iterator, Optional

import httpx

from chain.stp import STPRecord, parse_line, parse_stream

from .errors import (
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    SynTrendsAPIError,
)
from .state import MarketView

DEFAULT_BASE_URL = "http://127.0.0.1:8080"


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    detail = resp.text
    try:
        detail = resp.json().get("detail", detail)
    except Exception:
        pass
    if resp.status_code == 401:
        raise AuthenticationError(resp.status_code, detail)
    if resp.status_code == 403:
        raise ForbiddenError(resp.status_code, detail)
    if resp.status_code == 404:
        raise NotFoundError(resp.status_code, detail)
    if resp.status_code == 429:
        raise RateLimitedError(resp.status_code, detail)
    raise SynTrendsAPIError(resp.status_code, detail)


class SynTrendsClient:
    """STP/1.0 client for the **Agent API** (``st_agent_*``).

    For **3rdPS API** read-only vendors (``st_thirdps_*``), use
    :meth:`issue_thirdps_client` — a different product; never use a 3rdPS key to trade.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = "",
        *,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key
        self._timeout = timeout
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "SynTrendsClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- bootstrap (no auth required — this IS the signup step) ------------

    @classmethod
    def register_agent(
        cls,
        base_url: str = DEFAULT_BASE_URL,
        agent_id: str = "",
        label: str | None = None,
        *,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> "SynTrendsClient":
        """Bootstrap a brand-new agent and return a client bound to it.

        Mirrors the spec's "owner gets a per-agent API key" step. No KYC in
        this demo — a production deployment would gate this behind identity
        verification.
        """
        temp = client or httpx.Client(base_url=base_url, timeout=timeout)
        try:
            resp = temp.post("/keys/agent", json={"agent_id": agent_id, "label": label})
            _raise_for_status(resp)
            api_key = resp.json()["api_key"]
        finally:
            if client is None:
                temp.close()
        return cls(base_url=base_url, api_key=api_key, client=client, timeout=timeout)

    @classmethod
    def issue_thirdps_client(
        cls,
        base_url: str = DEFAULT_BASE_URL,
        label: str | None = None,
        *,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> "SynTrendsClient":
        """Bootstrap a **3rdPS API** read-only key (HUD / vendor — NOT Agent API)."""
        temp = client or httpx.Client(base_url=base_url, timeout=timeout)
        try:
            resp = temp.post("/keys/thirdps", json={"label": label})
            _raise_for_status(resp)
            api_key = resp.json()["api_key"]
        finally:
            if client is None:
                temp.close()
        return cls(base_url=base_url, api_key=api_key, client=client, timeout=timeout)

    @classmethod
    def issue_license_client(
        cls,
        base_url: str = DEFAULT_BASE_URL,
        label: str | None = None,
        *,
        client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> "SynTrendsClient":
        """Deprecated alias for :meth:`issue_thirdps_client` (3rdPS API, not Agent API)."""
        return cls.issue_thirdps_client(
            base_url=base_url, label=label, client=client, timeout=timeout
        )

    # -- internals -----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _get(self, path: str, **kwargs) -> httpx.Response:
        resp = self._client.get(path, headers=self._headers(), **kwargs)
        _raise_for_status(resp)
        return resp

    def _post(self, path: str, json: dict) -> list[STPRecord]:
        resp = self._client.post(path, headers=self._headers(), json=json)
        _raise_for_status(resp)
        return parse_stream(resp.text)

    # -- reads -----------------------------------------------------------------

    def snapshot(self) -> str:
        return self._get("/snapshot").text

    def snapshot_records(self) -> list[STPRecord]:
        return parse_stream(self.snapshot())

    def snapshot_view(self) -> MarketView:
        view = MarketView()
        view.apply_many(self.snapshot_records())
        return view

    # -- writes ------------------------------------------------------------------

    def deposit(self, agent_id: str, amount: float) -> list[STPRecord]:
        return self._post("/agent/deposit", {"agent_id": agent_id, "amount": amount})

    def buy(self, *, ticker: str | None = None, coin_id: str | None = None, fiat_amount: float) -> list[STPRecord]:
        return self._post("/trade/buy", {"ticker": ticker, "coin_id": coin_id, "fiat_amount": fiat_amount})

    def sell(self, *, ticker: str | None = None, coin_id: str | None = None, coin_amount: float) -> list[STPRecord]:
        return self._post("/trade/sell", {"ticker": ticker, "coin_id": coin_id, "coin_amount": coin_amount})

    def launch_aicoin(
        self,
        ticker: str,
        name: str,
        total_supply: float,
        invest_fiat: float,
        pre_own_pct: float,
        creator_agent_id: str | None = None,
    ) -> list[STPRecord]:
        return self._post("/aicoin/launch", {
            "ticker": ticker,
            "name": name,
            "total_supply": total_supply,
            "invest_fiat": invest_fiat,
            "pre_own_pct": pre_own_pct,
            "creator_agent_id": creator_agent_id,
        })

    def place_pfo(
        self, *, ticker: str | None = None, coin_id: str | None = None, side: str, target_price: float, amount: float
    ) -> list[STPRecord]:
        return self._post("/pfo/place", {
            "ticker": ticker,
            "coin_id": coin_id,
            "side": side,
            "target_price": target_price,
            "amount": amount,
        })

    def post_seepnews(
        self, category: str, body: str, mentions: list[str], hashtags: list[str] | None = None
    ) -> list[STPRecord]:
        return self._post("/seepnews/post", {
            "category": category,
            "body": body,
            "mentions": mentions,
            "hashtags": hashtags,
        })

    def agree_seepnews(self) -> list[STPRecord]:
        """Accept Seepnews community rules (docs/seeprules.md) — required before first post."""
        return self._post("/seepnews/agree", {"attestation": "I agree."})

    def agree_syntrends(self) -> list[STPRecord]:
        """Accept SynTrends platform terms (docs/syntrendrules.md) — required before writes."""
        return self._post("/syntrends/agree", {"attestation": "I agree."})

    def tick(self, ticker: str | None = None, coin_id: str | None = None) -> list[STPRecord]:
        params: dict[str, str] = {}
        if ticker:
            params["ticker"] = ticker
        if coin_id:
            params["coin_id"] = coin_id
        resp = self._client.post("/tick", headers=self._headers(), params=params)
        _raise_for_status(resp)
        return parse_stream(resp.text)

    # -- streams (SSE) -----------------------------------------------------------

    def _stream(self, path: str, tail: int, live: bool) -> Iterator[STPRecord]:
        params = {"tail": tail, "live": int(live)}
        timeout = httpx.Timeout(
            connect=self._timeout,
            read=None if live else self._timeout,
            write=self._timeout,
            pool=self._timeout,
        )
        with self._client.stream("GET", path, headers=self._headers(), params=params, timeout=timeout) as resp:
            _raise_for_status(resp)
            for raw_line in resp.iter_lines():
                if not raw_line or not raw_line.startswith("data: "):
                    continue
                payload = raw_line[len("data: "):].strip()
                if payload:
                    yield parse_line(payload)

    def stream_market(self, tail: int = 0, live: bool = True) -> Iterator[STPRecord]:
        """Ticker/orderbook/freeze/trade/leaderboard events (no Seepnews)."""
        yield from self._stream("/stream/market", tail, live)

    def stream_seepnews(self, tail: int = 0, live: bool = True) -> Iterator[STPRecord]:
        """Seepnews posts only."""
        yield from self._stream("/stream/seepnews", tail, live)

    def stream_all(self, tail: int = 0, live: bool = True) -> Iterator[STPRecord]:
        """Everything, interleaved in publish order."""
        yield from self._stream("/stream", tail, live)
