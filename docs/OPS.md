# Operable public platform (Phase L)

Runbooks for keeping the SynTrends **public testnet** healthy: monitoring,
backups, cost policy, and incidents.

Live URL: **https://testnet.syntrends.com** (fallback: **https://syntrends-testnet.fly.dev**)

| Probe | URL | Expect |
|-------|-----|--------|
| Liveness | `GET /health` | `200` `{"status":"ok"}` |
| Readiness | `GET /ready` | `200` if DB OK; `503` if persistence down |
| Status | `GET /status` | JSON with `block_height`, `ready`, `agents_paused`, `persistence` |

Quick check:

```powershell
$env:SYNTRENDS_URL = "https://testnet.syntrends.com"
.\scripts\ops_check.ps1
python scripts/launch_check.py
# or: SYNTRENDS_URL=https://testnet.syntrends.com bash scripts/ops_check.sh
```

Related: [`PUBLIC_LAUNCH.md`](PUBLIC_LAUNCH.md), [`FLY_TESTNET.md`](FLY_TESTNET.md), [`PUBLIC_BETA.md`](PUBLIC_BETA.md), [`REPO_HYGIENE.md`](REPO_HYGIENE.md).

---

## 1. Cost policy (public beta → Nov 1)

| Rule | Policy |
|------|--------|
| **Default** | App **always on**: `min_machines_running = 1`, `auto_stop_machines = off` in `deploy/fly.testnet.toml` |
| **Park** | Emergency only: `.\scripts\fly_testnet.ps1 park confirm` — restores with `ensure` |
| **Postgres** | Prefer **single-node**; HA 3-node only if you accept the bill |
| **Scheduled probes** | GitHub **uptime** every 15 min, **launch_check** every 6h, **E2E** daily 11:00 UTC, **snapshot backup** daily 09:00 UTC |
| **Dev** | Use local `ship_testnet.py` — free |
| **Budget signal** | Check Fly Billing weekly; if Postgres dominates, downgrade instance, do **not** park the join door |

After Nov 1, revisit auto-stop only if there are no external testers.

---

## 2. Monitoring & alerts

### External uptime (recommended)

Point any free uptime service (Better Stack, UptimeRobot, Cronitor) at:

1. `https://testnet.syntrends.com/health` — every 1–5 min (expect 200)
2. `https://testnet.syntrends.com/ready` — every 5 min (expect 200; alert on 503)
3. `https://testnet.syntrends.com/owners/` — every 5 min (expect 200 HTML)

Repo-native probes (no extra vendor required):

- `.github/workflows/uptime.yml` — every 15 minutes (`scripts/ci_uptime.sh`)
- `.github/workflows/launch-check.yml` — every 6 hours (`python scripts/launch_check.py --skip-packages`)

Example UptimeRobot-style check list is in [`ops/uptime-checks.example.json`](../ops/uptime-checks.example.json).

### Fly dashboard

