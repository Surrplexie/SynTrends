/**
 * MarketView: a local read model built by folding STP records — mirrors
 * `sdk/python/syntrends/state.py`. No side-channel JSON, no candles: this
 * is exactly what an agent's "picture of the market" looks like.
 */

import type {
  ParsedAgent,
  ParsedAICoinLaunch,
  ParsedBlock,
  ParsedError,
  ParsedFreezeEvent,
  ParsedLeaderboard,
  ParsedOrderBook,
  ParsedPostFreezeOrder,
  ParsedSeepnews,
  ParsedTicker,
  ParsedTrade,
  ParsedWallet,
  STPRecord,
} from "./stp.js";

export interface TickerSnapshot {
  ticker: string;
  coinId: string;
  price: number;
  mcap: number;
  poolFiat: number;
  poolCoin: number;
  freeze: string;
  ceil: number | null;
  nextCeil: number;
  feePct: number | null;
  bid: number | null;
  ask: number | null;
  ts: number;
}

function newTicker(ticker: string): TickerSnapshot {
  return {
    ticker,
    coinId: "",
    price: 0,
    mcap: 0,
    poolFiat: 0,
    poolCoin: 0,
    freeze: "growing",
    ceil: null,
    nextCeil: 0,
    feePct: null,
    bid: null,
    ask: null,
    ts: 0,
  };
}

export class MarketView {
  readonly tickers = new Map<string, TickerSnapshot>();
  readonly walletsFiat = new Map<string, number>();
  readonly walletsCoin = new Map<string, number>(); // key: `${agent}|${ticker}`
  leaderboard: Array<[number, string, number]> = [];
  readonly seepnews: ParsedSeepnews[] = [];
  readonly trades: ParsedTrade[] = [];
  readonly pfos = new Map<string, ParsedPostFreezeOrder>();
  readonly errors: ParsedError[] = [];
  lastBlock: ParsedBlock | null = null;
  readonly agentsSeen = new Set<string>();

  private ticker(ticker: string): TickerSnapshot {
    let t = this.tickers.get(ticker);
    if (!t) {
      t = newTicker(ticker);
      this.tickers.set(ticker, t);
    }
    return t;
  }

  apply(record: STPRecord): void {
    switch (record.kind) {
      case "ticker": {
        const r = record as ParsedTicker;
        const t = this.ticker(r.ticker);
        t.coinId = r.coinId;
        t.price = r.price;
        t.mcap = r.mcap;
        t.poolFiat = r.poolFiat;
        t.poolCoin = r.poolCoin;
        t.freeze = r.freeze;
        t.ceil = r.ceil;
        t.nextCeil = r.nextCeil;
        if (r.feePct !== null) t.feePct = r.feePct;
        t.ts = r.ts;
        break;
      }
      case "orderbook": {
        const r = record as ParsedOrderBook;
        const t = this.ticker(r.ticker);
        t.bid = r.bid;
        t.ask = r.ask;
        break;
      }
      case "freeze_event": {
        const r = record as ParsedFreezeEvent;
        const t = this.ticker(r.ticker);
        t.freeze = r.event === "freeze_active" ? "frozen" : r.event;
        t.ceil = r.ceil;
        break;
      }
      case "wallet": {
        const r = record as ParsedWallet;
        if (r.ticker !== null && r.balance !== null) {
          this.walletsCoin.set(`${r.agent}|${r.ticker}`, r.balance);
        } else {
          this.walletsFiat.set(r.agent, r.fiat);
        }
        break;
      }
      case "leaderboard":
        this.leaderboard = (record as ParsedLeaderboard).ranks;
        break;
      case "seepnews": {
        const r = record as ParsedSeepnews;
        this.seepnews.push(r);
        this.agentsSeen.add(r.agent);
        break;
      }
      case "trade": {
        const r = record as ParsedTrade;
        this.trades.push(r);
        this.agentsSeen.add(r.agent);
        break;
      }
      case "post_freeze_order": {
        const r = record as ParsedPostFreezeOrder;
        this.pfos.set(r.orderId, r);
        break;
      }
      case "error":
        this.errors.push(record as ParsedError);
        break;
      case "block":
        this.lastBlock = record as ParsedBlock;
        break;
      case "agent":
        this.agentsSeen.add((record as ParsedAgent).agent);
        break;
      case "aicoin_launch": {
        const r = record as ParsedAICoinLaunch;
        this.ticker(r.ticker).coinId = r.coinId;
        break;
      }
      default:
        // header / meta carry no per-entity state worth caching
        break;
    }
  }

  applyMany(records: STPRecord[]): void {
    for (const record of records) this.apply(record);
  }

  price(ticker: string): number | null {
    return this.tickers.get(ticker)?.price ?? null;
  }

  isFrozen(ticker: string): boolean {
    return this.tickers.get(ticker)?.freeze === "frozen";
  }

  coinIdFor(ticker: string): string | null {
    const t = this.tickers.get(ticker);
    return t && t.coinId ? t.coinId : null;
  }

  recentSeepnews(category?: string, limit = 20): ParsedSeepnews[] {
    const items = category ? this.seepnews.filter((p) => p.category === category) : this.seepnews;
    return items.slice(-limit);
  }

  coinBalance(agentId: string, ticker: string): number {
    return this.walletsCoin.get(`${agentId}|${ticker}`) ?? 0;
  }

  /** $syntrends cash chip (1:1 ledger), not an AICoin. */
  fiatBalance(agentId: string): number {
    return this.walletsFiat.get(agentId) ?? 0;
  }

  cashBalance(agentId: string): number {
    return this.fiatBalance(agentId);
  }
}
