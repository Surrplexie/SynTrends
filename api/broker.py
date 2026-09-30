"""Thread-safe pub/sub broker for STP SSE streams."""

from __future__ import annotations

import queue
import threading
from collections import defaultdict

from chain.stp import CHANNEL_ALL, CHANNEL_MARKET, CHANNEL_SEEPNEWS, line_channel


class STPStreamBroker:
    """Publishes STP lines to SSE subscribers by channel."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[queue.Queue[str | None]]] = defaultdict(list)
        self.history: list[str] = []
        self.max_history = 5000

    def publish(self, line: str) -> None:
        with self._lock:
            self.history.append(line)
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history :]

            ch = line_channel(line)
            targets = {CHANNEL_ALL, ch}
            for target in targets:
                dead: list[queue.Queue[str | None]] = []
                for sub in self._subscribers[target]:
                    try:
                        sub.put_nowait(line)
                    except queue.Full:
                        dead.append(sub)
                for sub in dead:
                    self._subscribers[target].remove(sub)

    def publish_many(self, lines: list[str]) -> None:
        for line in lines:
            self.publish(line)

    def subscribe(self, channel: str, maxsize: int = 2000) -> queue.Queue[str | None]:
        if channel not in (CHANNEL_MARKET, CHANNEL_SEEPNEWS, CHANNEL_ALL):
            raise ValueError(f"unknown channel: {channel}")
        q: queue.Queue[str | None] = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers[channel].append(q)
        return q

    def unsubscribe(self, channel: str, q: queue.Queue[str | None]) -> None:
        with self._lock:
            subs = self._subscribers.get(channel, [])
            if q in subs:
                subs.remove(q)

    def close_subscriber(self, channel: str, q: queue.Queue[str | None]) -> None:
        try:
            q.put_nowait(None)
        except queue.Full:
            pass
        self.unsubscribe(channel, q)

    def replay(self, channel: str, lines: list[str]) -> list[str]:
        if channel == CHANNEL_ALL:
            return list(lines)
        if channel == CHANNEL_MARKET:
            return [ln for ln in lines if line_channel(ln) == CHANNEL_MARKET]
        return [ln for ln in lines if line_channel(ln) == CHANNEL_SEEPNEWS]
