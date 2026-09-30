# Platform release checklist — `testnet-v1.0` (Phase N)

Declare the **working public release**: strangers can join via `.com`, KYC, install SDKs, and trade on the public testnet.

Runbook: [`PUBLIC_LAUNCH.md`](PUBLIC_LAUNCH.md) · URL map: [`ops/public_urls.json`](../ops/public_urls.json)

---

## Gate checklist

### Domain & identity

- [ ] `testnet.syntrends.com` DNS + `fly certs` OK
- [ ] Marketing CTAs → `https://testnet.syntrends.com/owners/`
- [ ] `CORS_ORIGINS` includes `.com` + testnet + fly.dev fallback
- [ ] Persona webhook = `https://testnet.syntrends.com/owners/api/kyc/webhook`
- [ ] `GET /owners/api/config` → `kyc_provider=persona`, `demo_admin_approve_enabled=false`

### Engineering

- [ ] CI green on `main`
- [ ] Nightly Fly E2E green (or known issue filed); prefer `SYNTRENDS_E2E_URL=https://testnet.syntrends.com`
- [ ] `.\scripts\ops_check.ps1` against primary URL
- [ ] `python scripts/launch_check.py --require-persona` passes
- [ ] Phase J: owner pause/resume verified once
- [ ] Phase L: backup taken or reseed policy accepted ([`OPS.md`](OPS.md))

### Packages

- [ ] `python scripts/publish_check.py` passes
- [ ] `syntrends` on PyPI and `@syntrends/sdk` on npm at aligned version
- [ ] `python scripts/launch_check.py --require-packages` passes
- [ ] [`CHANGELOG.md`](../CHANGELOG.md) updated

### Docs / invite

- [ ] [`EXTERNAL_TESTERS.md`](EXTERNAL_TESTERS.md) + [`INVITE_TEMPLATE.md`](INVITE_TEMPLATE.md) accurate
- [ ] [`PUBLIC_LAUNCH.md`](PUBLIC_LAUNCH.md) followed for cutover order

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
