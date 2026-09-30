# Fly.io public testnet — cost control & operations

Hosted demo URLs (when running):

**https://testnet.syntrends.com** (primary) · **https://syntrends-testnet.fly.dev** (fallback)

| Page | URL |
|------|-----|
| Owner portal | https://testnet.syntrends.com/owners/ |
| Status | https://testnet.syntrends.com/status/ |
| Explorer | https://testnet.syntrends.com/explorer/ |
| Join (on app) | https://testnet.syntrends.com/join.html |
| Marketing join | https://syntrends.com/join.html |

Public launch (DNS/CORS/Persona): [`PUBLIC_LAUNCH.md`](PUBLIC_LAUNCH.md) · URL map: [`ops/public_urls.json`](../ops/public_urls.json)

The public testnet is **always on** (`min_machines_running = 1`). Park is emergency-only (`park confirm`). Cold starts are not part of the join path.

---

## Daily workflow

**Develop locally** (free):

```powershell
python scripts/ship_testnet.py --no-e2e --port 8099
$env:SYNTRENDS_URL = "http://127.0.0.1:8099"
python -m demo.overnight_bot --hours 0.5
```

**Keep the public URL up** (default):

```powershell
.\scripts\fly_testnet.ps1 ensure
.\scripts\fly_testnet.ps1 health
.\scripts\fly_testnet.ps1 certs    # DNS/TLS for testnet.syntrends.com
python scripts/launch_check.py
```

Unix:

```bash
./scripts/fly_testnet.sh ensure
./scripts/fly_testnet.sh health
SYNTRENDS_URL=https://testnet.syntrends.com python -m demo.e2e_testnet
```

Emergency park (stops the join door):

```powershell
.\scripts\fly_testnet.ps1 park confirm
```

---

## What costs money on Fly

| Resource | App name (typical) | Billing when |
|----------|-------------------|--------------|
| **App VM** | `syntrends-testnet` | Running or auto-started (512 MB shared CPU) |
| **Postgres** | `syntrends-testnet-db` | **Always** if cluster exists — **biggest cost** |
| **Volumes** | attached to Postgres | Storage per GB-month |

A **3-node HA Postgres** cluster is overkill for a solo demo testnet. Expect **most of the bill** from Postgres, not the app.

Check spend: [fly.io/dashboard](https://fly.io/dashboard) → Billing.

---

## Cost controls (in repo)

### 1. Always-on machines (`deploy/fly.testnet.toml`)

After you redeploy with the updated config:

- `auto_stop_machines = "off"` — do not sleep the join door
- `auto_start_machines = true` — recover if Fly stops a machine
- `min_machines_running = 1` — one VM stays up
- `512mb` VM — smaller than previous 1 GB default

Redeploy once to apply:

```powershell
.\scripts\fly_testnet.ps1 deploy
# or: fly deploy -c deploy/fly.testnet.toml
```

### 2. Emergency park (`scale count 0`)

Stops app compute immediately. Requires an explicit confirm:

```powershell
.\scripts\fly_testnet.ps1 park confirm
```

Start again:

```powershell
.\scripts\fly_testnet.ps1 ensure
```

### 3. Downgrade or remove Postgres

**Option A — keep data, reduce Postgres cost**

List clusters:

```powershell
fly postgres list
```

If you created a 3-node HA cluster, consider migrating to a **single-node** Fly Postgres or an external free tier (Neon, Supabase) and updating the `DATABASE_URL` secret:

```powershell
fly secrets set DATABASE_URL="postgresql://..." -a syntrends-testnet
fly deploy -c deploy/fly.testnet.toml
```

Re-seed if you start fresh:

```powershell
fly ssh console -a syntrends-testnet -C "python -m demo.seed_testnet"
```

**Option B — ephemeral testnet (cheapest)**

Remove `DATABASE_URL` secret and use SQLite inside the container (state lost on redeploy). Only for throwaway demos — not recommended if you want persistent chain history.

**Option C — full teardown**

Only when you are sure you do not need the data:

```powershell
fly apps destroy syntrends-testnet-db
fly apps destroy syntrends-testnet
```

---

## Initial deploy (reference)

Prerequisites: [flyctl](https://fly.io/docs/flyctl/install/), `fly auth login`.

```powershell
fly apps create syntrends-testnet
fly postgres create --name syntrends-testnet-db --region iad
fly postgres attach syntrends-testnet-db -a syntrends-testnet
fly secrets set CORS_ORIGINS="https://syntrends.com,https://www.syntrends.com,https://seepnews.com,https://www.seepnews.com,https://testnet.syntrends.com,https://syntrends-testnet.fly.dev" -a syntrends-testnet
fly deploy -c deploy/fly.testnet.toml
fly ssh console -a syntrends-testnet -C "python -m demo.seed_testnet"
.\scripts\fly_testnet.ps1 ensure
.\scripts\fly_testnet.ps1 certs
.\scripts\fly_testnet.ps1 health
```

Prefer **single-node** Postgres for hobby testnet unless you need HA.

---

## Verify after start

```powershell
.\scripts\fly_testnet.ps1 status
SYNTRENDS_URL=https://testnet.syntrends.com python -m demo.e2e_testnet
```

---

## Local vs Fly

| | Local `ship_testnet.py` | Fly |
|--|-------------------------|-----|
| Cost | Free | App + Postgres |
| Persistence | `data/testnet_live.db` | Postgres |
| Best for | Dev, overnight bots, CI | Sharing URL with others |
| Uptime | While your PC runs | Public URL (always-on) |

**Recommendation:** leave Fly always-on through the Nov 1 public-beta window. Develop locally; do not park after a demo.

---

## Nightly CI E2E

GitHub Actions runs health every 15 minutes, launch_check every 6 hours, and the full testnet loop daily against Fly (see [`REPO_HYGIENE.md`](REPO_HYGIENE.md)). Set repo secret `FLY_API_TOKEN` so CI can scale the app if it was emergency-parked. Set Actions variable `SYNTRENDS_E2E_URL` to `https://testnet.syntrends.com`.

For Persona public beta E2E, also set Action secret `PERSONA_WEBHOOK_SECRET` to match Fly (workflow can forward it). Manual:

```powershell
$env:PERSONA_WEBHOOK_SECRET = "..."
python -m demo.e2e_testnet --base-url https://testnet.syntrends.com --check-pause
```

Manual trigger: **Actions → E2E Fly testnet → Run workflow**.

---

## Public beta KYC (Persona)

See [`PUBLIC_BETA.md`](PUBLIC_BETA.md). Short version:

```powershell
fly secrets set KYC_PROVIDER=persona `
  PERSONA_API_KEY=... PERSONA_WEBHOOK_SECRET=... PERSONA_TEMPLATE_ID=... `
  PERSONA_ENVIRONMENT=sandbox -a syntrends-testnet
```

Webhook: `https://testnet.syntrends.com/owners/api/kyc/webhook`  
(Fallback: `https://syntrends-testnet.fly.dev/owners/api/kyc/webhook`)

Until Persona secrets are set, the app may still run with `KYC_PROVIDER=demo` but **demo approve is disabled** — owners cannot get keys until Persona is configured.

Phase N cutover commands: `.\scripts\public_launch.ps1 print-cutover`

See [`OPS.md`](OPS.md) for monitoring, backup/restore, cost policy, and incidents.

See also: [`PUBLIC_LAUNCH.md`](PUBLIC_LAUNCH.md), [`TESTNET.md`](TESTNET.md), [`REPO_HYGIENE.md`](REPO_HYGIENE.md).
