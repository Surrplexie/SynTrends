import pytest

from chain.clock import ManualClock
from chain.fees import FEE_CAP, FEE_FLOOR, FeeEngine


def test_fee_starts_at_floor():
    fe = FeeEngine(clock=ManualClock(0.0))
    assert fe.current_fee("a1", "c1") == FEE_FLOOR


def test_fee_grows_with_each_transaction():
    clock = ManualClock(0.0)
    fe = FeeEngine(clock=clock)
    charged = [fe.record_transaction("a1", "c1") for _ in range(5)]
    assert charged == sorted(charged)
    assert charged[0] == FEE_FLOOR
    assert charged[-1] > FEE_FLOOR


def test_fee_decays_over_time():
    clock = ManualClock(0.0)
    fe = FeeEngine(clock=clock)
    for _ in range(50):
        fe.record_transaction("a1", "c1")
    high = fe.current_fee("a1", "c1")
    clock.advance(3600 * 5)  # 5 hours of inactivity
    lower = fe.current_fee("a1", "c1")
    assert lower < high


def test_fee_never_drops_below_floor():
    clock = ManualClock(0.0)
    fe = FeeEngine(clock=clock)
    fe.record_transaction("a1", "c1")
    clock.advance(3600 * 24 * 30)  # a month of inactivity
    assert fe.current_fee("a1", "c1") == FEE_FLOOR


def test_fee_caps_at_max():
    clock = ManualClock(0.0)
    fe = FeeEngine(clock=clock)
    for _ in range(20_000):
        fe.record_transaction("a1", "c1")
    assert fe.current_fee("a1", "c1") <= FEE_CAP


def test_fee_isolated_per_agent_and_coin():
    clock = ManualClock(0.0)
    fe = FeeEngine(clock=clock)
    for _ in range(50):
        fe.record_transaction("a1", "coinA")
    assert fe.current_fee("a1", "coinB") == FEE_FLOOR
    assert fe.current_fee("a2", "coinA") == FEE_FLOOR


def test_post_freeze_reset_within_band():
    clock = ManualClock(0.0)
    fe = FeeEngine(clock=clock)
    for _ in range(5000):
        if fe.current_fee("a1", "c1") >= 2.0:
            break
        fe.record_transaction("a1", "c1")
    fee_before = fe.current_fee("a1", "c1")
    assert 2.0 <= fee_before <= 18.0

    fe.reset_after_post_freeze_order("a1", "c1")
    assert fe.current_fee("a1", "c1") == pytest.approx(1.0)


def test_post_freeze_reset_ignored_outside_band():
    clock = ManualClock(0.0)
    fe = FeeEngine(clock=clock)
    # still at the floor (0.01%), well below the 2%-18% reset band
    fe.reset_after_post_freeze_order("a1", "c1")
    assert fe.current_fee("a1", "c1") == FEE_FLOOR
