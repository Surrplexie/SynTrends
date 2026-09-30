"""Deterministic clock used throughout the demo so tests never depend on
real wall-clock sleeps. Production code would swap this for `time.time`.
"""

from __future__ import annotations


class ManualClock:
    """A callable clock you can advance manually.

    Every engine in this package accepts a `clock` callable (defaulting to
    `time.time`) instead of calling `time.time()` directly, so tests and the
    scripted demo can compress "2-4 weeks" of cooldown into a few simulated
    seconds and get fully deterministic, instant results.
    """

    def __init__(self, start: float = 0.0):
        self._t = float(start)

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> float:
        self._t += seconds
        return self._t
