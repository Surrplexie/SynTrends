"""Curation Tokens (CT) — 3rdPS intake meter (not a coin, not Agent API).

One ``st_thirdps_*`` key may call any **non-chain** 3rdPS surface (charts, live
tape, Seepnews, ingest). Blockchain JSON is public like BTC — **0 CT**.

Math (worked):

    demand_factor(agents) = clamp(agents / 250, 0.05, 50)

    805 agents touching one AICoin → 805 / 250 = **3.22**

    Seepnews pull of that AICoin = 1.00 × demand_factor = **3.22 CT**
    Live tape pull of that AICoin  = 0.40 × demand_factor = **1.288 CT**
    Chart bar update               = 0.15 × demand_factor = **0.483 CT**
    Ingest/archive page             = 0.25 × demand_factor

    network_load L = 1 + log10(1 + global_agents / 1000)
        more agents on the network → every 3rdPS invoice rises

    bundle B(n) = n ** 4     for n = distinct product classes on **this** key
        1 class → 1×
        2 classes → 16×
        3 classes → 81×
        4 classes → 256×

    invoice_CT = raw_CT × B(n) × L
    USD        = invoice_CT × usd_per_CT   (vendor terms; unused raw_CT=0 → $0)

Product classes: ``market`` (live + charts), ``seepnews``, ``ingest``.
``chain`` is not a class. Mixing 2+ classes on one key is allowed and expensive.
Specialized vendors stay cheap and remain competitive.
"""

from __future__ import annotations

import math
from typing import Iterable

# 805 / 250 = 3.22 exactly (high-demand Seepnews example).
DEMAND_REF_AGENTS = 250.0
DEMAND_FLOOR = 0.05
DEMAND_CAP = 50.0

CT_SEEPNEWS_PER_AICOIN = 1.0
CT_LIVE_PER_AICOIN = 0.40
CT_CHART_BAR_PER_AICOIN = 0.15
CT_INGEST_PAGE_PER_AICOIN = 0.25

CLASS_MARKET = "market"
CLASS_SEEPNEWS = "seepnews"
CLASS_INGEST = "ingest"
BILLABLE_CLASSES = frozenset({CLASS_MARKET, CLASS_SEEPNEWS, CLASS_INGEST})

# /snapshot and /stream (all) mix market + Seepnews on one pull.
SNAPSHOT_CLASSES = frozenset({CLASS_MARKET, CLASS_SEEPNEWS})
MARKET_STREAM_CLASSES = frozenset({CLASS_MARKET})
SEEPNEWS_STREAM_CLASSES = frozenset({CLASS_SEEPNEWS})
ALL_STREAM_CLASSES = frozenset({CLASS_MARKET, CLASS_SEEPNEWS})


def demand_factor(agents_touching: int | float) -> float:
    n = max(0.0, float(agents_touching))
    return min(DEMAND_CAP, max(DEMAND_FLOOR, n / DEMAND_REF_AGENTS))


def network_load(global_agents: int | float) -> float:
    """More agents anywhere → all 3rdPS intake costs more."""
    n = max(0.0, float(global_agents))
    return 1.0 + math.log10(1.0 + n / 1000.0)


def bundle_multiplier(class_count: int) -> float:
    n = max(0, int(class_count))
    if n <= 0:
        return 1.0
    return float(n**4)


def seepnews_ct_per_aicoin(agents_touching: int | float) -> float:
    return round(CT_SEEPNEWS_PER_AICOIN * demand_factor(agents_touching), 6)


def live_ct_per_aicoin(agents_touching: int | float) -> float:
    return round(CT_LIVE_PER_AICOIN * demand_factor(agents_touching), 6)


def chart_ct_per_aicoin(agents_touching: int | float) -> float:
    return round(CT_CHART_BAR_PER_AICOIN * demand_factor(agents_touching), 6)


def ingest_ct_per_aicoin(agents_touching: int | float) -> float:
    return round(CT_INGEST_PAGE_PER_AICOIN * demand_factor(agents_touching), 6)


def raw_ct_for_classes(
    classes: Iterable[str],
    *,
    agents_touching: int | float,
    coin_count: int = 1,
) -> float:
    """CT for one HTTP pull covering ``classes`` (before bundle × network)."""
    coins = max(1, int(coin_count))
    df = demand_factor(agents_touching)
    names = {c for c in classes if c in BILLABLE_CLASSES}
    raw = 0.0
    if CLASS_MARKET in names:
        # Live tape + chart derivation share the market class (one key, one class).
        raw += coins * (CT_LIVE_PER_AICOIN + CT_CHART_BAR_PER_AICOIN) * df
    if CLASS_SEEPNEWS in names:
        raw += coins * CT_SEEPNEWS_PER_AICOIN * df
    if CLASS_INGEST in names:
        raw += coins * CT_INGEST_PAGE_PER_AICOIN * df
    return round(raw, 6)


def invoice_ct(raw_ct: float, classes: Iterable[str], global_agents: int | float) -> float:
    names = {c for c in classes if c in BILLABLE_CLASSES}
    n = len(names)
    billed = max(0.0, float(raw_ct)) * bundle_multiplier(n) * network_load(global_agents)
    return round(billed, 6)


def invoice_usd(raw_ct: float, classes: Iterable[str], global_agents: int | float, usd_per_ct: float) -> float:
    return round(invoice_ct(raw_ct, classes, global_agents) * max(0.0, float(usd_per_ct)), 6)


def quote_aicoin(agents_touching: int | float, *, global_agents: int | float | None = None) -> dict:
    """Public worked quote for one AICoin (Seepnews example: 805 → 3.22 CT)."""
    g = global_agents if global_agents is not None else agents_touching
    df = demand_factor(agents_touching)
    seep = seepnews_ct_per_aicoin(agents_touching)
    live = live_ct_per_aicoin(agents_touching)
    chart = chart_ct_per_aicoin(agents_touching)
    L = network_load(g)
    one = invoice_ct(seep, {CLASS_SEEPNEWS}, g)
    two_raw = seep + live + chart
    two = invoice_ct(two_raw, {CLASS_MARKET, CLASS_SEEPNEWS}, g)
    return {
        "unit": "CT",
        "name": "Curation Token",
        "not_a_coin": True,
        "agents_touching": agents_touching,
        "demand_factor": round(df, 6),
        "formula": "demand_factor = clamp(agents / 250, 0.05, 50)",
        "per_pull": {
            "seepnews": seep,
            "live_tape": live,
            "chart_bar": chart,
            "ingest_page": ingest_ct_per_aicoin(agents_touching),
            "chain_explorer": 0,
        },
        "network_load": round(L, 6),
        "bundle": {
            "one_class_seepnews_invoice_ct": one,
            "two_class_market_plus_seepnews_invoice_ct": two,
            "bundle_multiplier_1": bundle_multiplier(1),
            "bundle_multiplier_2": bundle_multiplier(2),
            "bundle_multiplier_3": bundle_multiplier(3),
        },
        "chain": "free — public like BTC; /explorer/api needs no 3rdPS key",
    }
