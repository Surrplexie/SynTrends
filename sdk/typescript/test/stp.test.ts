import assert from "node:assert/strict";
import { test } from "node:test";

import { MarketView } from "../src/state.js";
import { parseLine, parseStream, STPParseError } from "../src/stp.js";

test("parses header line", () => {
  const rec = parseLine("STP/1.0");
  assert.equal(rec.kind, "header");
});

test("parses ticker line with fee", () => {
  const line =
    "ST/T TICKER=GEM COIN_ID=abc123 PRICE=1.282846 MCAP=12828.46 " +
    "POOL_FIAT=900.00 POOL_COIN=9000.00 FREEZE=growing CEIL=none " +
    "NEXT_CEIL=2.924893 FEE_PCT=0.01 TS=1700000000.0";
  const rec = parseLine(line);
  assert.equal(rec.kind, "ticker");
  if (rec.kind !== "ticker") throw new Error("unreachable");
  assert.equal(rec.ticker, "GEM");
  assert.equal(rec.coinId, "abc123");
  assert.equal(rec.price, 1.282846);
  assert.equal(rec.ceil, null);
  assert.equal(rec.feePct, 0.01);
  assert.equal(rec.ts, 1700000000.0);
});

test("parses ticker line without fee and with numeric ceiling", () => {
  const line =
    "ST/T TICKER=GEM COIN_ID=abc COIN_ID=abc PRICE=2.0 MCAP=20.0 " +
    "POOL_FIAT=10.0 POOL_COIN=5.0 FREEZE=frozen CEIL=2.5 NEXT_CEIL=3.0 TS=5.0";
  const rec = parseLine(line);
  if (rec.kind !== "ticker") throw new Error("unreachable");
  assert.equal(rec.freeze, "frozen");
  assert.equal(rec.ceil, 2.5);
  assert.equal(rec.feePct, null);
});

test("parses trade line", () => {
  const line =
    "TX/BUY ORDER_ID=o1 AGENT=trader-a TICKER=GEM COIN_ID=c1 FIAT=200.00 " +
    "COINS=168.76 FEE=0.02 PRICE_AFTER=1.264013 TS=1700000000.0";
  const rec = parseLine(line);
  assert.equal(rec.kind, "trade");
  if (rec.kind !== "trade") throw new Error("unreachable");
  assert.equal(rec.side, "BUY");
  assert.equal(rec.agent, "trader-a");
  assert.equal(rec.coins, 168.76);
});

test("parses seepnews line with category and extra fields", () => {
  const line =
    "SN/[Trade] POST_ID=p1 AGENT=trader-a TICKER=GEM TS=1700000100 " +
    "HASH=deadbeef SIDE=BUY COINS=899.92 FIAT=100.00";
  const rec = parseLine(line);
  assert.equal(rec.kind, "seepnews");
  if (rec.kind !== "seepnews") throw new Error("unreachable");
  assert.equal(rec.category, "Trade");
  assert.equal(rec.hash, "deadbeef");
  assert.equal(rec.extra.SIDE, "BUY");
  assert.equal(rec.extra.COINS, "899.92");
});

test("parses leaderboard ranks in order", () => {
  const line = "LB/MCAP TS=1700000000.0 2=DOG:100.00 1=GEM:12828.46";
  const rec = parseLine(line);
  assert.equal(rec.kind, "leaderboard");
  if (rec.kind !== "leaderboard") throw new Error("unreachable");
  assert.deepEqual(rec.ranks, [
    [1, "GEM", 12828.46],
    [2, "DOG", 100.0],
  ]);
});

test("parses error line", () => {
  const rec = parseLine("ERR/ CODE=AICOIN MSG=insufficient_fiat");
  assert.equal(rec.kind, "error");
  if (rec.kind !== "error") throw new Error("unreachable");
  assert.equal(rec.code, "AICOIN");
  assert.equal(rec.msg, "insufficient_fiat");
});

test("unrecognized prefix throws STPParseError", () => {
  assert.throws(() => parseLine("XX/UNKNOWN FOO=bar"), STPParseError);
});

test("parseStream skips blanks and comments", () => {
  const text = ["STP/1.0", "", "# a comment", "ST/META TS=1.0 AGENTS=1 COINS=0"].join("\n");
  const records = parseStream(text);
  assert.equal(records.length, 2);
  assert.equal(records[0].kind, "header");
  assert.equal(records[1].kind, "meta");
});

test("MarketView folds ticker + orderbook + freeze_event + wallet", () => {
  const view = new MarketView();
  view.applyMany(
    parseStream(
      [
        "ST/T TICKER=GEM COIN_ID=c1 PRICE=1.0 MCAP=10.0 POOL_FIAT=5.0 POOL_COIN=5.0 " +
          "FREEZE=growing CEIL=none NEXT_CEIL=2.0 TS=1.0",
        "ST/O TICKER=GEM BID=0.9 ASK=1.1 DEPTH_BID_FIAT=100 DEPTH_ASK_FIAT=100 TS=1.0",
        "ST/E TICKER=GEM EVENT=freeze_active PRICE=2.0 CEIL=2.0 COOLDOWN_S=10 REMAINING_S=5 TS=2.0",
        "ST/W AGENT=trader-a FIAT=500.00",
        "ST/W AGENT=trader-a TICKER=GEM BALANCE=42.0",
      ].join("\n"),
    ),
  );

  assert.equal(view.price("GEM"), 1.0);
  assert.equal(view.isFrozen("GEM"), true);
  assert.equal(view.coinIdFor("GEM"), "c1");
  assert.equal(view.fiatBalance("trader-a"), 500.0);
  assert.equal(view.cashBalance("trader-a"), 500.0);
  assert.equal(view.coinBalance("trader-a", "GEM"), 42.0);
  const snap = view.tickers.get("GEM");
  assert.equal(snap?.bid, 0.9);
  assert.equal(snap?.ask, 1.1);
});

test("MarketView tracks seepnews, trades, and errors", () => {
  const view = new MarketView();
  view.applyMany(
    parseStream(
      [
        "SN/[System] POST_ID=p1 AGENT=SYSTEM TICKER=GEM TS=1.0 MSG=hello",
        "TX/BUY ORDER_ID=o1 AGENT=a1 TICKER=GEM COIN_ID=c1 FIAT=10 COINS=5 FEE=0.1 PRICE_AFTER=2.0 TS=1.0",
        "ERR/ CODE=X MSG=bad",
      ].join("\n"),
    ),
  );
  assert.equal(view.seepnews.length, 1);
  assert.equal(view.trades.length, 1);
  assert.equal(view.errors.length, 1);
  assert.ok(view.agentsSeen.has("a1"));
});
