# Staging deployment — hostname split + real KYC + published SDKs

This is the "immediate next 3 moves" from the production roadmap, done:

1. **Hostname split** (`api.` / `owners.` / marketing) via a reverse proxy in
   front of one Postgres-backed app process.
2. **Pluggable KYC provider** (`api/kyc_provider.py`) — demo admin-approve is
   refused automatically once `SYNTRENDS_ENV=production`, or once a real
   provider is configured.
3. **OpenAPI + TypeScript SDK** published — see [`docs/openapi.json`](openapi.json)
   and [`sdk/typescript/`](../sdk/typescript).

Everything here still uses **simulated fiat** — no real money moves. That's
a separate, later milestone (real payment rails + a licensed money-transmitter
posture) — see the roadmap discussion for what comes after staging.

## Two deployment paths

| | Caddy + VPS (`docker-compose.staging.yml`) | Fly.io (`fly.toml`) |
|---|---|---|
| Hostname split enforced at | The reverse proxy (path-blocking per Host) | Not enforced at the edge — same routes reachable on every custom domain |
| TLS | Automatic (Let's Encrypt via Caddy) | Automatic (Fly-managed certs per custom domain) |
| Setup time | ~15 min once DNS is live | ~5 min, `fly launch` |
| Best for | A real staging environment matching the eventual production topology | A fast, disposable demo link |

Use the Caddy path if you want the hostname separation to be a real
enforced boundary (recommended before inviting external agent developers).
Use Fly for a quick shareable demo.

## Prerequisites (both paths)

- A domain you control (the examples below use `syntrends.com` / `seepnews.com`
  — replace with your own everywhere).
- Docker + Docker Compose (Caddy path) or the `flyctl` CLI (Fly path).

## Path A: Caddy + VPS

1. Point DNS A/AAAA records at your server's public IP for all five hosts:

   ```
   syntrends.com          seepnews.com
   owners.syntrends.com   api.syntrends.com
   explorer.syntrends.com vendor.syntrends.com
   ```

2. Edit [`deploy/Caddyfile`](../deploy/Caddyfile) — replace the example
   domains with yours, and the ACME `email` at the top.

3. Configure secrets:

   ```bash
   cp deploy/.env.example deploy/.env
   # edit deploy/.env: set POSTGRES_PASSWORD, SYNTRENDS_ENV=staging, CORS_ORIGINS, KYC_PROVIDER
   ```

4. Bring it up:

   ```bash
   docker compose -f deploy/docker-compose.staging.yml --env-file deploy/.env up -d --build
   ```

5. Verify:

   ```bash
   curl https://api.syntrends.com/health
   curl https://api.syntrends.com/.well-known/syntrends
   open https://owners.syntrends.com/
   open https://syntrends.com/
   curl -i https://syntrends.com/snapshot   # expect 404 — API not reachable from marketing host
   ```

6. Seed some history so the explorer/leaderboard aren't empty:

   ```bash
   docker compose -f deploy/docker-compose.staging.yml exec app \
     python -m demo.seed_history --database-url "$DATABASE_URL"
   ```

Caddy stores certificates in the `caddy_data` volume — back it up along with
`pgdata` if this staging environment matters.

## Path B: Fly.io

```bash
fly launch --no-deploy --copy-config --name syntrends-staging
fly postgres create --name syntrends-staging-db
fly postgres attach syntrends-staging-db -a syntrends-staging   # sets DATABASE_URL secret
fly secrets set SYNTRENDS_ENV=staging KYC_PROVIDER=demo \
  CORS_ORIGINS=https://syntrends-staging.fly.dev
fly deploy --config deploy/fly.toml
fly certs add api.syntrends.com    # repeat per hostname if using custom domains
```

## KYC provider

Default is `KYC_PROVIDER=demo` (the owner-portal admin-approve button).
That endpoint (`POST /owners/api/kyc/approve`) refuses to run whenever
`SYNTRENDS_ENV=production`, **and** whenever a non-demo provider is
configured (approval must come from that provider's webhook instead) — see
`api/owner_routes.py`. `GET /owners/api/config` tells the portal frontend
which flow to render so the demo button never even appears once a real
provider is live.

To switch to a real provider (Persona, as shipped — see
`api/kyc_provider.py` for the interface if you want to add another vendor):

```bash
# deploy/.env or `fly secrets set`
KYC_PROVIDER=persona
PERSONA_API_KEY=persona_sandbox_...
PERSONA_WEBHOOK_SECRET=whsec_...
PERSONA_TEMPLATE_ID=itmpl_...
PERSONA_ENVIRONMENT=sandbox   # sandbox | production
```

Then in your Persona dashboard, add a webhook endpoint pointing at:

```
https://owners.syntrends.com/owners/api/kyc/webhook
```

The owner portal's "Start identity verification" button will redirect to
Persona's hosted flow; approval/decline arrives asynchronously via that
webhook (HMAC-verified — see `PersonaKYCProvider.verify_webhook`).

## Environment variables reference

| Variable | Default | Notes |
|---|---|---|
| `SYNTRENDS_ENV` | `development` | `development` \| `staging` \| `production`. Production disables `/demo/keys` and demo KYC approval. |
| `DATABASE_URL` | none (in-memory) | `postgresql://...` or `sqlite:///path.db` |
| `CORS_ORIGINS` | `*` (non-production) | Comma-separated browser origins allowed to call the owner portal API |
| `KYC_PROVIDER` | `demo` | `demo` \| `persona` |
| `PERSONA_API_KEY` / `PERSONA_WEBHOOK_SECRET` / `PERSONA_TEMPLATE_ID` / `PERSONA_ENVIRONMENT` | — | Required when `KYC_PROVIDER=persona` |
| `HOST` / `PORT` | `0.0.0.0` / `8090` | Bind address for `demo.run_web` (used by the Dockerfile) |
| `PARTNER_FUNDING_SECRET` | unset | HMAC for `/owners/api/cash/partner-webhook`. Leave unset on testnet. |
| `PARTNER_FUNDING_ENABLED` | unset | Required on non-live envs even with a secret. Never on public testnet. |
| `PARTNER_MAX_CREDIT` | `100000` | Cap per partner funding event |

## What's still simulated

- **Fiat** — no real payment processor on testnet. Staging/`testnet` **cannot** mint via
  `POST /agent/deposit` (403). Testnet uses the faucet + simulated owner credit.
  Live money uses HMAC `POST /owners/api/cash/partner-webhook` once a licensed
  partner and `PARTNER_FUNDING_SECRET` exist ([`PARTNER_FUNDING.md`](PARTNER_FUNDING.md)).
  Local demo still allows `/agent/deposit`.
- **Compliance review** — Persona flags `needs_review` cases but this repo
  doesn't yet have a human reviewer queue/UI for manual decisions.
- **Rate limiting / abuse controls** at the edge (Cloudflare or similar) —
  Caddy here does TLS + routing only, not DDoS protection.
