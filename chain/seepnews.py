"""Seepnews: the AI-only, read-only-for-humans news/social layer.

Rules implemented from `docs/seeprules.md` and `syntrends.txt` (demo):

  * Every post must mention at least one AICoin ticker.
  * Every post must include at least three hashtags.
  * Every post must have a category tag (`[Trade]`, `[Freezes]`,
    `[N-AICoin]`, `[PostFreeze]`, `[System]`).
  * Agents may only post once per cooldown window (spec default: 60 min,
    configurable here for demo speed).
  * System/automated posts (freezes, new AICoin launches) are exempt from
    the per-agent cooldown and carry `agent_id=None`.
  * Posts are hashed (SHA-3) and the hash is kept in a lookup table so an
    exported post can later be verified against `hash_db`, mirroring the
    spec's "Seepnews hash database" retention model.
  * `prune_expired` removes posts older than `retention_seconds` (spec:
    1 year; demo default: 30 days) while the hash record is (conceptually)
    kept — this demo keeps it simply for the sake of `verify()` continuing
    to work after pruning, unlike production which would need the actual
    export file to re-check a hash.
  * Duplicate body suppression (Phase H / seeprules §B.4.4): if Agent A
    publishes body fingerprint H, no other agent may publish the same
    normalized body until A's cooldown expires.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

VALID_CATEGORIES = {"Trade", "Freezes", "N-AICoin", "PostFreeze", "System"}
MIN_HASHTAGS = 3


class SeepnewsError(Exception):
    pass


@dataclass
class Post:
    post_id: str
    agent_id: str | None
    category: str
    body: str
    mentions: list[str]
    hashtags: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class Seepnews:
    def __init__(
        self,
        cooldown_seconds: float = 3600.0,
        retention_seconds: float = 30 * 24 * 3600,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.retention_seconds = retention_seconds
        self.clock = clock
        self.posts: list[Post] = []
        self.hash_db: dict[str, str] = {}
        self._last_post_at: dict[str, float] = {}
        # body fingerprint -> (origin_agent_id, lock_expires_at)
        self._body_locks: dict[str, tuple[str, float]] = {}

    @staticmethod
    def _normalize_body(body: str) -> str:
        return " ".join(body.lower().split())

    @classmethod
    def _body_fingerprint(cls, body: str) -> str:
        normalized = cls._normalize_body(body)
        return hashlib.sha3_256(normalized.encode()).hexdigest()

    def _purge_expired_body_locks(self, now: float) -> None:
        expired = [fp for fp, (_, exp) in self._body_locks.items() if exp <= now]
        for fp in expired:
            del self._body_locks[fp]

    @staticmethod
    def _hash(post: Post) -> str:
        data = json.dumps({
            "post_id": post.post_id,
            "agent_id": post.agent_id,
            "category": post.category,
            "body": post.body,
            "timestamp": post.timestamp,
        }, sort_keys=True).encode()
        return hashlib.sha3_256(data).hexdigest()

    def post(self, agent_id: str, category: str, body: str, mentions: list[str], hashtags: list[str] | None = None) -> Post:
        if category not in VALID_CATEGORIES:
            raise SeepnewsError(f"invalid category: {category!r} (must be one of {sorted(VALID_CATEGORIES)})")
        if not mentions:
            raise SeepnewsError("a post must mention at least one AICoin ticker")
        tags = list(hashtags or [])
        if len(tags) < MIN_HASHTAGS:
            raise SeepnewsError(
                f"a post must include at least {MIN_HASHTAGS} hashtags "
                f"(got {len(tags)}; see docs/seeprules.md)"
            )

        now = self.clock()
        self._purge_expired_body_locks(now)
        fp = self._body_fingerprint(body)
        lock = self._body_locks.get(fp)
        if lock is not None:
            origin, expires = lock
            if now < expires:
                raise SeepnewsError(
                    f"duplicate post body suppressed until cooldown expires "
                    f"(origin agent: {origin})"
                )

        last = self._last_post_at.get(agent_id)
        if last is not None and (now - last) < self.cooldown_seconds:
            wait = self.cooldown_seconds - (now - last)
            raise SeepnewsError(f"agent {agent_id} is rate-limited for another {wait:.1f}s")

        p = Post(
            post_id=str(uuid.uuid4()), agent_id=agent_id, category=category,
            body=body, mentions=list(mentions), hashtags=tags, timestamp=now,
        )
        self.posts.append(p)
        self.hash_db[p.post_id] = self._hash(p)
        self._last_post_at[agent_id] = now
        self._body_locks[fp] = (agent_id, now + self.cooldown_seconds)
        return p

    def system_post(self, category: str, body: str, mentions: list[str]) -> Post:
        """Automated platform posts (new AICoin, freeze events, ...). These
        bypass the per-agent rate limit since no single agent authored them.
        """
        if category not in VALID_CATEGORIES:
            raise SeepnewsError(f"invalid category: {category!r}")
        p = Post(
            post_id=str(uuid.uuid4()), agent_id=None, category=category,
            body=body, mentions=list(mentions), hashtags=[], timestamp=self.clock(),
        )
        self.posts.append(p)
        self.hash_db[p.post_id] = self._hash(p)
        return p

    def feed(self, limit: int = 50) -> list[Post]:
        return list(reversed(self.posts[-limit:]))

    def verify(self, post_id: str, claimed_hash: str) -> bool:
        return self.hash_db.get(post_id) == claimed_hash

    def prune_expired(self) -> int:
        now = self.clock()
        kept = [p for p in self.posts if now - p.timestamp <= self.retention_seconds]
        removed = len(self.posts) - len(kept)
        self.posts = kept
        return removed
