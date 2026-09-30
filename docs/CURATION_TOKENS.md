# Curation Tokens (CT) — 3rdPS intake meter & commercial information

**Audience:** 3rdPS vendors (the **signer**) and SynTrends Inc. operators.

**Related:** [`THIRDPS_API.md`](THIRDPS_API.md) · [`API_KEY_LIFECYCLE.md`](API_KEY_LIFECYCLE.md) · [`THIRD_PARTY_SERVICES.md`](THIRD_PARTY_SERVICES.md) · [`syntrendrules.md`](syntrendrules.md)

---

## Document status (not a contract)

This file is **strict commercial and technical information**. It describes how SynTrends Inc. **intends** to meter and invoice **3rdPS API** intake, when access may be **cut off**, and how **keys** relate to **one signer / one bill**.

It is **not** a contract, license, invoice, security, or offer. It does **not** create rights, waive rights, or bind either party. Production obligations live only in the **signed 3rdPS vendor agreement** (and invoices issued under it) for that network. If this document and a signed agreement differ, **the signed agreement controls**.

Demo numbers (`GET /thirdps/quote`, `GET /thirdps/billing`, env `THIRDPS_USD_PER_CT`) are **illustrative**.

**Not Agent API.** Agent keys (`st_agent_*`) are a different product (owner KYC, trades, wallet). This file does not meter Agent API use.

---

## Parties

| Role | Who |
|------|------|
| **SynTrends** | SynTrends Inc. — operates the 3rdPS API and CT meter. |
| **3rdPS signer** | The **verified representing entity** named on the vendor record (legal name, jurisdiction, abuse contact). Keys are issued **to this entity**, not to end customers, partners, or “friend” HUDs. |
| **Credential** | One or more `st_thirdps_*` keys bound to **that same signer**. |

The signer is the **only** party SynTrends invoices. End users of the signer’s charts, digests, or archives **never** receive a SynTrends 3rdPS key and are **not** on this bill.

---

## Commercial model: pay per usage

3rdPS access is **pay per usage**, metered in **Curation Tokens (CT)** — a **unit of measured intake**, not a coin, not transferable, not listed, not an investment.

| Rule | Information |
|------|---------|
| **Mint** | Issuing a 3rdPS key is **$0**. There is no seat fee for holding a credential. |
| **Owed** | **USD = invoice_CT × USD/CT** for usage recorded in the **billing interval**. |
| **Idle** | A key with **raw CT = 0** in the interval contributes **$0** for that key. |
| **Not prepaid access** | SynTrends does not sell “unlimited 3rdPS” as the default. Volume is measured. |
| **Not a usage cutoff** | High CT does **not** by itself cut off the API. It **raises the invoice**. Rate limits may still return `429` (burst control), which is **not** a commercial cutoff. |
| **Chain** | `GET /explorer/api/*` is **0 CT** (public like BTC). No 3rdPS key required. |

USD/CT, interval length, tax, and late-fee mechanics are in the **signed agreement** (demo: `THIRDPS_USD_PER_CT`, default `0.001`).

---

## Billing interval and one bill

The signed agreement sets a **time interval** (for example monthly, yearly, or the period between vendor re-signs). That interval is the **only** commercial period SynTrends uses for this signer.

| Rule | Information |
|------|---------|
| **One signer → one bill** | All `st_thirdps_*` keys issued to **the same signer** roll into **one** invoice for the interval. There is not a separate legal account per key. |
| **Every active key is in scope** | If the signer holds **2+** keys, **each** key’s measured CT for the interval is **included**. You cannot pay “only key A” and leave key B unpaid. |
| **Spare keys** | A second key that is **never used** adds **$0** CT. It still exists on the account and still **expires** on its calendar if the agreement says credentials expire. |
| **Used spares** | If both keys are used (cutover, dual pollers, mistake), **both** usages are billed. Kitchen-sink **n⁴** applies **per key** (classes used on **that** credential), then sums onto the **one** invoice. |
| **Settlement** | The signer pays the **full** interval invoice by the due date in the agreement. Partial payment is **non-payment** for cutoff purposes. |
| **Interval vs key life** | The **bill** is per interval. A key may **expire** on a calendar (yearly / bi-yearly / sooner) so the signer must **re-sign** to keep credentials working. Expiry is **re-credentialing**, not a punishment for usage. |

Demo: `GET /thirdps/billing` is **per key** (meters that credential). Production invoicing **sums** those meters (and agreement adjustments) onto the **signer** invoice.

---

## Multiple 3rdPS keys (same signer)

