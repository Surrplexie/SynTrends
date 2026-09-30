# Repository hygiene

Maintainer checklist for **Surrplexie/st** — CI, branch protection, secrets, and deploy discipline.

---

## Nightly E2E on Fly

Workflow: [`.github/workflows/e2e-fly-nightly.yml`](../.github/workflows/e2e-fly-nightly.yml)

| Trigger | When |
|---------|------|
| Schedule | Daily 11:00 UTC |
| Manual | Actions → **E2E Fly testnet** → Run workflow |

Also: **Testnet uptime** every 15 min (`uptime.yml`), **Launch check** every 6h (`launch-check.yml`), **snapshot backup** daily 09:00 UTC (`backup-testnet.yml`).

**Required secrets:**

| Secret | Purpose |
|--------|---------|
| `FLY_API_TOKEN` | Wake scaled-to-zero machines |
| `PERSONA_WEBHOOK_SECRET` | Signed KYC webhook for E2E once public beta uses Persona |

**Optional variable:** `SYNTRENDS_E2E_URL` — prefer `https://testnet.syntrends.com` after Phase N DNS; default fallback is `https://syntrends-testnet.fly.dev`.

Each run:

1. `fly scale count 1` (if token set)
2. Wait up to 180s for `/health` + `env=testnet`
3. `python -m demo.e2e_testnet --check-pause` (full loop + pause/resume; Persona webhook when configured)

Public beta KYC policy: [`PUBLIC_BETA.md`](PUBLIC_BETA.md).  
Ops runbook (Phase L): [`OPS.md`](OPS.md).

Local parity:

```bash
export FLY_API_TOKEN=...   # optional
bash scripts/ci_fly_e2e.sh
```

The nightly job does **not** auto-park after success (avoids disrupting manual demos).

---

## Branch protection (GitHub)

Enable on **`main`**:

1. GitHub → **Settings** → **Branches** → **Add branch protection rule**
2. Branch name pattern: `main`
3. Enable:
   - **Require a pull request before merging** (optional for solo maintainer; recommended before collaborators)
   - **Require status checks to pass before merging**
   - Status checks: `Python 3.10`, `Python 3.11`, `Python 3.12`, `TypeScript SDK`, `OpenAPI export smoke`
4. Enable **Do not allow bypassing the above settings** (if you have org admin)

If `gh` CLI is installed later:

```bash
gh api repos/Surrplexie/st/branches/main/protection -X PUT \
  -f required_status_checks[strict]=true \
  -f required_status_checks[contexts][]='Python 3.12' \
  -f enforce_admins=true \
  -f required_pull_request_reviews[required_approving_review_count]=0 \
  -f restrictions=null
```

Adjust check names to match the exact labels in the **Actions** tab after the first green run.

---

## CI (`.github/workflows/ci.yml`)

Every push/PR to `main`:

| Job | What it catches |
|-----|-----------------|
| Python 3.10–3.12 | pytest regressions |
| TypeScript SDK | `npm test` on Linux |
| OpenAPI smoke | drift in `docs/openapi.json` |

Local pre-push:

```powershell
python -m pytest -q
python scripts/export_openapi.py
git diff docs/openapi.json
cd sdk/typescript; npm test
```

---

## Commit & deploy flow

1. Work on a feature branch (or direct to `main` if solo — still run pytest locally).
2. Push → wait for CI green.
3. Deploy Fly when the public testnet should pick up the change:

   ```powershell
   .\scripts\fly_testnet.ps1 deploy
   .\scripts\fly_testnet.ps1 ensure
   SYNTRENDS_URL=https://testnet.syntrends.com python -m demo.e2e_testnet
   ```

4. Do **not** park after deploy. Emergency only:

   ```powershell
   .\scripts\fly_testnet.ps1 park confirm
   ```

See [`FLY_TESTNET.md`](FLY_TESTNET.md) for cost details.

---

## Secrets — never commit

| Secret | Where it lives |
|--------|----------------|
| Fly Postgres password | Fly secrets / dashboard only |
| `DATABASE_URL` | `fly secrets set` |
| Owner/agent API keys | Owner portal; rotate if pasted in chat |
| Session tokens | Browser localStorage only |

If credentials appeared in logs, chat, or `tmp.txt` — **rotate Postgres password** and re-set `DATABASE_URL` on Fly.

`.gitignore` excludes internal docs (`docs/CI_AND_RELEASE.md`), local DBs, `.env`, and build artifacts.

---

## Version tags (optional)

When cutting a testnet milestone:

```powershell
git tag -a testnet-v1.0 -m "Public testnet E2E + 4h soak verified"
git push origin testnet-v1.0
```

Use semantic tags when publishing SDKs to PyPI/npm.

---

## Definition of “green to share testnet”

- [ ] CI green on `main`
- [ ] `python -m demo.e2e_testnet --base-url https://syntrends-testnet.fly.dev` passes
- [ ] `.\scripts\ops_check.ps1` passes (`/health` + `/ready` + `/status`)
- [ ] Fly app running (`.\scripts\fly_testnet.ps1 ensure`)
- [ ] Explorer shows blocks after seed
- [ ] No secrets in committed files
- [ ] Recent snapshot backup or documented reseed-only policy ([`OPS.md`](OPS.md))

---

## Related

| Doc | Purpose |
|-----|---------|
| [`OPS.md`](OPS.md) | Monitoring, backup, cost, incidents |
| [`FLY_TESTNET.md`](FLY_TESTNET.md) | Park/start/deploy, Postgres cost |
| [`TESTNET.md`](TESTNET.md) | Testnet env vars, Docker, local ship |
| [`PUBLIC_BETA.md`](PUBLIC_BETA.md) | Public beta + Persona |
| `docs/CI_AND_RELEASE.md` | Extended maintainer runbook (gitignored — local copy) |
