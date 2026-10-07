# Platform release checklist — `testnet-v1.0` (Phase N)

Declare the **working public release**: strangers can join via `.com`, KYC, install SDKs, and trade on the public testnet.

Runbook: [`PUBLIC_LAUNCH.md`](PUBLIC_LAUNCH.md) · URL map: [`ops/public_urls.json`](../ops/public_urls.json) · Log: [`OPS_LOG.md`](OPS_LOG.md)

**2026-10-06:** engineering gates + `testnet-v1.0` tag done. Invites **not** sent (operator-only).

---

## Gate checklist

### Domain & identity

- [x] `testnet.syntrends.com` DNS + `fly certs` OK (launch_check HTTP 200 on `/owners/` `/join.html`)
- [x] Marketing CTAs → `https://testnet.syntrends.com/owners/`
- [x] `CORS_ORIGINS` includes `.com` + testnet + fly.dev fallback
- [ ] Persona webhook = `https://testnet.syntrends.com/owners/api/kyc/webhook` (confirm in Persona dashboard if not already)
- [x] `GET /owners/api/config` → `kyc_provider=persona`, `demo_admin_approve_enabled=false`

### Engineering

- [ ] CI green on `main` (check Actions after token set)
- [ ] Nightly Fly E2E green (or known issue filed); `SYNTRENDS_E2E_URL` **set** 2026-10-06
- [x] `.\scripts\ops_check.ps1` against primary URL (2026-10-06)
- [x] `python scripts/launch_check.py --require-persona` passes (2026-10-06)
- [ ] Phase J: owner pause/resume verified once
- [x] Phase L: `backups/pre-postgres.json` restored onto MPG ([`OPS.md`](OPS.md))

### Packages

- [ ] `python scripts/publish_check.py` passes (re-run if cutting a new SDK)
- [x] `syntrends` on PyPI and `@syntrends/sdk` on npm at `0.1.0`
- [x] `python scripts/launch_check.py --require-packages` passes (2026-10-06)
- [x] [`CHANGELOG.md`](../CHANGELOG.md) updated (Unreleased: MPG cutover)

### Docs / invite

- [x] [`EXTERNAL_TESTERS.md`](EXTERNAL_TESTERS.md) + [`INVITE_TEMPLATE.md`](INVITE_TEMPLATE.md) exist — **not sent**
- [x] [`PUBLIC_LAUNCH.md`](PUBLIC_LAUNCH.md) cutover through tag; invite step deferred

### Git & hygiene

```powershell
git tag -a testnet-v1.0 -m "Public testnet v1 — Phase N launch"
git push origin testnet-v1.0

git tag -a v0.1.0 -m "syntrends / @syntrends/sdk 0.1.0"
git push origin v0.1.0
```

- [ ] `main` requires CI status checks ([`REPO_HYGIENE.md`](REPO_HYGIENE.md))

---

## Post-release

1. Invite 3–10 testers ([`INVITE_TEMPLATE.md`](INVITE_TEMPLATE.md))
2. Label issues `external-tester`
3. Uptime monitors on primary ([`ops/uptime-checks.example.json`](../ops/uptime-checks.example.json))
4. Uptime monitors on primary ([`ops/uptime-checks.example.json`](../ops/uptime-checks.example.json)) plus GitHub `uptime.yml`
5. Keep Fly always-on; emergency park only: `.\scripts\fly_testnet.ps1 park confirm`

**Done means:** a stranger installs the SDK, completes KYC, and trades on the public testnet without cloning.
