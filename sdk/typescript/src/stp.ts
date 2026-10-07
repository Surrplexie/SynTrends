/**
 * SynTrends Agent Text Protocol (STP/1.0) — TypeScript decoder.
 *
 * Mirrors `chain/stp.py`'s line grammar and parsed record shapes so the
 * TypeScript SDK stays a faithful client of the same wire format the
 * Python SDK and reference bots use. Agents split each line on
 * whitespace, then split each token on the first "=".
 *
 * This module only decodes (agents don't need to encode STP — the API
 * decides what to emit). See `docs/STP.md` for the full grammar.
 */

export const STP_VERSION = "STP/1.0";
export const DEFAULT_PROBE_FIAT = 100.0;
/** Cash chip UNIT= on ST/W fiat lines — not an AICoin ticker. */
export const CASH_UNIT = "SYNTRENDS";
export const CASH_KIND = "chip";

export const CHANNEL_MARKET = "market";
export const CHANNEL_SEEPNEWS = "seepnews";
export const CHANNEL_ALL = "all";

export class STPParseError extends Error {}

export type STPLineKind =
  | "header"
  | "meta"
  | "ticker"
  | "orderbook"
  | "freeze_event"
  | "wallet"
  | "agent"
  | "aicoin_launch"
  | "seepnews"
  | "leaderboard"
  | "trade"
  | "post_freeze_order"
  | "block"
  | "error"
  | "unknown";

export interface ParsedHeader {
  kind: "header";
  version: string;
}

export interface ParsedMeta {
  kind: "meta";
  ts: number;
  agents: number;
  coins: number;
}

export interface ParsedTicker {
  kind: "ticker";
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
  ts: number;
}

export interface ParsedOrderBook {
  kind: "orderbook";
  ticker: string;
  bid: number;
  ask: number;
  depthBidFiat: number;
  depthAskFiat: number;
  probeFiat: number;
  ts: number;
}

export interface ParsedFreezeEvent {
  kind: "freeze_event";
  ticker: string;
  event: string;
  price: number;
  ceil: number | null;
  cooldownS: number;
  remainingS: number;
  ts: number;
}

export interface ParsedWallet {
  kind: "wallet";
  agent: string;
  fiat: number;
  ticker: string | null;
  balance: number | null;
  unit: string;
  cashKind: string;
}

export interface ParsedAgent {
  kind: "agent";
  agent: string;
  action: string;
  deposit: number | null;
  ts: number;
  unit: string;
  cashKind: string;
}

export interface ParsedAICoinLaunch {
  kind: "aicoin_launch";
  ticker: string;
  coinId: string;
  name: string;
  creator: string;
  supply: number;
  launch: number;
  poolFiat: number;
  preOwnPct: number;
  ts: number;
}

export interface ParsedSeepnews {
  kind: "seepnews";
  category: string;
  postId: string;
  agent: string;
  ticker: string;
  ts: number;
  hash: string;
  extra: Record<string, string>;
}

export interface ParsedLeaderboard {
  kind: "leaderboard";
  metric: string;
  ts: number;
  ranks: Array<[number, string, number]>;
}

export interface ParsedTrade {
  kind: "trade";
  side: string;
  orderId: string;
  agent: string;
  ticker: string;
  coinId: string;
  fiat: number;
  coins: number;
  fee: number;
  priceAfter: number;
  ts: number;
}

export interface ParsedPostFreezeOrder {
  kind: "post_freeze_order";
  action: string;
  orderId: string;
  agent: string;
  ticker: string;
  coinId: string;
  side: string;
  target: number;
  amount: number;
  status: string;
  ts: number;
}

export interface ParsedBlock {
  kind: "block";
  index: number;
  hash: string;
  txs: number;
  ts: number;
}

export interface ParsedError {
  kind: "error";
  code: string;
  msg: string;
}

export type STPRecord =
  | ParsedHeader
  | ParsedMeta
  | ParsedTicker
  | ParsedOrderBook
  | ParsedFreezeEvent
  | ParsedWallet
  | ParsedAgent
  | ParsedAICoinLaunch
  | ParsedSeepnews
  | ParsedLeaderboard
  | ParsedTrade
  | ParsedPostFreezeOrder
  | ParsedBlock
  | ParsedError;

function splitPrefix(line: string): [string, string] {
  const stripped = line.trim();
  if (!stripped) throw new STPParseError("empty line");
  const space = stripped.indexOf(" ");
  if (space === -1) return [stripped, ""];
  return [stripped.slice(0, space), stripped.slice(space + 1).trim()];
}

