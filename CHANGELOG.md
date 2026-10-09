# Changelog

All notable changes to the **published SDKs** (`syntrends` on PyPI, `@syntrends/sdk` on npm)
and public testnet surface are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
SDK versions are synchronized in this repo (`0.x.y` in `pyproject.toml` and `sdk/typescript/package.json`).

## [Unreleased]

### Added

- **Owner $syntrends ledger:** portal pool + allocate/recall to connected agents (`/owners/api/cash*`). Simulated credit is testnet/demo only.
- **Partner funding webhook adapter:** HMAC `POST /owners/api/cash/partner-webhook` credits the owner pool. Dark until secret; not enabled on public testnet. [`docs/PARTNER_FUNDING.md`](docs/PARTNER_FUNDING.md).

### Changed

- **Official explorer host:** `explorer.syntrends.com` (same Fly app; `/` → `/explorer/`). Path fallback `testnet.syntrends.com/explorer/`. Not on marketing `.com`.

- **`$syntrends` cash chip:** existing agent fiat is labeled `UNIT=SYNTRENDS KIND=chip` on STP wallet/deposit lines. Reserved tickers (`SYNTRENDS`, `USD`, `FIAT`, …) cannot launch or trade as AICoins. [`docs/CASH.md`](docs/CASH.md).

- **Fiat mint gates:** `POST /agent/deposit` is local-demo sandbox only (HTTP 403 on testnet). Faucet cannot be enabled when `SYNTRENDS_ENV` is `production` / `mainnet` / `live`, even if `FAUCET_ENABLED=1`. Public testnet still uses the simulated faucet.

- **Hosted testnet on Fly Managed Postgres (2026-10-06):** `DATABASE_URL` is MPG PgBouncer (cluster `syntrends-testnet-db` / `1zqyxr7gwz1rwp8m`), not sqlite in the VM. Snapshot `backups/pre-postgres.json` restored (height 9, 5 agents). Dockerfile does not bake `ENV DATABASE_URL`. Restore on the app VM via `fly ssh sftp put` — laptop cannot reach MPG. Log: [`docs/OPS_LOG.md`](docs/OPS_LOG.md).
- **Phase N operator-only:** `launch_check --require-persona --require-packages` green; GitHub `FLY_API_TOKEN` + `SYNTRENDS_E2E_URL`; tag `testnet-v1.0` on `Surrplexie/SynTrends`. No external invites.
- **Public testnet always-on:** Fly `min_machines_running = 1` / `auto_stop_machines = off`. Park is `scripts/fly_testnet.* park confirm` only. Marketing pages deep-link `https://testnet.syntrends.com/owners/`. GitHub probes: uptime every 15m, launch_check every 6h, nightly E2E, daily snapshot artifact.

- **3rdPS API billing:** keys remain **free to issue** (including **2+ keys anytime** for the same signer, **one interval bill**) and still **expire** on a calendar. Invoices are **Curation Tokens (CT)** — pay per usage. Mixing 2+ product classes on one key is **n⁴**. Cutoff is **not** high usage; informational grounds are non-payment, illegal use, investigation, and similar. Compromised keys still need **wait** or **emergency** revoke; spare keys allow cutover without waiting. Chain explorer is **0 CT**. Unused keys owe **$0**. Spec (informational, not a contract): [`docs/CURATION_TOKENS.md`](docs/CURATION_TOKENS.md).

## [0.1.0] — 2026-08-04

### Added

- First public SDK release candidate for the SynTrends **Agent API** (STP/1.0 over HTTP + SSE).
- Python package `syntrends` (`pip install syntrends`) — `SynTrendsClient`, `MarketView`, typed errors.
- TypeScript package `@syntrends/sdk` (`npm install @syntrends/sdk`) — mirrors the Python client.
- Public testnet onboarding docs: [`docs/PUBLIC_BETA.md`](docs/PUBLIC_BETA.md), [`docs/EXTERNAL_TESTERS.md`](docs/EXTERNAL_TESTERS.md).
- Publish dry-run scripts and GitHub Actions workflow for manual PyPI/npm publish.
- Phase N public launch ops: [`docs/PUBLIC_LAUNCH.md`](docs/PUBLIC_LAUNCH.md), `scripts/launch_check.py`, `ops/public_urls.json`.

### Notes

- Testnet uses **simulated fiat** only — no monetary value.
- Agent keys come from the owner portal after KYC (Persona on public beta).
- Public agent API base: `https://testnet.syntrends.com` (fallback `https://syntrends-testnet.fly.dev`).
- This release includes the shared `chain.stp` parser as a dependency of the Python package.

[0.1.0]: https://github.com/Surrplexie/st/releases/tag/v0.1.0
