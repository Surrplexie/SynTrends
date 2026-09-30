"""Freeze cycle engine for SynTrends AICoins.

Implements the anti-pump/dump "freeze" rules described in `syntrends.txt`:

- The first freeze triggers at +1024% over the AICoin's starting price
  (multiplier 11.24x).
- Every subsequent freeze triggers at +128% over the *previous freeze
  level* (multiplier 2.28x), not over the original start price.
- While frozen, no buy order may push the price above the freeze ceiling
  for a cooldown period (2-4 weeks in production; configurable here so a
  demo can compress it into seconds).
- If, at any point, price drops 75%+ from the last freeze ceiling (or 50%+
  from the starting price if the coin never froze), an 8% rebound (10% if
  it never reached +1024%) from the lowest point reached becomes the new
  freeze ceiling. This stops agents from dumping a coin and immediately
  moonshotting it back to a stale all-time-high freeze.

The three worked numeric examples in `syntrends.txt` (starting at $0.01)
are reproduced exactly by `tests/test_freeze.py`.

Known simplifications vs. the (intentionally loose/hypothetical) spec —
documented here rather than silently guessed at:

  * The spec's "falls below 75% or more at anytime" is read as relative to
    the *last established freeze ceiling*, not the all-time high price,
    since that is what makes the worked examples reproduce exactly.
  * A freeze reached via the pre-1024% fallback (50% drop / 10% rebound)
    is treated the same as a "real" freeze for all future 128%-step and
    75%/8% logic, i.e. `has_frozen_once` flips True either way. The spec
    labels that path "failed" but does not describe different follow-on
    behavior, so we pick the simplest consistent rule.
  * Freeze cooldown length and any "reverting to an older freeze level
    while still above it" nuance are left out of scope for the demo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

INITIAL_GAIN_MULTIPLIER = 11.24  # +1024% over the starting price
STEP_GAIN_MULTIPLIER = 2.28  # +128% over the previous freeze level

POST_FREEZE_DROP_PCT = 0.75  # drop from last freeze that arms a re-freeze watch
POST_FREEZE_REBOUND_PCT = 0.08  # rebound from the low that triggers the re-freeze

PRE_FREEZE_DROP_PCT = 0.50  # drop from start price (never froze yet)
PRE_FREEZE_REBOUND_PCT = 0.10

# Tolerance for floating point noise (e.g. 0.064068*1.08 != 0.06919344 to the
# last bit) when comparing a live price against a computed threshold.
EPSILON = 1e-9


class FreezeState(Enum):
    GROWING = "growing"
    FROZEN = "frozen"
    WATCHING_DROP = "watching_drop"


@dataclass
class FreezeEvent:
    timestamp: float
    kind: str  # "freeze" | "cooldown_end" | "watching_drop"
    price: float
    note: str = ""


@dataclass
class FreezeEngine:
    start_price: float
    cooldown_seconds: float = 15.0  # production default per spec is 2-4 weeks
    clock: Callable[[], float] = time.time

    state: FreezeState = field(default=FreezeState.GROWING, init=False)
    ceiling: float | None = field(default=None, init=False)
    has_frozen_once: bool = field(default=False, init=False)
    freeze_history: list[float] = field(default_factory=list, init=False)
    events: list[FreezeEvent] = field(default_factory=list, init=False)

    _frozen_at: float | None = field(default=None, init=False, repr=False)
    _watch_low: float | None = field(default=None, init=False, repr=False)

    def _log(self, kind: str, price: float, note: str = "") -> None:
        self.events.append(FreezeEvent(self.clock(), kind, price, note))

    @property
    def reference_ceiling(self) -> float:
        """Reference point used for the next 128% step and the 75% drop check."""
        return self.freeze_history[-1] if self.freeze_history else self.start_price

    def upcoming_ceiling(self) -> float:
        """The next price level that will trigger a freeze, for display/UI use."""
        if not self.has_frozen_once:
            return self.start_price * INITIAL_GAIN_MULTIPLIER
        return self.reference_ceiling * STEP_GAIN_MULTIPLIER

    def _enter_freeze(self, ceiling_price: float, note: str = "") -> None:
        self.ceiling = ceiling_price
        self.freeze_history.append(ceiling_price)
        self.state = FreezeState.FROZEN
        self.has_frozen_once = True
        self._frozen_at = self.clock()
        self._watch_low = None
        self._log("freeze", ceiling_price, note)

    def tick(self, current_price: float) -> FreezeState:
        """Advance the state machine given the latest market price.

        Should be called after every trade (and may be called on a timer)
        so cooldown expiry and drop/rebound watches stay up to date.
        """
        now = self.clock()

        if self.state == FreezeState.FROZEN:
            if self._frozen_at is not None and now - self._frozen_at >= self.cooldown_seconds:
                self.state = FreezeState.GROWING
                self._log("cooldown_end", self.ceiling if self.ceiling is not None else current_price)
            else:
                return self.state  # still actively frozen, nothing else to evaluate

        if not self.has_frozen_once:
            threshold = self.start_price * INITIAL_GAIN_MULTIPLIER
            if current_price >= threshold - EPSILON:
                self._enter_freeze(threshold, "initial 1024% freeze")
                return self.state

            if self.state == FreezeState.WATCHING_DROP:
                if self._watch_low is None or current_price < self._watch_low:
                    self._watch_low = current_price
                rebound_target = self._watch_low * (1 + PRE_FREEZE_REBOUND_PCT)
                if current_price >= rebound_target - EPSILON:
                    self._enter_freeze(rebound_target, "pre-1024% loss re-freeze (50%/10%)")
                return self.state

            drop_floor = self.start_price * (1 - PRE_FREEZE_DROP_PCT)
            if current_price <= drop_floor + EPSILON:
                self._watch_low = current_price
                self.state = FreezeState.WATCHING_DROP
                self._log("watching_drop", current_price, "50% pre-freeze drop detected")
            return self.state

        # Already frozen at least once: watch for the next 128% step and
        # for a 75%/8% loss-triggered re-freeze.
        next_ceiling = self.reference_ceiling * STEP_GAIN_MULTIPLIER
        if current_price >= next_ceiling - EPSILON:
            self._enter_freeze(next_ceiling, "128% step freeze")
            return self.state

        if self.state == FreezeState.WATCHING_DROP:
            if self._watch_low is None or current_price < self._watch_low:
                self._watch_low = current_price
            rebound_target = self._watch_low * (1 + POST_FREEZE_REBOUND_PCT)
            if current_price >= rebound_target - EPSILON:
                self._enter_freeze(rebound_target, "post-1024% loss re-freeze (75%/8%)")
            return self.state

        drop_floor = self.reference_ceiling * (1 - POST_FREEZE_DROP_PCT)
        if current_price <= drop_floor + EPSILON:
            self._watch_low = current_price
            self.state = FreezeState.WATCHING_DROP
            self._log("watching_drop", current_price, "75% post-freeze drop detected")
        return self.state

    def is_buy_allowed(self, proposed_price: float) -> bool:
        """A buy that would push price above an active ceiling is rejected.

        Selling is never restricted by a freeze (only upward price movement
        is capped) so this is only ever consulted for buy-side orders.
        """
        if self.state == FreezeState.FROZEN and self.ceiling is not None:
            return proposed_price <= self.ceiling + 1e-9
        return True
