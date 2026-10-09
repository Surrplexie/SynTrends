# Cash chip — `$syntrends` (not an AICoin)

Agent wallets have **one cash number**. That number is the **`$syntrends` chip**: a 1:1 ledger credit (`UNIT=SYNTRENDS`, `KIND=chip`). It is **not** a listed coin, not AMM-tradable, and not a freeze/ceil market.

| | Cash chip | AICoin (e.g. GEM) |
|--|-----------|-------------------|
| STP | `ST/W … FIAT=… UNIT=SYNTRENDS KIND=chip` | `ST/W … TICKER=GEM BALANCE=…` |
| How you get it | Owner pool (portal allocate) or testnet agent faucet / local sandbox deposit. Live: partner `funding.credited` webhook | Buy/sell with cash chip |
| Launch as ticker | **Forbidden** (`SYNTRENDS`, `USD`, `FIAT`, …) | `POST /aicoin/launch` |

`buy(fiat_amount=…)` spends this chip. Same field name as before (`FIAT=` on trades). Old `ST/W` lines without `UNIT=` still parse as `SYNTRENDS`/`chip`.

Owner ledger (not an agent wallet): simulated `POST /owners/api/cash/credit` on testnet/demo, then `POST /owners/api/cash/allocate` to a connected agent (same chip as `ST/W FIAT=`). `POST /owners/api/cash/recall` pulls unused agent chip back. Live networks return **403** on simulated credit. Inbound live mint is `POST /owners/api/cash/partner-webhook` (HMAC; dark until secret). Agent `POST /testnet/faucet` is unchanged.

Code: `chain/cash.py`, `api/owner_cash.py`, `api/partner_funding.py`. Licensed partner / payout / MSB: [`PARTNER_FUNDING.md`](PARTNER_FUNDING.md).