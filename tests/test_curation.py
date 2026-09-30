"""Curation Token math — 805 agents → 3.22 CT Seepnews pull."""

from __future__ import annotations

from api.curation import (
    CLASS_MARKET,
    CLASS_SEEPNEWS,
    bundle_multiplier,
    demand_factor,
    invoice_ct,
    seepnews_ct_per_aicoin,
)


def test_seepnews_high_demand_is_322_ct():
    assert demand_factor(805) == 3.22
    assert seepnews_ct_per_aicoin(805) == 3.22


def test_bundle_n4():
    assert bundle_multiplier(1) == 1
    assert bundle_multiplier(2) == 16
    assert bundle_multiplier(3) == 81


def test_two_classes_invoice_far_above_one():
    seep = seepnews_ct_per_aicoin(805)
    one = invoice_ct(seep, {CLASS_SEEPNEWS}, 805)
    two = invoice_ct(seep + 1.288 + 0.483, {CLASS_MARKET, CLASS_SEEPNEWS}, 805)
    assert two > one * 10
