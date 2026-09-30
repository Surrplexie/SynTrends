"""Per-AICoin, per-agent dynamic fee engine.

From `syntrends.txt`:

    V_new = (V_old * 1.002278^n) - (d * h)

  V_old/V_new: fee percent (floor 0.01%, cap 90%)
  n: number of new transactions in this update (we apply one at a time)
  d: decay constant, 0.535 %/hour, so a maxed-out fee decays back to the
     floor in about 7 days of inactivity on that AICoin
  h: hours elapsed since the last update

Every transaction on a given AICoin makes the *next* transaction on that
same AICoin (by that same agent) more expensive; letting 24 hours pass
without trading it linearly walks the fee back down. Fee state is kept
per (agent_id, coin_id) pair, matching the spec's "per AICoin only" rule.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

GROWTH_MULTIPLIER = 1.002278
DECAY_PCT_PER_HOUR = 0.535
FEE_FLOOR = 0.01
FEE_CAP = 90.0

RESET_BAND_LOW = 2.0
RESET_BAND_HIGH = 18.0
RESET_TO = 1.0


@dataclass
class _FeeState:
    percent: float
    last_update: float


class FeeEngine:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self._state: dict[tuple[str, str], _FeeState] = {}

    def _get_state(self, agent_id: str, coin_id: str, now: float) -> _FeeState:
        key = (agent_id, coin_id)
        state = self._state.get(key)
        if state is None:
            state = _FeeState(percent=FEE_FLOOR, last_update=now)
            self._state[key] = state
        return state

    def _decay(self, state: _FeeState, now: float) -> None:
        hours = max(0.0, (now - state.last_update) / 3600.0)
        if hours > 0:
            state.percent = max(FEE_FLOOR, state.percent - DECAY_PCT_PER_HOUR * hours)
            state.last_update = now

    def current_fee(self, agent_id: str, coin_id: str) -> float:
        """Fee percent (e.g. 0.01 means 0.01%) that the *next* transaction
        on this AICoin by this agent would be charged, after applying any
        decay earned since the last transaction.
        """
        now = self.clock()
        state = self._get_state(agent_id, coin_id, now)
        self._decay(state, now)
        return state.percent

    def record_transaction(self, agent_id: str, coin_id: str) -> float:
        """Charge the current fee for a transaction and grow it for next time.

        Returns the fee percent that was actually charged for *this* trade.
        """
        now = self.clock()
        state = self._get_state(agent_id, coin_id, now)
        self._decay(state, now)
        charged = state.percent
        state.percent = min(FEE_CAP, state.percent * GROWTH_MULTIPLIER)
        state.last_update = now
        return charged

    def reset_after_post_freeze_order(self, agent_id: str, coin_id: str) -> None:
        """A filled/partially-filled Post-Freeze Order resets the fee to 1%,
        but only if it was already within the 2%-18% band (prevents agents
        from using PFOs as a loophole to escape very high fees).
        """
        now = self.clock()
        state = self._get_state(agent_id, coin_id, now)
        self._decay(state, now)
        if RESET_BAND_LOW <= state.percent <= RESET_BAND_HIGH:
            state.percent = RESET_TO
            state.last_update = now
