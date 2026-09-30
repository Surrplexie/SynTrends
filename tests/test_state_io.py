"""Tests for chain state serialization (Phase E)."""

from __future__ import annotations

from chain.clock import ManualClock
from chain.engine import SynTrendsDemo
from chain.state_io import dump_demo, load_demo


def test_dump_load_roundtrip_preserves_agents_and_coins():
    clock = ManualClock(start=1_700_000_000.0)
    demo = SynTrendsDemo(clock=clock)
    demo.register_agent("founder")
    demo.register_agent("trader")
    demo.deposit_fiat("founder", 5000)
    demo.deposit_fiat("trader", 5000)
    coin = demo.launch_aicoin("GEM", "Gem", "founder", 10_000, 1000, 0.10)
    demo.buy("trader", coin.coin_id, 100)
    demo.mine_block()

    payload = dump_demo(demo, clock)
    clock2 = ManualClock(start=1_700_000_000.0)
    restored = load_demo(payload, clock2)

    assert restored.agents == demo.agents
    assert set(restored.coins.keys()) == set(demo.coins.keys())
    assert restored.wallets.fiat_balance("trader") == demo.wallets.fiat_balance("trader")
    assert len(restored.chain.chain) == len(demo.chain.chain)
    assert restored.chain.is_valid()


def test_load_advances_clock_to_saved_time():
    clock = ManualClock(start=100.0)
    demo = SynTrendsDemo(clock=clock)
    demo.register_agent("a")
    clock.advance(50.0)
    payload = dump_demo(demo, clock)

    clock2 = ManualClock(start=100.0)
    load_demo(payload, clock2)
    assert clock2() >= 150.0
