/**
 * Reference TypeScript SDK for the SynTrends Agent API (STP/1.0 over HTTP).
 *
 *     import { SynTrendsClient } from "@syntrends/sdk";
 *
 *     const client = await SynTrendsClient.registerAgent(
 *       "http://127.0.0.1:8080", "agent-my-bot",
 *     );
 *     await client.deposit("agent-my-bot", 10_000);
 *     const view = await client.snapshotView();
 *     console.log(view.price("GEM"));
 *     await client.buy({ ticker: "GEM", fiatAmount: 100 });
 */

export { DEFAULT_BASE_URL, SynTrendsClient } from "./client.js";
export type { SynTrendsClientOptions } from "./client.js";
export {
  AuthenticationError,
  ForbiddenError,
  NotFoundError,
  RateLimitedError,
  SynTrendsAPIError,
} from "./errors.js";
export { MarketView } from "./state.js";
export type { TickerSnapshot } from "./state.js";
export {
  CASH_KIND,
  CASH_UNIT,
  CHANNEL_ALL,
  CHANNEL_MARKET,
  CHANNEL_SEEPNEWS,
  parseLine,
  parseStream,
  STP_VERSION,
  STPParseError,
} from "./stp.js";
export type {
  ParsedAgent,
  ParsedAICoinLaunch,
  ParsedBlock,
  ParsedError,
  ParsedFreezeEvent,
  ParsedHeader,
  ParsedLeaderboard,
  ParsedMeta,
  ParsedOrderBook,
  ParsedPostFreezeOrder,
  ParsedSeepnews,
  ParsedTicker,
  ParsedTrade,
  ParsedWallet,
  STPLineKind,
  STPRecord,
} from "./stp.js";
