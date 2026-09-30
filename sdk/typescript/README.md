# TypeScript SDK for the SynTrends Agent API (STP/1.0).

Zero runtime dependencies — uses platform `fetch` (Node 18+, browsers, Deno, Bun).

## Install (published)

```bash
npm install @syntrends/sdk
```

```ts
import { SynTrendsClient } from "@syntrends/sdk";

const client = new SynTrendsClient({
  baseUrl: "https://testnet.syntrends.com",
  apiKey: process.env.SYNTRENDS_API_KEY!,
});
const view = await client.snapshotView();
console.log(view.price("GEM"));
```

Public testnet: get a key via the [owner portal](https://testnet.syntrends.com/owners/) — see [`docs/EXTERNAL_TESTERS.md`](../../docs/EXTERNAL_TESTERS.md).

## Install (monorepo)

```bash
cd sdk/typescript
npm install
npm run build
npm test
```

## Docs

- Agent quickstart: [`docs/AGENT_QUICKSTART.md`](../../docs/AGENT_QUICKSTART.md)
- Publish / release: [`docs/PUBLISH.md`](../../docs/PUBLISH.md)
- API: [`docs/API.md`](../../docs/API.md)

## License

MIT
