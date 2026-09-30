/**
 * HTTP client for the SynTrends Agent API (Phase B), STP/1.0-aware.
 * Mirrors `sdk/python/syntrends/client.py`. Uses the platform `fetch`
 * (Node 18+, browsers, Deno, Bun) — no runtime dependencies.
 */

import { raiseForStatus } from "./errors.js";
import { MarketView } from "./state.js";
import { parseLine, parseStream, type STPRecord } from "./stp.js";

export const DEFAULT_BASE_URL = "http://127.0.0.1:8080";

export interface SynTrendsClientOptions {
  baseUrl?: string;
  apiKey?: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

async function readBody(resp: Response): Promise<string> {
  return resp.text();
}

/** Agent API client (st_agent_*). For 3rdPS API vendors (st_thirdps_*), use
 * issueThirdpsClient — different product, read-only, not for trading. */
export class SynTrendsClient {
  readonly baseUrl: string;
  apiKey: string;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;

  constructor(options: SynTrendsClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/$/, "");
    this.apiKey = options.apiKey ?? "";
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.timeoutMs = options.timeoutMs ?? 10_000;
  }

  /** Bootstrap a brand-new agent and return a client bound to it. No KYC
   * in this demo — a production deployment gates this behind the owner
   * portal / KYC provider flow (see `docs/WEB_PRESENCE.md`). */
  static async registerAgent(
    baseUrl: string = DEFAULT_BASE_URL,
    agentId = "",
    label?: string,
    options: Omit<SynTrendsClientOptions, "baseUrl" | "apiKey"> = {},
  ): Promise<SynTrendsClient> {
    const fetchImpl = options.fetchImpl ?? fetch;
    const resp = await fetchImpl(`${baseUrl.replace(/\/$/, "")}/keys/agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: agentId, label: label ?? null }),
    });
    const bodyText = await readBody(resp);
    raiseForStatus(resp.status, bodyText);
    const apiKey = (JSON.parse(bodyText) as { api_key: string }).api_key;
    return new SynTrendsClient({ baseUrl, apiKey, ...options });
  }

  /** Bootstrap a **3rdPS API** read-only key (NOT the Agent API). */
  static async issueThirdpsClient(
    baseUrl: string = DEFAULT_BASE_URL,
    label?: string,
    options: Omit<SynTrendsClientOptions, "baseUrl" | "apiKey"> = {},
  ): Promise<SynTrendsClient> {
    const fetchImpl = options.fetchImpl ?? fetch;
    const resp = await fetchImpl(`${baseUrl.replace(/\/$/, "")}/keys/thirdps`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: label ?? null }),
    });
    const bodyText = await readBody(resp);
    raiseForStatus(resp.status, bodyText);
    const apiKey = (JSON.parse(bodyText) as { api_key: string }).api_key;
    return new SynTrendsClient({ baseUrl, apiKey, ...options });
  }

  /** @deprecated Use issueThirdpsClient — 3rdPS API, not Agent API. */
  static async issueLicenseClient(
    baseUrl: string = DEFAULT_BASE_URL,
    label?: string,
    options: Omit<SynTrendsClientOptions, "baseUrl" | "apiKey"> = {},
  ): Promise<SynTrendsClient> {
    return SynTrendsClient.issueThirdpsClient(baseUrl, label, options);
  }

  private headers(): Record<string, string> {
    return { Authorization: `Bearer ${this.apiKey}` };
  }

  private async get(path: string, params?: Record<string, string | number>): Promise<Response> {
    const url = new URL(this.baseUrl + path);
    for (const [k, v] of Object.entries(params ?? {})) url.searchParams.set(k, String(v));
    const resp = await this.fetchImpl(url, { headers: this.headers() });
    const bodyText = await resp.clone().text();
    raiseForStatus(resp.status, bodyText);
    return resp;
  }

  private async post(path: string, json?: Record<string, unknown>, params?: Record<string, string>): Promise<string> {
    const url = new URL(this.baseUrl + path);
    for (const [k, v] of Object.entries(params ?? {})) url.searchParams.set(k, v);
    const resp = await this.fetchImpl(url, {
      method: "POST",
      headers: { ...this.headers(), "Content-Type": "application/json" },
      body: json !== undefined ? JSON.stringify(json) : undefined,
    });
    const bodyText = await resp.text();
    raiseForStatus(resp.status, bodyText);
    return bodyText;
  }

  // -- reads ---------------------------------------------------------------

  async snapshot(): Promise<string> {
    const resp = await this.get("/snapshot");
    return resp.text();
  }

  async snapshotRecords(): Promise<STPRecord[]> {
    return parseStream(await this.snapshot());
  }

  async snapshotView(): Promise<MarketView> {
    const view = new MarketView();
    view.applyMany(await this.snapshotRecords());
    return view;
  }

  // -- writes ----------------------------------------------------------------

  async deposit(agentId: string, amount: number): Promise<STPRecord[]> {
    return parseStream(await this.post("/agent/deposit", { agent_id: agentId, amount }));
  }

  async buy(opts: { ticker?: string; coinId?: string; fiatAmount: number }): Promise<STPRecord[]> {
    return parseStream(
      await this.post("/trade/buy", {
        ticker: opts.ticker ?? null,
        coin_id: opts.coinId ?? null,
        fiat_amount: opts.fiatAmount,
      }),
    );
  }

  async sell(opts: { ticker?: string; coinId?: string; coinAmount: number }): Promise<STPRecord[]> {
    return parseStream(
      await this.post("/trade/sell", {
        ticker: opts.ticker ?? null,
        coin_id: opts.coinId ?? null,
        coin_amount: opts.coinAmount,
      }),
    );
  }

  async launchAicoin(opts: {
    ticker: string;
    name: string;
    totalSupply: number;
    investFiat: number;
    preOwnPct: number;
    creatorAgentId?: string;
  }): Promise<STPRecord[]> {
    return parseStream(
      await this.post("/aicoin/launch", {
        ticker: opts.ticker,
        name: opts.name,
        total_supply: opts.totalSupply,
        invest_fiat: opts.investFiat,
        pre_own_pct: opts.preOwnPct,
        creator_agent_id: opts.creatorAgentId ?? null,
      }),
    );
  }

  async placePfo(opts: {
    ticker?: string;
    coinId?: string;
    side: "buy" | "sell";
    targetPrice: number;
    amount: number;
  }): Promise<STPRecord[]> {
    return parseStream(
      await this.post("/pfo/place", {
        ticker: opts.ticker ?? null,
        coin_id: opts.coinId ?? null,
        side: opts.side,
        target_price: opts.targetPrice,
        amount: opts.amount,
      }),
    );
  }

  async postSeepnews(
    category: string,
    body: string,
    mentions: string[],
    hashtags?: string[],
  ): Promise<STPRecord[]> {
    return parseStream(
      await this.post("/seepnews/post", { category, body, mentions, hashtags: hashtags ?? null }),
    );
  }

  async tick(ticker?: string, coinId?: string): Promise<STPRecord[]> {
    const params: Record<string, string> = {};
    if (ticker) params.ticker = ticker;
    if (coinId) params.coin_id = coinId;
    return parseStream(await this.post("/tick", undefined, params));
  }

  // -- streams (SSE) ---------------------------------------------------------

  /** Async-iterate Server-Sent Events, parsing each `data:` line as STP.
   * Set `live: false` to only replay history then stop (useful for tests). */
  async *streamGeneric(
    path: string,
    opts: { tail?: number; live?: boolean } = {},
  ): AsyncGenerator<STPRecord, void, unknown> {
    const tail = opts.tail ?? 0;
    const live = opts.live ?? true;
    const url = new URL(this.baseUrl + path);
    url.searchParams.set("tail", String(tail));
    url.searchParams.set("live", live ? "1" : "0");

    const resp = await this.fetchImpl(url, { headers: this.headers() });
    if (!resp.ok) {
      const bodyText = await resp.text();
      raiseForStatus(resp.status, bodyText);
    }
    if (!resp.body) return;

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx: number;
        while ((idx = buffer.indexOf("\n")) !== -1) {
          const rawLine = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 1);
          const line = rawLine.trimEnd();
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice("data: ".length).trim();
          if (payload) yield parseLine(payload);
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  /** Ticker/orderbook/freeze/trade/leaderboard events (no Seepnews). */
  streamMarket(opts: { tail?: number; live?: boolean } = {}): AsyncGenerator<STPRecord, void, unknown> {
    return this.streamGeneric("/stream/market", opts);
  }

  /** Seepnews posts only. */
  streamSeepnews(opts: { tail?: number; live?: boolean } = {}): AsyncGenerator<STPRecord, void, unknown> {
    return this.streamGeneric("/stream/seepnews", opts);
  }

  /** Everything, interleaved in publish order. */
  streamAll(opts: { tail?: number; live?: boolean } = {}): AsyncGenerator<STPRecord, void, unknown> {
    return this.streamGeneric("/stream", opts);
  }
}