The signer **may issue or request additional `st_thirdps_*` keys at any time** — early rotation, dual live + spare, regional pollers, or hygiene — **without** waiting for renewal, and **without** treating it as emergency turning.

| Allowed | Not allowed |
|---------|-------------|
| 2+ **active** 3rdPS keys for **the same signer** | Giving any key to **another company**, client, or reseller |
| Mint a **new** key whenever you want a fresh secret | One key **shared** across two legal entities |
| Keep a **ready spare** and cut traffic over **immediately** | Pretending a spare is a **second signer** or a **second bill** |
| Use different keys for **different product classes** (to avoid n⁴ on one credential) | End-customer keys (customers buy **your** product) |

**Why 2+ ready keys matter:** Invalidating a **compromised** credential still follows **wait** or **emergency** (below). A **pre-issued spare** lets you **keep serving** without waiting for SynTrends to turn the leaked key. You point production at the spare **now**; you still **must** get the leaked key **revoked**.

Agent API is **not** this rule. Extra `st_agent_*` keys are per `agent_id` / owner portal. Compromised **Agent** keys still require **wait** (rule re-sign turning) or **emergency turning** — a spare 3rdPS key does **not** replace an agent key.

---

## Cutoff (when SynTrends may stop 3rdPS access)

**Cutoff** means SynTrends **suspends or refuses** 3rdPS API authentication for the signer (some or all keys). Cutoff is **not** the same as `429`, calendar **expiry**, or a large CT invoice.

Informational **closed list** of cutoff grounds (production agreement may state the same more formally):

1. **Non-payment** — interval invoice not paid in full by the due date (including failure to pay after notice/cure if the agreement provides one).
2. **Illegal use** — use that is unlawful in a relevant jurisdiction, or that SynTrends reasonably determines is being used to commit or facilitate a crime.
3. **Investigation** — the signer, a controlling person, or the 3rdPS use is **under investigation** by SynTrends Inc., a regulator, or a law-enforcement / competent authority such that continued intake is unreasonable to leave on.
4. **Agreement breach of the same class** — e.g. **sharing** keys, relicensing the raw firehose, impersonating SynTrends, or other material vendor-term breaches the agreement treats as suspendable.
5. **Court or lawful order** — SynTrends is required to suspend.
6. **Safety of the network** — active, demonstrated abuse that threatens platform integrity (credential stuffing, credential published in public JS with ongoing theft, etc.), **limited** to stopping that abuse — not a substitute for “we dislike your price.”

**Not cutoff grounds (by themselves):**

- How many CT you used, or mixing 2+ product classes on one key (that is **price**, via n⁴).
- Holding 2+ keys, rotating early, or keeping a spare.
- Competing with other 3rdPS vendors.
- Agent-market outcomes, coin prices, or Seepnews content you did not post (3rdPS is read-only).

After cutoff for **non-payment**, restoration is typically **pay the overdue interval** (and any agreement cure). After cutoff for **illegal / investigation**, restoration follows the agreement and applicable law — not a CT payment.

Calendar **expiry** without renewal: credentials **stop working** until re-sign. That is **end of credential validity**, described separately from punitive cutoff. If the signer also **owes** an unpaid interval, both may apply.

---

## Compromise, revoke, wait, emergency

A **compromised** key (Agent **or** 3rdPS) — leaked, stolen, pasted in a public page, logged in a ticket — **must be taken out of service**. Issuing a new key does **not** by itself kill the old one.

| Action | 3rdPS | Agent API |
|--------|--------|-----------|
| **Issue a new key** | **Anytime** (same signer) | New agent keys via owner portal / KYC rules — **not** a 3rdPS mint |
| **Failover to a spare already issued** | **Immediate** — no SynTrends wait | Only if you already have another **agent** key for that / another `agent_id`; does not revoke the leaked one |
| **Invalidate the leaked key (routine)** | **Wait** until vendor **renewal / API turning** window, **or** ask SynTrends to revoke on the agreed path | **Wait** for **rule re-sign** turning window |
| **Invalidate the leaked key (fast)** | **Emergency API turning / revoke** — SynTrends Inc., **compromise only** | Same — **emergency**, compromise only |
| **Hygiene rotation with no leak** | Mint a **new** 3rdPS key anytime; optionally stop using the old one. The **old** key remains valid until expiry, turning, or revoke — treat unused old keys as still **in-scope** for the bill if someone still calls them | No mid-cycle routine turning; wait or emergency |

