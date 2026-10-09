# Phase N — Public launch (ops)

Go-live for the **working public release**: strangers use `syntrends.com` → KYC → SDK → trade on the **public testnet** (simulated fiat). No new product features — DNS, CORS, Persona, packages, gates, invites.

Canonical URL map: [`ops/public_urls.json`](../ops/public_urls.json)

| Surface | Primary URL |
|---------|-------------|
| Marketing | https://syntrends.com |
| Public testnet (agents + portal) | https://testnet.syntrends.com |
| Chain explorer (official host) | https://explorer.syntrends.com |
| Owner portal | https://testnet.syntrends.com/owners/ |
| Fallback (ops) | https://syntrends-testnet.fly.dev |

**Done means:** a stranger completes onboarding on `.com`, installs `syntrends` / `@syntrends/sdk`, and trades without cloning.

## Status (2026-10-06)

See [`OPS_LOG.md`](OPS_LOG.md). Gates and tag are done. **Invites are not sent** (no external testers yet). Operator-only soak.

| Item | State |
|------|--------|
| DNS/TLS `testnet.syntrends.com` | Live (`launch_check` `/owners/` `/join.html`) |
| Persona on testnet | `kyc_provider=persona`, `demo_admin_approve_enabled=false` |
| SDKs 0.1.0 | PyPI + npm |
| Fly MPG + restore | height 9, 5 agents, `backend=postgres` |
| `launch_check --require-persona --require-packages` | Passed |
| `FLY_API_TOKEN` + `SYNTRENDS_E2E_URL` | Set on `Surrplexie/SynTrends` |
| Tag `testnet-v1.0` | Pushed to origin |
| `INVITE_TEMPLATE` | **Not sent** |
| Real fiat | Out of scope |

---

## Preconditions (Phases K–M)

- [x] Persona KYC path ([`PUBLIC_BETA.md`](PUBLIC_BETA.md))
- [x] Ops probes / backup ([`OPS.md`](OPS.md))
- [x] SDK publish path ([`PUBLISH.md`](PUBLISH.md), [`EXTERNAL_TESTERS.md`](EXTERNAL_TESTERS.md))

---

## 1. DNS + TLS (Fly custom domain)

Point DNS at the Fly app `syntrends-testnet` (A/AAAA or CNAME per Fly certs output):

| Hostname | Target |
|----------|--------|
| `testnet.syntrends.com` | Fly app `syntrends-testnet` |
| `explorer.syntrends.com` | Same app — official chain view (`/` → `/explorer/`) |

Optional aliases (same Fly app; `/` redirects to the matching mount once DNS+certs exist):

| Hostname | `/` goes to |
|----------|-------------|
| `explorer.testnet.syntrends.com` | `/explorer/` |
| `owners.testnet.syntrends.com` | `/owners/` |
| `api.testnet.syntrends.com` | `/.well-known/syntrends` |
| `status.testnet.syntrends.com` | `/status/` |

Path URLs on `testnet.syntrends.com` keep working. Cloudflare: CNAME each name to `syntrends-testnet.fly.dev` (DNS only), then `fly certs add <host> -a syntrends-testnet`.

```powershell
.\scripts\fly_testnet.ps1 certs
# Cloudflare: CNAME explorer.syntrends.com -> syntrends-testnet.fly.dev
# (same records as testnet.syntrends.com)
fly certs check explorer.syntrends.com -a syntrends-testnet
```

Marketing hosts (`syntrends.com`, `seepnews.com`) stay on your existing static/hosting. Marketing HTML in this repo deep-links **`https://testnet.syntrends.com/owners/`** (`data-portal` + `web/shared/portal-link.js` rewrites to `/owners/` on localhost/Fly). Helper: `.\scripts\fly_testnet.ps1 certs`.

---

## 2. CORS + Persona cutover

```powershell
fly secrets set CORS_ORIGINS="https://syntrends.com,https://www.syntrends.com,https://seepnews.com,https://www.seepnews.com,https://testnet.syntrends.com,https://syntrends-testnet.fly.dev" `
  KYC_PROVIDER=persona `
  PERSONA_API_KEY=... `
  PERSONA_WEBHOOK_SECRET=... `
  PERSONA_TEMPLATE_ID=... `
  PERSONA_ENVIRONMENT=sandbox `
  -a syntrends-testnet
```

In the Persona dashboard, set the webhook to:

```
https://testnet.syntrends.com/owners/api/kyc/webhook
```

(Keep the fly.dev webhook URL temporarily if you dual-run during cutover.)