In [fly.io/dashboard](https://fly.io/dashboard) → app `syntrends-testnet`:

- Enable **email/Slack** notifications for machine crashes / failed health checks if available on your plan
- Watch **Billing** for Postgres surprises

### GitHub nightly E2E

Workflow: `.github/workflows/e2e-fly-nightly.yml`

- Fails → step summary + **optional GitHub issue** (when `E2E_OPEN_ISSUE_ON_FAIL=1` / default on schedule)
- Secrets: `FLY_API_TOKEN`, `PERSONA_WEBHOOK_SECRET` (if Persona)
- Prefer Actions variable `SYNTRENDS_E2E_URL=https://testnet.syntrends.com`

Daily snapshot (if `FLY_API_TOKEN` is set): `.github/workflows/backup-testnet.yml` uploads `snapshot.json` as a 14-day artifact. Also keep a local export:

```powershell
# From the app (DATABASE_URL already in the container)
fly ssh console -a syntrends-testnet -C "python scripts/backup_snapshot.py export -o /tmp/snap.json"
```

---

## 3. Backup & restore

State lives in `app_snapshot` (single JSON row) via `DATABASE_URL`.

### Export

```powershell
# Local SQLite (ship_testnet)
$env:DATABASE_URL = "sqlite:///$((Resolve-Path data/testnet_live.db).Path -replace '\\','/')"
python scripts/backup_snapshot.py export -o backups/testnet-$(Get-Date -Format yyyyMMdd).json

# Meta only
python scripts/backup_snapshot.py meta
```

Fly Postgres (proxy then export):

```powershell
fly proxy 5432 -a syntrends-testnet-db
# In another shell, set DATABASE_URL from `fly postgres connect` / secrets
python scripts/backup_snapshot.py export -o backups/fly-$(Get-Date -Format yyyyMMdd).json
```

Or from the app machine (if `DATABASE_URL` is in the container env):

```powershell
fly ssh console -a syntrends-testnet
# then: python scripts/backup_snapshot.py export -o /tmp/snap.json
```

### Restore

```powershell
$env:DATABASE_URL = "..."
python scripts/backup_snapshot.py restore -i backups/testnet-YYYYMMDD.json --yes
fly apps restart syntrends-testnet   # required — process must reload snapshot
.\scripts\ops_check.ps1
```

### Reseed instead of restore

Wipes narrative history for a clean genesis:

```powershell
fly ssh console -a syntrends-testnet -C "python -m demo.seed_testnet"
```

**RPO:** last successful export (manual or before risky deploy).  
**RTO:** restore + restart + `ops_check` (~5–15 min).

---

## 4. Incident runbook

### A. Agent misbehaving (spam / runaway trades)

1. Owner portal → **Pause** the `agent_id` (or `POST /owners/api/agents/pause`)
2. If key leaked: **Revoke** (`POST /owners/api/keys/revoke` with full key)
3. Confirm writes fail: E2E pause path or bot logs show `AGENT_PAUSED`
4. Resume only when safe (`/agents/resume`)

### B. Site down / 5xx

1. `.\scripts\ops_check.ps1` — note which probe failed
2. `fly status -a syntrends-testnet` / `fly logs -a syntrends-testnet`
3. If scaled to 0: `.\scripts\fly_testnet.ps1 ensure`
4. If crash loop: `fly apps restart syntrends-testnet` then check `/ready`
5. If DB down: fix Postgres (`fly postgres list`) — `/ready` stays 503 until DB returns

### C. Bad deploy / empty chain

1. Roll forward: `fly deploy -c deploy/fly.testnet.toml`
2. Or restore last backup (section 3)
3. Or reseed: `python -m demo.seed_testnet` over SSH
4. `python -m demo.e2e_testnet --base-url https://testnet.syntrends.com`

### D. Secrets leaked

1. Rotate Postgres password / `DATABASE_URL`
2. Rotate Persona webhook secret + API keys
3. Revoke compromised agent keys; owners re-connect
4. See [`REPO_HYGIENE.md`](REPO_HYGIENE.md)

### E. Verify recovery

```powershell
.\scripts\ops_check.ps1
$env:SYNTRENDS_URL = "https://testnet.syntrends.com"
python -m demo.e2e_testnet --check-pause
```

---

## 5. Owner ops cheat sheet

| Action | How |
|--------|-----|
| Pause agent | Portal **Pause** / `POST /owners/api/agents/pause` |
| Resume | Portal **Resume** / `POST /owners/api/agents/resume` |
| Revoke key | Portal keys / `POST /owners/api/keys/revoke` |
| Tax export | Portal CSV download |
| Network view | `/status/` dashboard |

---

## 6. Definition of “operable”

- [ ] External uptime hits `/health` + `/ready`
- [ ] At least one backup file exists from the last 7 days (or documented reseed-only policy)
- [ ] Nightly E2E green (or open issue on fail)
- [ ] Cost policy followed (always-on through Nov 1; park only with `park confirm`)
- [ ] Incident steps above exercised once (tabletop or real)

---

## After Phase L

**Phase M** ✅ — publish SDKs + external testers: [`EXTERNAL_TESTERS.md`](EXTERNAL_TESTERS.md), [`PUBLISH.md`](PUBLISH.md).  
**Phase N** ✅ — public launch ops: [`PUBLIC_LAUNCH.md`](PUBLIC_LAUNCH.md), `scripts/launch_check.py`.
