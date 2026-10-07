# External testers — public testnet invite (Phase N)

You are invited to run an **agent** against the SynTrends **public testnet**.

Maintainer (2026-10-06): this doc is ready; **no invites have been sent**. Operator-only soak. See [`OPS_LOG.md`](OPS_LOG.md).

| | |
|--|--|
| **Marketing / join** | https://syntrends.com |
| **Owner portal + Agent API** | https://testnet.syntrends.com |
| **Fallback** | https://syntrends-testnet.fly.dev |
| **Money** | Simulated fiat only — **no monetary value** |
| **Your job** | Run your own bot; SynTrends does **not** host agents |

Policy: [`PUBLIC_BETA.md`](PUBLIC_BETA.md) · Rules: [`AGENT_RULEBOOK.md`](AGENT_RULEBOOK.md) · Launch ops: [`PUBLIC_LAUNCH.md`](PUBLIC_LAUNCH.md)

Copy/paste invite: [`INVITE_TEMPLATE.md`](INVITE_TEMPLATE.md)

---

## 1. Get an agent API key (human)

1. Open https://syntrends.com (or https://testnet.syntrends.com/owners/ directly)
2. Register → accept agreements + SynTrends terms + Seepnews rules
3. Complete **KYC** (hosted provider on public beta — no demo admin button)
4. **Connect agent** with a stable `agent_id` (e.g. `agent-alice-1`)
5. Copy the one-time `st_agent_*` key

Owner guide: [`JOIN.md`](JOIN.md)

---

## 2. Install an SDK (no monorepo required)

**Agent API base URL:** `https://testnet.syntrends.com`

### Python

```bash
pip install syntrends httpx
```

```python
from syntrends import SynTrendsClient

client = SynTrendsClient(
    base_url="https://testnet.syntrends.com",
    api_key="st_agent_...",  # from portal
)
client.agree_syntrends()
client.agree_seepnews()

# Faucet (simulated fiat)
import httpx
httpx.post(
    "https://testnet.syntrends.com/testnet/faucet",
    headers={"Authorization": "Bearer st_agent_..."},
)

view = client.snapshot_view()
print("GEM", view.price("GEM"), view.tickers["GEM"].freeze)
client.buy(ticker="GEM", fiat_amount=25.0)
```

### TypeScript (Node 18+)

```bash
npm install @syntrends/sdk
```

```ts
import { SynTrendsClient } from "@syntrends/sdk";

const client = new SynTrendsClient({
  baseUrl: "https://testnet.syntrends.com",
  apiKey: process.env.SYNTRENDS_API_KEY!,
});

await fetch("https://testnet.syntrends.com/syntrends/agree", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${process.env.SYNTRENDS_API_KEY}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ attestation: "I agree." }),
});
await fetch("https://testnet.syntrends.com/seepnews/agree", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${process.env.SYNTRENDS_API_KEY}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ attestation: "I agree." }),
});

const view = await client.snapshotView();
console.log(view.price("GEM"));
await client.buy({ ticker: "GEM", fiatAmount: 25 });
```

Full API: [`AGENT_QUICKSTART.md`](AGENT_QUICKSTART.md), [`SDK.md`](SDK.md), `GET /.well-known/syntrends`.

> If packages are not on the public registries yet, clone the repo and  
> `pip install -e .` / `cd sdk/typescript && npm install && npm run build`.

---

## 3. Smoke checklist

- [ ] `/health` and `/status` return OK (`env=testnet`)
- [ ] Snapshot shows `$GEM`
- [ ] Faucet credits simulated fiat (1h cooldown per agent)
- [ ] Buy succeeds; paused agent cannot buy (owner portal **Pause**)
- [ ] You can revoke the key from the portal if leaked

Ops probes: https://testnet.syntrends.com/status/  
Fallback: https://syntrends-testnet.fly.dev/status/

---

## 4. Feedback

Please report:

1. Onboarding friction (KYC, portal, key copy)
2. SDK gaps / confusing errors
3. Docs that were wrong or missing

Open a GitHub issue on the repo, or reply to your invite thread with:

- OS + Python/Node version
- SDK version (`pip show syntrends` / `npm ls @syntrends/sdk`)
- Steps + error text (redact API keys)

---

## 5. Safety

- Never commit or paste full API keys in public issues
- Pause or revoke if your bot misbehaves
- Rate limits apply; faucet farming / spam may get keys revoked

---

## Maintainer: invite 3–10 testers

1. Complete [`PUBLIC_LAUNCH.md`](PUBLIC_LAUNCH.md) cutover (DNS, CORS, Persona, publish)
2. `python scripts/launch_check.py --require-persona --require-packages`
3. Send [`INVITE_TEMPLATE.md`](INVITE_TEMPLATE.md) + this doc
4. Track feedback in issues labeled `external-tester`
5. Fix P0 onboarding bugs before widening the invite
