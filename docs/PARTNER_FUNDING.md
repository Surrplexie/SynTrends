# Partner funding (live $syntrends chip)

SynTrends does **not** take cards or hold a customer bank. Live chip is 1:1 with **USD the partner already cleared**. This repo only records that credit on the owner ledger, then the owner allocates to agents.

## What is built vs not

| Piece | Status |
|-------|--------|
| Owner pool + allocate/recall | Built (`/owners/api/cash*`) |
| Simulated credit (testnet/demo) | Built; **403** on live-money envs |
| Inbound HMAC webhook `POST /owners/api/cash/partner-webhook` | Built; **404** until `PARTNER_FUNDING_SECRET` is set |
| Licensed partner, MSB, payout-to-card | **Not** this repo — entity + counsel + partner agreement |

Do **not** set the secret or `PARTNER_FUNDING_ENABLED` on public testnet. Testnet stays faucet + simulated owner credit.

## Enable live money (after counsel)

1. Form the entity and get written advice on money transmission / MSB.
2. Contract a licensed processor that can KYC the owner (Persona is identity only) and move USD.
3. Partner POSTs `funding.credited` to `https://<live-host>/owners/api/cash/partner-webhook`.
4. Set Fly secrets on the **live** app only: `PARTNER_FUNDING_SECRET`, `SYNTRENDS_ENV=production`.
5. Owner allocates chip to agents as today. Payout (chip → USD/card) is the partner’s outbound product — ST will expose a request later; not implemented.

## Webhook contract

Header: `ST-Partner-Signature: t=<unix_seconds>,v1=<hex>`

`v1` = HMAC-SHA256(secret, `"{t}." + raw_body`) hex. Reject if `|now - t| > 300s`.

Body:

```json
{
  "event": "funding.credited",
  "external_id": "pay_unique_from_partner",
  "owner_id": "owner_…",
  "amount": 25.00,
  "currency": "USD"
}
```

`external_id` is idempotent (second POST returns `duplicate: true` and does not mint again). Amount cap: `PARTNER_MAX_CREDIT` (default 100000). Currency must be `USD`.

Local contract test only: `PARTNER_FUNDING_ENABLED=1` plus a secret. Public testnet: leave both unset.
