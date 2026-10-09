# Ops log — hosted testnet

Dated record of what actually ran. Runbooks stay in [`OPS.md`](OPS.md), [`FLY_TESTNET.md`](FLY_TESTNET.md), [`PUBLIC_LAUNCH.md`](PUBLIC_LAUNCH.md). Do not put passwords or `st_agent_*` keys in this file.

**Primary:** https://testnet.syntrends.com  
**Fallback:** https://syntrends-testnet.fly.dev  
**Fly org / app:** `st-986` / `syntrends-testnet`  
**GitHub:** `Surrplexie/SynTrends`

---

## 2026-10-06 — Postgres cutover + Phase N gates (operator-only)

### Persistence

- Hosted testnet was on **sqlite inside the VM** (lost on crash/redeploy). Snapshot exported first as `backups/pre-postgres.json` (~39824 bytes, height ~9, 5 agents).
- Created **Fly Managed Postgres (MPG)** cluster `syntrends-testnet-db`, id `1zqyxr7gwz1rwp8m`, region **iad**, Basic. App user `fly-user`, database `fly-db`.
- Attached to `syntrends-testnet` (Connect UI: attached Oct 2026). Connection is **PgBouncer** at `pgbouncer.1zqyxr7gwz1rwp8m.flympg.net` with `sslmode=require`.
- **Dockerfile** no longer bakes `ENV DATABASE_URL=sqlite://...` (image ENV was beating Fly secrets).
- First Postgres boot **reseeded** empty `fly-db` (height 7 / 3 agents). Restored `pre-postgres.json` **on the VM** (laptop cannot reach MPG):

```text
fly ssh sftp put backups\pre-postgres.json /tmp/pre-postgres.json -a syntrends-testnet
fly ssh console -a syntrends-testnet --pty=false -C "python scripts/backup_snapshot.py restore -i /tmp/pre-postgres.json --yes"
fly apps restart syntrends-testnet
```

- After restart, `GET /status`: `block_height=9`, `agents=5`, `persistence.backend=postgres`, `persistence_ok=true`. Did **not** run `seed_testnet` after restore.

### Launch gates

From a Windows laptop (`SYNTRENDS_URL=https://testnet.syntrends.com`):

- `.\scripts\ops_check.ps1` — `/health` ok, `/ready` 200, env=testnet, height 9, agents 5, kyc=persona, persistence_ok=true
- `py -3 scripts\launch_check.py --require-persona --require-packages` — passed (PyPI `syntrends==0.1.0`, npm `@syntrends/sdk@0.1.0`, owners config persona / demo_approve=false / public_beta=true)

### GitHub / tag

- Installed GitHub CLI (`winget install GitHub.cli`).
- Actions secret `FLY_API_TOKEN` set on `Surrplexie/SynTrends`.
- Actions variable `SYNTRENDS_E2E_URL=https://testnet.syntrends.com`.
- Annotated tag `testnet-v1.0` already existed locally; **pushed** to origin (`[new tag]`).

### Not done (intentional)

- No `INVITE_TEMPLATE` send. No known external testers. Soak is operator-only (this PC + spare laptop + Ollama).
- Real fiat / MSB / production Persona — out of scope.
- MPG password rotate if a live URI was pasted in chat — still recommended; do it from MPG Connect → Rotate Password, then reset `DATABASE_URL` (never commit the URI).

### Next

Leave Fly always-on (`min_machines_running=1`). Watch Actions (uptime / launch_check / nightly E2E / snapshot backup). Invite only when there are people. Do not park; do not reseed.

---

## 2026-10-07 — Fiat mint gates (step 1, no partner yet)

- `POST /agent/deposit` mints only on local demo (`development` / `demo` / `test`). Public testnet and live-money envs return **403**.
- `SYNTRENDS_ENV=production|mainnet|live` forces faucet **off** even if `FAUCET_ENABLED=1`.
- Hosted testnet still uses simulated `POST /testnet/faucet`.

---

## 2026-10-07 — `$syntrends` is a chip, not a coin (step 3)

- Same agent fiat number; STP now emits `UNIT=SYNTRENDS KIND=chip`.
- Cannot `launch` / `buy` ticker `SYNTRENDS` / `USD` / `FIAT` / etc. as an AICoin.
- Partner adapters (step 4) not built. Doc: [`CASH.md`](CASH.md).

---

## 2026-10-07 — Official explorer hostname

- Canonical chain view: `https://explorer.syntrends.com` (same `syntrends-testnet` app until mainnet).
- App redirects that Host `/` → `/explorer/`. Network name comes from `/status` (still `syntrends-testnet-1`).
- Needs Cloudflare CNAME + `fly certs add explorer.syntrends.com`. Path still works: `https://testnet.syntrends.com/explorer/`.

---

## 2026-10-08 — Owner $syntrends ledger + allocate

- Owner portal card **3c** and `GET/POST /owners/api/cash`, `/cash/credit`, `/cash/allocate`, `/cash/recall`.
- Simulated owner credit only when faucet or sandbox deposit is allowed (testnet/demo). Production/mainnet/live → **403**.
- Allocate/recall always for linked agents: owner pool ↔ agent `FIAT` chip. Does not mint AICoins.
- Agent faucet left in place for e2e.

---

## 2026-10-08 — Partner funding adapter (not live money)

- `POST /owners/api/cash/partner-webhook` HMAC `funding.credited` → owner chip. 404 with no secret. Testnet stays simulated credit (do not set `PARTNER_FUNDING_SECRET` on Fly testnet).
- Licensed processor, MSB, and payout-to-card are still counsel + partner. Doc: [`PARTNER_FUNDING.md`](PARTNER_FUNDING.md).

---

## 2026-10-08 — Deploy owner ledger to Fly testnet

- Ship `REM-1.08`/`REM-1.09` so `https://testnet.syntrends.com/owners/` has card 3c and `/owners/api/cash*`.

---

## 2026-10-09 — Hosted soak + hostname aliases + miner plan

- Portal card 3c is live. Simulated credit/allocate on Fly needs Persona KYC before agent connect (demo approve stays off).
- App `/` Host redirects for `owners.` / `api.` / `status.` / `explorer.testnet` (same machine). DNS/certs still operator Cloudflare + `fly certs add`.
- Public miners not opened. Local `python -m demo.run_miner`. Doc: [`MINERS.md`](MINERS.md).
