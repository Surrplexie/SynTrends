# Changelog

All notable changes to the **published SDKs** (`syntrends` on PyPI, `@syntrends/sdk` on npm)
and public testnet surface are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
SDK versions are synchronized in this repo (`0.x.y` in `pyproject.toml` and `sdk/typescript/package.json`).

## [Unreleased]

### Changed

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
