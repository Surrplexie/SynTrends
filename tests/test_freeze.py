"""Reproduces the three worked freeze examples from syntrends.txt exactly,
starting at $0.01, plus buy-rejection behavior while frozen.
"""

import pytest

from chain.clock import ManualClock
from chain.freeze import FreezeEngine, FreezeState


def test_example_1_two_freezes_then_loss_refreeze():
    clock = ManualClock(0.0)
    fe = FreezeEngine(start_price=0.01, cooldown_seconds=1.0, clock=clock)

    assert fe.tick(0.05) == FreezeState.GROWING

    state = fe.tick(0.1124)  # +1024%
    assert state == FreezeState.FROZEN
    assert fe.ceiling == pytest.approx(0.1124)
    assert not fe.is_buy_allowed(0.15)
    assert fe.is_buy_allowed(0.1124)

    clock.advance(2.0)  # cooldown ends
    assert fe.tick(0.1124) == FreezeState.GROWING

    state = fe.tick(0.256272)  # +128% over 0.1124
    assert state == FreezeState.FROZEN
    assert fe.ceiling == pytest.approx(0.256272)

    clock.advance(2.0)
    assert fe.tick(0.256272) == FreezeState.GROWING

    # 75% drop from the last freeze (0.256272 * 0.25 = 0.064068)
    state = fe.tick(0.064068)
    assert state == FreezeState.WATCHING_DROP

    # 8% rebound from the low -> new freeze
    state = fe.tick(0.06919344)
    assert state == FreezeState.FROZEN
    assert fe.ceiling == pytest.approx(0.06919344)
    assert fe.freeze_history == pytest.approx([0.1124, 0.256272, 0.06919344])


def test_example_2_pre_1024_50pct_drop_10pct_rebound():
    clock = ManualClock(0.0)
    fe = FreezeEngine(start_price=0.01, cooldown_seconds=1.0, clock=clock)

    state = fe.tick(0.005)  # 50% loss from start, never reached 1024%
    assert state == FreezeState.WATCHING_DROP

    state = fe.tick(0.0055)  # 10% rebound
    assert state == FreezeState.FROZEN
    assert fe.ceiling == pytest.approx(0.0055)
    assert fe.freeze_history == pytest.approx([0.0055])


def test_example_3_repeated_128pct_steps_without_losses():
    clock = ManualClock(0.0)
    fe = FreezeEngine(start_price=0.01, cooldown_seconds=1.0, clock=clock)

    assert fe.tick(0.1124) == FreezeState.FROZEN
    clock.advance(2.0)
    fe.tick(0.1124)

    assert fe.tick(0.256272) == FreezeState.FROZEN
    clock.advance(2.0)
    fe.tick(0.256272)

    state = fe.tick(0.58430016)  # 2nd +128% step
    assert state == FreezeState.FROZEN
    assert fe.ceiling == pytest.approx(0.58430016)
    assert fe.freeze_history == pytest.approx([0.1124, 0.256272, 0.58430016])


def test_buy_allowed_only_when_not_frozen():
    clock = ManualClock(0.0)
    fe = FreezeEngine(start_price=1.0, cooldown_seconds=5.0, clock=clock)

    assert fe.is_buy_allowed(1000.0)  # growing: unrestricted

    fe.tick(11.24)
    assert fe.state == FreezeState.FROZEN
    assert fe.is_buy_allowed(11.24)
    assert not fe.is_buy_allowed(11.25)

    clock.advance(6.0)
    fe.tick(11.24)
    assert fe.state == FreezeState.GROWING
    assert fe.is_buy_allowed(50.0)


def test_upcoming_ceiling_before_and_after_first_freeze():
    clock = ManualClock(0.0)
    fe = FreezeEngine(start_price=0.01, cooldown_seconds=1.0, clock=clock)
    assert fe.upcoming_ceiling() == pytest.approx(0.1124)

    fe.tick(0.1124)
    clock.advance(2.0)
    fe.tick(0.1124)
    assert fe.upcoming_ceiling() == pytest.approx(0.256272)


def test_cooldown_still_active_blocks_further_state_changes():
    clock = ManualClock(0.0)
    fe = FreezeEngine(start_price=1.0, cooldown_seconds=10.0, clock=clock)
    fe.tick(11.24)
    assert fe.state == FreezeState.FROZEN

    clock.advance(5.0)  # cooldown not yet over
    state = fe.tick(999.0)  # even a huge price shouldn't unfreeze early
    assert state == FreezeState.FROZEN
    assert fe.ceiling == pytest.approx(11.24)
