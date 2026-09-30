import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import { after, before, test } from "node:test";

import { AuthenticationError, ForbiddenError } from "../src/errors.js";
import { SynTrendsClient } from "../src/client.js";

/**
 * Minimal in-process mock of the SynTrends Agent API surface this SDK
 * touches (bootstrap, snapshot, one write, one SSE stream). This keeps
 * the TypeScript SDK test suite self-contained (no Python process
 * required); see `sdk/typescript/README.md` for a live-server smoke test.
 */
function startMockServer(): Promise<{ server: Server; baseUrl: string }> {
  const snapshotText = [
    "STP/1.0",
    "ST/META TS=1.0 AGENTS=1 COINS=1",
    "ST/W AGENT=agent-ts-test FIAT=1000.00",
    "ST/T TICKER=GEM COIN_ID=c1 PRICE=1.0 MCAP=10.0 POOL_FIAT=5.0 POOL_COIN=5.0 " +
      "FREEZE=growing CEIL=none NEXT_CEIL=2.0 TS=1.0",
  ].join("\n");

  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    const auth = req.headers["authorization"];

    if (req.method === "POST" && url.pathname === "/keys/agent") {
      let body = "";
      req.on("data", (chunk) => (body += chunk));
      req.on("end", () => {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ agent_id: "agent-ts-test", api_key: "st_agent_test_token" }));
      });
      return;
    }

    if (req.method === "POST" && url.pathname === "/keys/thirdps") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ api_key: "st_thirdps_test_token", api_class: "thirdps" }));
      return;
    }
    if (req.method === "POST" && url.pathname === "/keys/license") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ api_key: "st_thirdps_test_token", api_class: "thirdps" }));
      return;
    }

    if (url.pathname === "/snapshot") {
      if (auth !== "Bearer st_agent_test_token" && auth !== "Bearer st_thirdps_test_token") {
        res.writeHead(401, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ detail: "invalid key" }));
        return;
      }
      res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
      res.end(snapshotText);
      return;
    }

    if (req.method === "POST" && url.pathname === "/trade/buy") {
      if (auth === "Bearer st_thirdps_test_token") {
        res.writeHead(403, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ detail: "read-only key" }));
        return;
      }
      let body = "";
      req.on("data", (chunk) => (body += chunk));
      req.on("end", () => {
        const parsed = JSON.parse(body) as { fiat_amount: number };
        const line =
          `TX/BUY ORDER_ID=o1 AGENT=agent-ts-test TICKER=GEM COIN_ID=c1 ` +
          `FIAT=${parsed.fiat_amount.toFixed(2)} COINS=5.00 FEE=0.01 PRICE_AFTER=1.01 TS=2.0`;
        res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
        res.end(line);
      });
      return;
    }

    if (url.pathname === "/stream/market") {
      res.writeHead(200, {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
      });
      res.write(
        "data: ST/T TICKER=GEM COIN_ID=c1 PRICE=1.5 MCAP=15.0 POOL_FIAT=5.0 POOL_COIN=5.0 " +
          "FREEZE=growing CEIL=none NEXT_CEIL=2.0 TS=3.0\n\n",
      );
      res.write("data: ERR/ CODE=X MSG=done\n\n");
      res.end();
      return;
    }

    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ detail: "not found" }));
  });

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      resolve({ server, baseUrl: `http://127.0.0.1:${port}` });
    });
  });
}

let ctx: { server: Server; baseUrl: string };

before(async () => {
  ctx = await startMockServer();
});

after(() => {
  ctx.server.close();
});

test("registerAgent bootstraps a client with a working key", async () => {
  const client = await SynTrendsClient.registerAgent(ctx.baseUrl, "agent-ts-test");
  assert.equal(client.apiKey, "st_agent_test_token");
  const text = await client.snapshot();
  assert.ok(text.startsWith("STP/1.0"));
});

test("snapshotView builds a MarketView with wallet and ticker data", async () => {
  const client = await SynTrendsClient.registerAgent(ctx.baseUrl, "agent-ts-test");
  const view = await client.snapshotView();
  assert.equal(view.price("GEM"), 1.0);
  assert.equal(view.fiatBalance("agent-ts-test"), 1000.0);
});

test("invalid key raises AuthenticationError", async () => {
  const client = new SynTrendsClient({ baseUrl: ctx.baseUrl, apiKey: "st_agent_bogus" });
  await assert.rejects(() => client.snapshot(), AuthenticationError);
});

test("buy returns parsed STP trade records", async () => {
  const client = await SynTrendsClient.registerAgent(ctx.baseUrl, "agent-ts-test");
  const records = await client.buy({ ticker: "GEM", fiatAmount: 50 });
  assert.equal(records.length, 1);
  assert.equal(records[0].kind, "trade");
});

test("thirdps client cannot trade (403 -> ForbiddenError)", async () => {
  const client = await SynTrendsClient.issueThirdpsClient(ctx.baseUrl, "vendor");
  assert.equal(client.apiKey, "st_thirdps_test_token");
  await assert.rejects(() => client.buy({ ticker: "GEM", fiatAmount: 1 }), ForbiddenError);
});

test("streamMarket yields parsed SSE records then stops at stream end", async () => {
  const client = await SynTrendsClient.registerAgent(ctx.baseUrl, "agent-ts-test");
  const received: string[] = [];
  for await (const record of client.streamMarket({ live: false })) {
    received.push(record.kind);
  }
  assert.deepEqual(received, ["ticker", "error"]);
});