Confirm:

```powershell
.\scripts\fly_testnet.ps1 start
curl https://testnet.syntrends.com/owners/api/config
# expect: kyc_provider=persona, demo_admin_approve_enabled=false, public_beta=true
```

Helper (prints the secret commands; does not upload secrets):

```powershell
.\scripts\public_launch.ps1 print-cutover
```

One-shot orchestrator (create/deploy/CORS/certs/checks when Fly auth works):

```powershell
.\scripts\go_live.ps1
.\scripts\go_live.ps1 -Strict   # after Persona + PyPI/npm
```

---

## 3. Publish SDKs

1. Repo secrets: `PYPI_API_TOKEN`, `NPM_TOKEN`
2. Actions → **Publish SDKs** → confirm `0.1.0` → `both`
3. Or follow [`PUBLISH.md`](PUBLISH.md) manually

```powershell
python scripts/publish_check.py
pip index versions syntrends   # after publish
npm view @syntrends/sdk version
```

---

## 4. Launch gates (automated)

```powershell
$env:SYNTRENDS_URL = "https://testnet.syntrends.com"
.\scripts\fly_testnet.ps1 start
.\scripts\ops_check.ps1
python scripts/launch_check.py
# Strict (fail if packages missing / KYC not persona):
python scripts/launch_check.py --require-persona --require-packages
```

Optional full E2E (needs Persona webhook secret matching Fly):

```powershell
$env:PERSONA_WEBHOOK_SECRET = "..."
python -m demo.e2e_testnet --base-url https://testnet.syntrends.com --check-pause
```

Platform checklist: [`RELEASE.md`](RELEASE.md).

---

## 5. Git + branch protection

```powershell
git tag -a testnet-v1.0 -m "Public testnet v1 — Phase N launch"
git push origin testnet-v1.0

# After PyPI/npm publish:
git tag -a v0.1.0 -m "syntrends / @syntrends/sdk 0.1.0"
git push origin v0.1.0
```

Enable `main` required checks ([`REPO_HYGIENE.md`](REPO_HYGIENE.md)).

Set Actions vars/secrets if needed:

| Name | Purpose |
|------|---------|
| `SYNTRENDS_E2E_URL` | Prefer `https://testnet.syntrends.com` |
| `FLY_API_TOKEN` | Nightly wake |
| `PERSONA_WEBHOOK_SECRET` | Nightly KYC E2E |

---

## 6. Open the door

**Deferred.** The join door is live and empty. Do not send [`INVITE_TEMPLATE.md`](INVITE_TEMPLATE.md) until there are people. Until then: soak (operator + laptop + Ollama), leave Fly always-on, watch Actions.

When inviting:

1. Send [`INVITE_TEMPLATE.md`](INVITE_TEMPLATE.md) + [`EXTERNAL_TESTERS.md`](EXTERNAL_TESTERS.md) to 3–10 testers
2. Label issues `external-tester`
3. Point uptime monitors at primary URLs ([`ops/uptime-checks.example.json`](../ops/uptime-checks.example.json))
4. Emergency park only: `.\scripts\fly_testnet.ps1 park confirm` ([`FLY_TESTNET.md`](FLY_TESTNET.md))

---

## Cutover order (safe)

1. Add cert + DNS for `testnet.syntrends.com` (keep fly.dev working)
2. Expand `CORS_ORIGINS` (include both primary + fallback)
3. Flip Persona webhook to primary; smoke KYC once
4. Publish SDKs
5. `launch_check.py --require-persona --require-packages`
6. Update marketing CTAs → testnet owners URL
7. Tag + invite

Rollback: point invites / marketing back to `https://syntrends-testnet.fly.dev`; Persona webhook can follow.

---

## Out of scope (not Phase N)

- Real fiat / mainnet
- Hostname-strict API split on Fly edge (use Docker+Caddy later — [`TESTNET.md`](TESTNET.md))
- Hosting third-party agent processes

---

## Related

| Doc | Role |
|-----|------|
| [`EXTERNAL_TESTERS.md`](EXTERNAL_TESTERS.md) | Tester invite |
| [`PUBLISH.md`](PUBLISH.md) | PyPI / npm |
| [`RELEASE.md`](RELEASE.md) | Gate checklist |
| [`PUBLIC_BETA.md`](PUBLIC_BETA.md) | Beta policy |
| [`OPS.md`](OPS.md) | Incidents / backup |
| [`FLY_TESTNET.md`](FLY_TESTNET.md) | Park / start / cost |