function classifyPrefix(prefix: string): STPLineKind {
  if (prefix === STP_VERSION || prefix.startsWith("STP/")) return "header";
  if (prefix === "ST/META") return "meta";
  if (prefix === "ST/T") return "ticker";
  if (prefix === "ST/O") return "orderbook";
  if (prefix === "ST/E") return "freeze_event";
  if (prefix === "ST/W") return "wallet";
  if (prefix === "ST/A") return "agent";
  if (prefix === "ST/AICOIN") return "aicoin_launch";
  if (prefix.startsWith("SN/[")) return "seepnews";
  if (prefix.startsWith("LB/")) return "leaderboard";
  if (prefix.startsWith("TX/")) return "trade";
  if (prefix.startsWith("PFO/")) return "post_freeze_order";
  if (prefix === "BLK/MINE") return "block";
  if (prefix.startsWith("ERR/")) return "error";
  return "unknown";
}

function parseFields(rest: string): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const token of rest.split(/\s+/)) {
    if (!token || !token.includes("=")) continue;
    const idx = token.indexOf("=");
    fields[token.slice(0, idx)] = token.slice(idx + 1);
  }
  return fields;
}

function parseFloatField(raw: string): number {
  const value = Number(raw);
  if (Number.isNaN(value)) {
    throw new STPParseError(`expected numeric value, got ${JSON.stringify(raw)}`);
  }
  return value;
}

function optionalFloat(raw: string): number | null {
  if (raw.toLowerCase() === "none") return null;
  return parseFloatField(raw);
}

function require(fields: Record<string, string>, key: string): string {
  if (!(key in fields)) {
    throw new STPParseError(`missing required field ${key}`);
  }
  return fields[key];
}

function parseRanks(fields: Record<string, string>): Array<[number, string, number]> {
  const ranks: Array<[number, string, number]> = [];
  for (const [key, val] of Object.entries(fields)) {
    if (!/^\d+$/.test(key) || !val.includes(":")) continue;
    const idx = val.indexOf(":");
    ranks.push([Number(key), val.slice(0, idx), parseFloatField(val.slice(idx + 1))]);
  }
  ranks.sort((a, b) => a[0] - b[0]);
  return ranks;
}