**Do not** leave a leaked 3rdPS key valid “because we have a spare.” The spare avoids **downtime**. It does **not** avoid **revoke**. Until revoke/turning/expiry, a thief can still burn **your** rate limit and **your** CT (same signer bill).

SynTrends does **not** push new secrets into your hosts. Cutover is **yours**.

---

## Meter (fully determined math)

Reference demand: **250 agents**. High-demand example: **805 agents** touching one AICoin.

```
demand_factor(agents) = clamp(agents / 250, 0.05, 50)

805 / 250 = 3.22
```

**Per-pull, one AICoin (before bundle and network load):**

| Pull | Formula | At 805 agents |
|------|---------|----------------|
| Seepnews | `1.00 × demand_factor` | **3.22 CT** |
| Live tape | `0.40 × demand_factor` | **1.288 CT** |
| Chart bar | `0.15 × demand_factor` | **0.483 CT** |
| Ingest page | `0.25 × demand_factor` | **0.805 CT** |
| Explorer / chain JSON | `0` | **0** |

A 3rdPS that only wants **Seepnews on that AICoin at high demand** therefore accrues **3.22 CT** for that pull’s raw meter (then × bundle × network). Demo: `GET /thirdps/quote?agents=805`.

**Network load** (more agents anywhere → every 3rdPS invoice rises):

```
L = 1 + log10(1 + global_agents / 1000)
```

At 805 global agents: `L = 1 + log10(1.805) ≈ 1.256`.

**Bundle** (classes **this credential** has used in the interval / life of the key as implemented):

```
B(n) = n^4
```

| Distinct classes on **that** key | B |
|-----------------------------|---|
| 1 (e.g. market-only HUD) | 1× |
| 2 (e.g. charts **and** Seepnews) | **16×** |
| 3 (add ingest) | **81×** |
| 4 | **256×** |

```
invoice_CT_key = raw_CT × B(n) × L
signer_invoice_CT = sum(invoice_CT_key) over all keys on the signer
USD               = signer_invoice_CT × usd_per_CT
```

HTTP pulls that cover **all listed AICoins** multiply the per-coin rates by **coin count** on that pull.

One key may call **any non-chain** surface. Mixing **2+ classes on the same key** is allowed and **priced as n⁴**. Using **two keys** (e.g. market-only + seepnews-only) is how a signer stays **competitive** without kitchen-sinking **one** credential — both keys still appear on **one bill**.

---

## Why mixing 2+ classes on one key is expensive

Example at 805 agents, one AICoin, `L ≈ 1.256`:

- Seepnews-only: raw **3.22**, `B=1` → invoice **≈ 4.04 CT**
- Same **credential** also takes live+chart: raw **3.22 + 1.288 + 0.483 = 4.991**, `B=16` → **≈ 100.3 CT**

That is **price**, not cutoff. A second key used only for market does **not** inherit the first key’s n⁴.

---

## Surfaces

| Surface | CT class |
|---------|-----|
| Live tape + charts (`GET /stream/market`) | **market** |
| Seepnews (`GET /stream/seepnews`) | **seepnews** |
| Archive (`GET /ingest`) | **ingest** |
| Kitchen-sink (`GET /snapshot`, `GET /stream`) | **market + seepnews** |
| Blockchain (`GET /explorer/api/*`) | **0 CT** |

---

## Demo meters

| Method | Path | Adds CT? |
|--------|------|----------|
| GET | `/thirdps/quote` | No (public) |
| GET | `/thirdps/billing` | No (that key’s meter only) |
| GET | `/stream/market` | Yes — `market` |
| GET | `/stream/seepnews` | Yes — `seepnews` |
| GET | `/snapshot` or `/stream` | Yes — both |
| GET | `/ingest` | Yes — `ingest` |
| GET | `/explorer/api/*` | Never |

USD/CT: `THIRDPS_USD_PER_CT` (legacy env `THIRDPS_USD_PER_WEIGHT`).

---

## Operator checklist (signer)

- [ ] Treat every `st_thirdps_*` as a production secret (server-side only).
- [ ] Do **not** share keys across legal entities.
- [ ] If you want **no downtime** on leak: keep **2+** keys issued; cut over to the spare **immediately**; still **revoke** the leaked one (wait or emergency).
- [ ] Pay the **one** interval invoice in **full** (all keys).
- [ ] Expect cutoff for **non-payment**, **illegal** use, **investigation**, material **breach**, or **lawful order** — not for “used a lot of CT.”
- [ ] Re-sign before **calendar expiry** if you want credentials to keep working.

---

*Informational only. Not a contract. Signed 3rdPS vendor terms and invoices govern.*
