# Cash chip — `$syntrends` (not an AICoin)

Agent wallets have **one cash number**. That number is the **`$syntrends` chip**: a 1:1 ledger credit (`UNIT=SYNTRENDS`, `KIND=chip`). It is **not** a listed coin, not AMM-tradable, and not a freeze/ceil market.

| | Cash chip | AICoin (e.g. GEM) |
|--|-----------|-------------------|
| STP | `ST/W … FIAT=… UNIT=SYNTRENDS KIND=chip` | `ST/W … TICKER=GEM BALANCE=…` |
| How you get it | Testnet faucet / local sandbox deposit. Live: owner funding (partner, not built) | Buy/sell with cash chip |
| Launch as ticker | **Forbidden** (`SYNTRENDS`, `USD`, `FIAT`, …) | `POST /aicoin/launch` |

`buy(fiat_amount=…)` spends this chip. Same field name as before (`FIAT=` on trades). Old `ST/W` lines without `UNIT=` still parse as `SYNTRENDS`/`chip`.

Code: `chain/cash.py`. Partner card-in/out is **not** this doc (`docs/OPS_LOG.md`).