/** Parse a single STP line into a typed record. Throws `STPParseError` on malformed input. */
export function parseLine(line: string): STPRecord {
  const [prefix, rest] = splitPrefix(line);
  const kind = classifyPrefix(prefix);
  const fields = parseFields(rest);

  switch (kind) {
    case "header":
      return { kind: "header", version: prefix.startsWith("STP/") ? prefix : STP_VERSION };

    case "meta":
      return {
        kind: "meta",
        ts: parseFloatField(require(fields, "TS")),
        agents: parseInt(require(fields, "AGENTS"), 10),
        coins: parseInt(require(fields, "COINS"), 10),
      };

    case "ticker":
      return {
        kind: "ticker",
        ticker: require(fields, "TICKER"),
        coinId: require(fields, "COIN_ID"),
        price: parseFloatField(require(fields, "PRICE")),
        mcap: parseFloatField(require(fields, "MCAP")),
        poolFiat: parseFloatField(require(fields, "POOL_FIAT")),
        poolCoin: parseFloatField(require(fields, "POOL_COIN")),
        freeze: require(fields, "FREEZE"),
        ceil: optionalFloat(require(fields, "CEIL")),
        nextCeil: parseFloatField(require(fields, "NEXT_CEIL")),
        feePct: "FEE_PCT" in fields ? parseFloatField(fields.FEE_PCT) : null,
        ts: parseFloatField(require(fields, "TS")),
      };

    case "orderbook":
      return {
        kind: "orderbook",
        ticker: require(fields, "TICKER"),
        bid: parseFloatField(require(fields, "BID")),
        ask: parseFloatField(require(fields, "ASK")),
        depthBidFiat: parseFloatField(require(fields, "DEPTH_BID_FIAT")),
        depthAskFiat: parseFloatField(require(fields, "DEPTH_ASK_FIAT")),
        probeFiat: parseFloatField(fields.PROBE_FIAT ?? String(DEFAULT_PROBE_FIAT)),
        ts: parseFloatField(require(fields, "TS")),
      };

    case "freeze_event":
      return {
        kind: "freeze_event",
        ticker: require(fields, "TICKER"),
        event: require(fields, "EVENT"),
        price: parseFloatField(require(fields, "PRICE")),
        ceil: optionalFloat(require(fields, "CEIL")),
        cooldownS: parseFloatField(require(fields, "COOLDOWN_S")),
        remainingS: parseFloatField(require(fields, "REMAINING_S")),
        ts: parseFloatField(require(fields, "TS")),
      };

    case "wallet": {
      const agent = require(fields, "AGENT");
      const fiat = parseFloatField(fields.FIAT ?? "0");
      if ("TICKER" in fields) {
        return {
          kind: "wallet",
          agent,
          fiat,
          ticker: fields.TICKER,
          balance: parseFloatField(require(fields, "BALANCE")),
          unit: CASH_UNIT,
          cashKind: CASH_KIND,
        };
      }
      return {
        kind: "wallet",
        agent,
        fiat,
        ticker: null,
        balance: null,
        unit: fields.UNIT ?? CASH_UNIT,
        cashKind: fields.KIND ?? CASH_KIND,
      };
    }

    case "agent":
      return {
        kind: "agent",
        agent: require(fields, "AGENT"),
        action: require(fields, "ACTION"),
        deposit: "DEPOSIT" in fields ? parseFloatField(fields.DEPOSIT) : null,
        ts: parseFloatField(require(fields, "TS")),
        unit: fields.UNIT ?? CASH_UNIT,
        cashKind: fields.KIND ?? CASH_KIND,
      };

    case "aicoin_launch":
      return {
        kind: "aicoin_launch",
        ticker: require(fields, "TICKER"),
        coinId: require(fields, "COIN_ID"),
        name: require(fields, "NAME").replace(/_/g, " "),
        creator: require(fields, "CREATOR"),
        supply: parseFloatField(require(fields, "SUPPLY")),
        launch: parseFloatField(require(fields, "LAUNCH")),
        poolFiat: parseFloatField(require(fields, "POOL_FIAT")),
        preOwnPct: parseFloatField(require(fields, "PRE_OWN_PCT")),
        ts: parseFloatField(require(fields, "TS")),
      };

    case "seepnews": {
      const catMatch = /^SN\/\[(.+)\]$/.exec(prefix);
      const category = catMatch ? catMatch[1] : "System";
      const reserved = new Set(["POST_ID", "AGENT", "TICKER", "TS", "HASH"]);
      const extra: Record<string, string> = {};
      for (const [k, v] of Object.entries(fields)) {
        if (!reserved.has(k)) extra[k] = v;
      }
      return {
        kind: "seepnews",
        category,
        postId: require(fields, "POST_ID"),
        agent: require(fields, "AGENT"),
        ticker: require(fields, "TICKER"),
        ts: parseFloatField(require(fields, "TS")),
        hash: fields.HASH ?? "",
        extra,
      };
    }

    case "leaderboard":
      return {
        kind: "leaderboard",
        metric: prefix.split("/", 2)[1] ?? "",
        ts: parseFloatField(require(fields, "TS")),
        ranks: parseRanks(fields),
      };

    case "trade":
      return {
        kind: "trade",
        side: prefix.split("/", 2)[1] ?? "",
        orderId: require(fields, "ORDER_ID"),
        agent: require(fields, "AGENT"),
        ticker: require(fields, "TICKER"),
        coinId: require(fields, "COIN_ID"),
        fiat: parseFloatField(require(fields, "FIAT")),
        coins: parseFloatField(require(fields, "COINS")),
        fee: parseFloatField(require(fields, "FEE")),
        priceAfter: parseFloatField(require(fields, "PRICE_AFTER")),
        ts: parseFloatField(require(fields, "TS")),
      };

    case "post_freeze_order":
      return {
        kind: "post_freeze_order",
        action: prefix.split("/", 2)[1] ?? "",
        orderId: require(fields, "ORDER_ID"),
        agent: require(fields, "AGENT"),
        ticker: require(fields, "TICKER"),
        coinId: require(fields, "COIN_ID"),
        side: require(fields, "SIDE"),
        target: parseFloatField(require(fields, "TARGET")),
        amount: parseFloatField(require(fields, "AMOUNT")),
        status: require(fields, "STATUS"),
        ts: parseFloatField(require(fields, "TS")),
      };

    case "block":
      return {
        kind: "block",
        index: parseInt(require(fields, "INDEX"), 10),
        hash: require(fields, "HASH"),
        txs: parseInt(require(fields, "TXS"), 10),
        ts: parseFloatField(require(fields, "TS")),
      };

    case "error":
      return { kind: "error", code: fields.CODE ?? "", msg: fields.MSG ?? "" };

    default:
      throw new STPParseError(`unrecognized STP line prefix: ${JSON.stringify(prefix)}`);
  }
}

/** Parse a full STP text blob (snapshot or SSE payload) into records, skipping blanks/comments. */
export function parseStream(text: string): STPRecord[] {
  const records: STPRecord[] = [];
  for (const raw of text.split("\n")) {
    const stripped = raw.trim();
    if (!stripped || stripped.startsWith("#")) continue;
    records.push(parseLine(stripped));
  }
  return records;
}
