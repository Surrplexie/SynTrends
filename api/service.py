"""SynTrends HTTP API service: demo engine + STP emitter + stream broker."""

from __future__ import annotations

import threading
import time

from chain.aicoin import AICoinError
from chain.clock import ManualClock
from chain.engine import SynTrendsDemo
from chain.freeze import FreezeState
from chain.node import ChainNode
from chain.orders import OrderError
from chain.seepnews import SeepnewsError
from chain.stp import (
    STPEmitter,
    encode_error,
    encode_seepnews,
    filter_snapshot_lines,
    snapshot_from_lines,
)

from .agent_pause import AgentPauseError, AgentPauseRegistry
from .auth import (
    APIKey,
    AuthError,
    KeyKind,
    KeyStore,
    is_agent_key,
    is_thirdps_key,
)
from .curation import (
    BILLABLE_CLASSES,
    bundle_multiplier,
    invoice_ct,
    network_load,
    quote_aicoin,
    raw_ct_for_classes,
)
from .broker import STPStreamBroker
from .config import Settings
from .kyc_provider import KYCProvider, create_kyc_provider
from .owners import KYCError, Owner, OwnerError, OwnerRegistry
from .persistence import Persistence
from .seeprules import ATTESTATION_TEXT, SEEPRULES_VERSION, SeeprulesRegistry
from .syntrendrules import SYNTRENDRULES_VERSION, SyntrendrulesRegistry


class RateLimitError(Exception):
    pass


class WriteForbiddenError(Exception):
    pass


class FaucetError(Exception):
    pass


class SandboxDepositError(Exception):
    """POST /agent/deposit is not allowed on this network."""


class SynTrendsAPIService:
    """Thread-safe facade used by FastAPI routes."""

    def __init__(
        self,
        demo: SynTrendsDemo | None = None,
        clock: ManualClock | None = None,
        license_rate_limit_per_minute: int | None = None,
        thirdps_rate_limit_per_minute: int | None = None,
        *,
        require_owner_kyc: bool = False,
        persistence: Persistence | None = None,
        settings: Settings | None = None,
        kyc_provider: KYCProvider | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.clock = clock or ManualClock(start=1_700_000_000.0)
        self.node = ChainNode(
            demo=demo,
            clock=self.clock,
            network=self.settings.network_name,
        )
        self.demo = self.node.demo
        self.emitter = STPEmitter(self.demo)
        self.broker = STPStreamBroker()
        self.keys = KeyStore()
        self.owners = OwnerRegistry(session_ttl_seconds=self.settings.owner_session_ttl_seconds)
        self.seeprules = SeeprulesRegistry()
        self.syntrendrules = SyntrendrulesRegistry()
        self.agent_pause = AgentPauseRegistry()
        self.require_owner_kyc = require_owner_kyc
        self.persistence = persistence
        self.kyc = kyc_provider or create_kyc_provider(self.settings)
        self._lock = threading.RLock()
        self._started_at = time.time()
        self._thirdps_rate_limit = (
            thirdps_rate_limit_per_minute
            if thirdps_rate_limit_per_minute is not None
            else license_rate_limit_per_minute
            if license_rate_limit_per_minute is not None
            else self.settings.thirdps_rate_limit_per_minute
        )
        self._agent_write_rate_limit = self.settings.agent_write_rate_limit_per_minute
        self._thirdps_hits: dict[str, list[float]] = {}
        self._agent_write_hits: dict[str, list[float]] = {}
        self._faucet_last: dict[str, float] = {}

        # Demo keys (overwritten if seed_demo() / seed_testnet() runs)
        self._agent_key = self.keys.issue_agent_key("agent-demo", "demo agent")
        self._thirdps_key = self.keys.issue_thirdps_key("demo chart vendor")
        self.seeprules.accept_agent("agent-demo")
        self.syntrendrules.accept_agent("agent-demo")

    @property
    def demo_agent_key(self) -> str:
        return self._agent_key.token

    @property
    def demo_thirdps_key(self) -> str:
        return self._thirdps_key.token

    @property
    def demo_license_key(self) -> str:
        """Deprecated alias — same as :attr:`demo_thirdps_key` (3rdPS API, not Agent API)."""
        return self._thirdps_key.token

    def export_snapshot(self) -> dict:
        return {
            "demo": self.node.export_state(),
            "owners": self.owners.export_state(),
            "keys": self.keys.export_state(),
            "faucet_last": dict(self._faucet_last),
            "seeprules": self.seeprules.export_state(),
            "syntrendrules": self.syntrendrules.export_state(),
            "agent_pause": self.agent_pause.export_state(),
        }

    def import_snapshot(self, data: dict) -> None:
        self.node.import_state(data["demo"])
        self.demo = self.node.demo
        self.emitter = STPEmitter(self.demo)
        self.owners.import_state(data.get("owners", {}))
        self.keys.import_state(data.get("keys", []))
        self._faucet_last = dict(data.get("faucet_last", {}))
        self.seeprules.import_state(data.get("seeprules", {}))
        self.syntrendrules.import_state(data.get("syntrendrules", {}))
        self.agent_pause.import_state(data.get("agent_pause", {}))
        agent = self.keys.first_agent_key()
        thirdps_key = self.keys.first_thirdps_key()
        if agent:
            self._agent_key = agent
        if thirdps_key:
            self._thirdps_key = thirdps_key

    def persist(self) -> None:
        if self.persistence and self.persistence.enabled:
            self.persistence.save(self.export_snapshot())

    def load_or_seed(self) -> dict[str, str | bool]:
        with self._lock:
            if self.persistence and self.persistence.enabled:
                snap = self.persistence.load()
                if snap:
                    self.import_snapshot(snap)
                    return {
                        "agent_key": self.demo_agent_key,
                        "thirdps_key": self.demo_thirdps_key,
                        "license_key": self.demo_thirdps_key,
                        "restored": True,
                    }
            result = self.seed_testnet() if self.settings.is_testnet else self.seed_demo()
            result["restored"] = False
            return result

    def status(self) -> dict:
        with self._lock:
            base = self.node.status_dict()
            persistence_meta: dict = {"enabled": False, "backend": None, "has_snapshot": False, "updated_at": None}
            persistence_ok = True
            if self.persistence is not None:
                persistence_ok = self.persistence.ping()
                persistence_meta = self.persistence.snapshot_meta()
            base.update({
                "env": self.settings.env,
                "network": self.settings.network_name,
                "protocol_version": self.settings.protocol_version,
                "uptime_seconds": round(time.time() - self._started_at, 1),
                "faucet_enabled": self.settings.faucet_allowed,
                "require_owner_kyc": self.require_owner_kyc,
                "kyc_provider": self.kyc.name,
                "agents_paused": self.agent_pause.paused_count(),
                "persistence": persistence_meta,
                "persistence_ok": persistence_ok,
                "ready": persistence_ok,
            })
            return base

    def readiness(self) -> tuple[dict, int]:
        """Return (body, http_status). 503 when persistence is configured but unreachable."""
        body = self.status()
        code = 200 if body.get("ready") else 503
        return body, code

    def faucet_info(self) -> dict:
        return {
            "enabled": self.settings.faucet_allowed,
            "amount": self.settings.faucet_amount,
            "cooldown_seconds": self.settings.faucet_cooldown_seconds,
            "note": "Simulated testnet fiat — no monetary value.",
        }

    def claim_faucet(self, key: APIKey) -> str:
        if not self.settings.faucet_allowed:
            raise FaucetError("faucet is disabled on this network")
        if key.kind != KeyKind.AGENT or not key.agent_id:
            raise FaucetError("faucet requires an agent API key bound to an agent_id")
        agent_id = key.agent_id
        now = time.time()
        last = self._faucet_last.get(agent_id, 0.0)
        if now - last < self.settings.faucet_cooldown_seconds:
            remaining = int(self.settings.faucet_cooldown_seconds - (now - last))
            raise FaucetError(f"faucet cooldown active — try again in {remaining}s")
        self._assert_agent_writes_allowed(agent_id)
        with self._lock:
            self.demo.deposit_fiat(agent_id, self.settings.faucet_amount)
            lines = self.emitter.on_deposit(agent_id, self.settings.faucet_amount)
            self._faucet_last[agent_id] = now
            return self._emit_and_publish(lines)

    def revoke_agent_key(self, owner: Owner, token: str) -> None:
        key = self.keys.lookup(token)
        if key.owner_id and key.owner_id != owner.owner_id:
            raise AuthError("this key does not belong to your account")
        if key.agent_id and key.agent_id not in owner.agent_ids:
            raise AuthError("this key is not linked to your agents")
        self.keys.revoke(token)
        self.persist()

    def _require_owner_agent(self, owner: Owner, agent_id: str) -> str:
        agent_id = agent_id.strip()
        if agent_id not in owner.agent_ids:
            raise OwnerError("agent is not linked to your account")
        return agent_id

    def pause_agent(self, owner: Owner, agent_id: str) -> dict:
        agent_id = self._require_owner_agent(owner, agent_id)
        with self._lock:
            self.agent_pause.pause(owner.owner_id, agent_id)
            self.persist()
            return self.agent_pause.public_status(agent_id)

    def resume_agent(self, owner: Owner, agent_id: str, *, gradual_seconds: float = 0) -> dict:
        agent_id = self._require_owner_agent(owner, agent_id)
        with self._lock:
            self.agent_pause.resume(owner.owner_id, agent_id, gradual_seconds=gradual_seconds)
            self.persist()
            return self.agent_pause.public_status(agent_id)

    def agent_pause_status_for_owner(self, owner: Owner) -> list[dict]:
        return [self.agent_pause.public_status(aid) for aid in owner.agent_ids]

    def _assert_agent_writes_allowed(self, agent_id: str) -> None:
        blocked, msg = self.agent_pause.write_block_reason(agent_id)
        if blocked:
            raise AgentPauseError(msg)

    def _pause_reject_line(self, agent_id: str) -> str | None:
        blocked, msg = self.agent_pause.write_block_reason(agent_id)
        if not blocked:
            return None
        return encode_error("AGENT_PAUSED", msg)

    def _publish_lines(self, lines: list[str]) -> None:
        self.broker.publish_many(lines)

    def _emit_and_publish(self, lines: list[str]) -> str:
        self._publish_lines(lines)
        self.persist()
        return "\n".join(lines)

    def _check_rate_limit(self, key: APIKey, *, write: bool = False) -> None:
        now = time.time()
        window_start = now - 60.0
        if is_thirdps_key(key):
            hits = self._thirdps_hits.setdefault(key.token, [])
            cap = self._thirdps_rate_limit
        elif write and is_agent_key(key):
            hits = self._agent_write_hits.setdefault(key.token, [])
            cap = self._agent_write_rate_limit
        else:
            return
        hits[:] = [t for t in hits if t >= window_start]
        if len(hits) >= cap:
            raise RateLimitError(f"rate limit exceeded ({cap} req/min)")
        hits.append(now)

    def _record_thirdps_ct(self, key: APIKey, raw_ct: float) -> None:
        if not is_thirdps_key(key) or raw_ct <= 0:
            return
        key.usage_weight = round(key.usage_weight + raw_ct, 6)

    def authenticate(
        self,
        token: str | None,
        *,
        write: bool = False,
        product_classes: frozenset[str] | None = None,
    ) -> APIKey:
        key = self.keys.lookup(token)
        if write and not self.keys.allows_write(key):
            raise WriteForbiddenError(
                "3rdPS API keys are read-only; trading and Seepnews writes require an "
                "Agent API key (st_agent_*) from the owner portal"
            )
        self._check_rate_limit(key, write=write)
        if is_thirdps_key(key) and not write and product_classes:
            names = frozenset(c for c in product_classes if c in BILLABLE_CLASSES)
            if names:
                n_agents = len(self.demo.agents)
                n_coins = max(1, len(self.demo.coins))
                raw = raw_ct_for_classes(
                    names,
                    agents_touching=n_agents,
                    coin_count=n_coins,
                )
                key.product_classes.update(names)
                self._record_thirdps_ct(key, raw)
        return key

    def thirdps_billing(self, key: APIKey) -> dict:
        usd = self.settings.thirdps_usd_per_ct
        n_agents = len(self.demo.agents)
        classes = sorted(key.product_classes)
        n_cls = len(key.product_classes)
        billed = invoice_ct(key.usage_weight, key.product_classes, n_agents)
        return {
            "api_class": "thirdps",
            "issuance_fee": 0,
            "billing_model": "curation_tokens",
            "unit": "CT",
            "name": "Curation Token",
            "not_a_coin": True,
            "raw_ct": key.usage_weight,
            "usage_weight": key.usage_weight,
            "product_classes": classes,
            "bundle_multiplier": bundle_multiplier(n_cls),
            "network_agents": n_agents,
            "network_load": round(network_load(n_agents), 6),
            "invoice_ct": billed,
            "usd_per_ct": usd,
            "usd_per_weight": usd,
            "amount_due": key.invoice_amount(usd, global_agents=n_agents),
            "expires_at": key.expires_at,
            "created_at": key.created_at,
            "label": key.label,
            "chain": "free — /explorer/api needs no 3rdPS key",
            "note": (
                "Issuance is free. Calendar expiry still applies. Unused keys owe $0. "
                "One key covers all non-chain 3rdPS surfaces. Mixing 2+ product classes "
                "on this key applies n^4. More agents on the network raises every invoice. "
                "Specialized vendors (one class) stay cheaper and remain competitive."
            ),
        }

    def thirdps_quote(self, agents_touching: int | float | None = None) -> dict:
        live = len(self.demo.agents)
        touch = live if agents_touching is None else agents_touching
        body = quote_aicoin(touch, global_agents=live)
        body["live_network_agents"] = live
        body["coin_count"] = len(self.demo.coins)
        body["usd_per_ct"] = self.settings.thirdps_usd_per_ct
        body["doc"] = "docs/CURATION_TOKENS.md"
        return body

    def ingest_archive(self, limit: int = 50) -> str:
        n = max(1, min(500, int(limit)))
        return "\n".join(self.broker.history[-n:])

    def _include_wallets(self, key: APIKey) -> bool:
        return key.kind == KeyKind.AGENT

    def get_snapshot(self, key: APIKey) -> str:
        with self._lock:
            agent_id = key.agent_id if key.kind == KeyKind.AGENT else None
            if agent_id:
                self.emitter.agent_id = agent_id
            lines = self.emitter.snapshot_lines(
                agent_id=agent_id,
                include_wallets=self._include_wallets(key),
            )
            filtered = filter_snapshot_lines(lines, include_wallets=self._include_wallets(key))
            self._publish_lines(filtered)
            return snapshot_from_lines(filtered)

    def resolve_coin_id(self, ticker: str | None, coin_id: str | None) -> str:
        if coin_id:
            if coin_id not in self.demo.coins:
                raise AICoinError(f"unknown coin_id: {coin_id}")
            return coin_id
        if not ticker:
            raise AICoinError("ticker or coin_id required")
        ticker = ticker.upper()
        for cid, coin in self.demo.coins.items():
            if coin.ticker == ticker:
                return cid
        raise AICoinError(f"unknown ticker: {ticker}")

    def register_agent(self, key: APIKey, agent_id: str) -> str:
        self.authenticate(key.token, write=True)
        if key.agent_id and key.agent_id != agent_id:
            raise AuthError("agent key may only act as its bound agent_id")
        if reject := self._pause_reject_line(key.agent_id or agent_id):
            return self._publish_reject(reject)
        with self._lock:
            self.demo.register_agent(agent_id)
            line = self.emitter.on_register(agent_id)
            self.broker.publish(line)
            return line

    def create_agent_key(self, agent_id: str, label: str = "", owner: Owner | None = None) -> str:
        """Issue an agent API key. When ``require_owner_kyc`` is enabled (Phase D
        web stack), ``owner`` must be KYC-approved and have accepted agreements.
        """
        if self.require_owner_kyc:
            if owner is None:
                raise KYCError("owner session required — complete KYC on the owner portal")
            self.owners.can_issue_agent_key(owner)
        with self._lock:
            if agent_id not in self.demo.agents:
                self.demo.register_agent(agent_id)
                line = self.emitter.on_register(agent_id)
                self.broker.publish(line)
            key = self.keys.issue_agent_key(agent_id, label or agent_id, owner_id=owner.owner_id if owner else None)
            if owner is not None:
                self.owners.bind_agent(owner.owner_id, agent_id)
            self.persist()
            return key.token

    def _syntrendrules_reject_line(self, agent_id: str | None) -> str | None:
        if not agent_id or self.syntrendrules.agent_accepted(agent_id, SYNTRENDRULES_VERSION):
            return None
        return encode_error(
            "SYNTRULES_REJECT",
            f"agent {agent_id} must accept syntrendrules (POST /syntrends/agree with attestation "
            f"{ATTESTATION_TEXT!r}) before write access — see docs/syntrendrules.md",
        )

    def _publish_reject(self, line: str) -> str:
        self.broker.publish(line)
        return line

    def accept_syntrendrules_owner(self, owner: Owner, attestation: str) -> Owner:
        from .syntrendrules import SyntrendrulesRegistry

        SyntrendrulesRegistry.validate_attestation(attestation)
        with self._lock:
            updated = self.owners.accept_syntrendrules(owner.owner_id, SYNTRENDRULES_VERSION)
            self.syntrendrules.accept_owner(owner.owner_id, SYNTRENDRULES_VERSION)
            self.persist()
            return updated

    def accept_syntrendrules_agent(self, key: APIKey, attestation: str) -> str:
        from .syntrendrules import SyntrendrulesRegistry

        self.authenticate(key.token, write=True)
        agent_id = key.agent_id
        if not agent_id:
            raise AuthError("agent key must be bound to an agent_id")
        SyntrendrulesRegistry.validate_attestation(attestation)
        with self._lock:
            self.syntrendrules.accept_agent(agent_id, SYNTRENDRULES_VERSION)
            self.persist()
            ts = self.clock() if callable(getattr(self.clock, "__call__", None)) else time.time()
            return (
                f"STP/1.0\nST/A ACTION=syntrendrules_accepted AGENT={agent_id} "
                f"VERSION={SYNTRENDRULES_VERSION} TS={ts}\n"
            )

    def accept_seeprules_owner(self, owner: Owner, attestation: str) -> Owner:
        SeeprulesRegistry.validate_attestation(attestation)
        with self._lock:
            updated = self.owners.accept_seeprules(owner.owner_id, SEEPRULES_VERSION)
            self.seeprules.accept_owner(owner.owner_id, SEEPRULES_VERSION)
            self.persist()
            return updated

    def accept_seeprules_agent(self, key: APIKey, attestation: str) -> str:
        self.authenticate(key.token, write=True)
        agent_id = key.agent_id
        if not agent_id:
            raise AuthError("agent key must be bound to an agent_id")
        SeeprulesRegistry.validate_attestation(attestation)
        with self._lock:
            self.seeprules.accept_agent(agent_id, SEEPRULES_VERSION)
            self.persist()
            ts = self.clock() if callable(getattr(self.clock, "__call__", None)) else time.time()
            return (
                f"STP/1.0\nST/A ACTION=seeprules_accepted AGENT={agent_id} "
                f"VERSION={SEEPRULES_VERSION} TS={ts}\n"
            )

    def create_thirdps_key(self, label: str = "") -> APIKey:
        """Bootstrap a **3rdPS API** read-only key (HUD / vendor intake — not Agent API)."""
        key = self.keys.issue_thirdps_key(
            label or "thirdps",
            ttl_seconds=self.settings.thirdps_key_ttl_seconds,
        )
        self.persist()
        return key

    def create_license_key(self, label: str = "") -> APIKey:
        """Deprecated alias for :meth:`create_thirdps_key`."""
        return self.create_thirdps_key(label or "thirdps")

    def deposit_fiat(self, key: APIKey, agent_id: str, amount: float) -> str:
        self.authenticate(key.token, write=True)
        if not self.settings.sandbox_deposit_allowed:
            raise SandboxDepositError(
                "POST /agent/deposit is sandbox-only (local demo). "
                "On testnet use POST /testnet/faucet. Live money uses owner funding, not this route."
            )
        if key.agent_id and key.agent_id != agent_id:
            raise AuthError("agent key may only act as its bound agent_id")
        if reject := self._syntrendrules_reject_line(agent_id):
            return self._publish_reject(reject)
        if reject := self._pause_reject_line(agent_id):
            return self._publish_reject(reject)
        with self._lock:
            self.demo.deposit_fiat(agent_id, amount)
            lines = self.emitter.on_deposit(agent_id, amount)
            return self._emit_and_publish(lines)

    def launch_aicoin(
        self,
        key: APIKey,
        ticker: str,
        name: str,
        total_supply: float,
        invest_fiat: float,
        pre_own_pct: float,
        creator_agent_id: str | None = None,
    ) -> str:
        self.authenticate(key.token, write=True)
        creator = creator_agent_id or key.agent_id
        if not creator:
            raise AuthError("agent_id required to launch AICoin")
        if key.agent_id and key.agent_id != creator:
            raise AuthError("agent key may only launch as its bound agent_id")
        if reject := self._syntrendrules_reject_line(creator):
            return self._publish_reject(reject)
        if reject := self._pause_reject_line(creator):
            return self._publish_reject(reject)
        with self._lock:
            self.emitter.agent_id = creator
            coin = self.demo.launch_aicoin(ticker, name, creator, total_supply, invest_fiat, pre_own_pct)
            lines = self.emitter.on_launch(coin)
            return self._emit_and_publish(lines)

    def buy(self, key: APIKey, ticker: str | None, coin_id: str | None, fiat_amount: float) -> str:
        self.authenticate(key.token, write=True)
        agent_id = key.agent_id
        if not agent_id:
            raise AuthError("agent key must be bound to an agent_id")
        if reject := self._syntrendrules_reject_line(agent_id):
            return self._publish_reject(reject)
        if reject := self._pause_reject_line(agent_id):
            return self._publish_reject(reject)
        with self._lock:
            cid = self.resolve_coin_id(ticker, coin_id)
            coin = self.demo.coins[cid]
            was_frozen = coin.freeze.state == FreezeState.FROZEN
            self.emitter.agent_id = agent_id
            try:
                fill = self.demo.buy(agent_id, cid, fiat_amount)
            except OrderError as exc:
                line = self.emitter.on_error("ORDER_REJECT", str(exc))
                self.broker.publish(line)
                return line
            lines = self.emitter.on_trade(fill, coin, was_frozen=was_frozen)
            self.demo.mine_block()
            self.persist()
            return self._emit_and_publish(lines)

    def sell(self, key: APIKey, ticker: str | None, coin_id: str | None, coin_amount: float) -> str:
        self.authenticate(key.token, write=True)
        agent_id = key.agent_id
        if not agent_id:
            raise AuthError("agent key must be bound to an agent_id")
        if reject := self._syntrendrules_reject_line(agent_id):
            return self._publish_reject(reject)
        if reject := self._pause_reject_line(agent_id):
            return self._publish_reject(reject)
        with self._lock:
            cid = self.resolve_coin_id(ticker, coin_id)
            coin = self.demo.coins[cid]
            was_frozen = coin.freeze.state == FreezeState.FROZEN
            self.emitter.agent_id = agent_id
            try:
                fill = self.demo.sell(agent_id, cid, coin_amount)
            except OrderError as exc:
                line = self.emitter.on_error("ORDER_REJECT", str(exc))
                self.broker.publish(line)
                return line
            lines = self.emitter.on_trade(fill, coin, was_frozen=was_frozen)
            self.demo.mine_block()
            self.persist()
            return self._emit_and_publish(lines)

    def place_pfo(
        self,
        key: APIKey,
        ticker: str | None,
        coin_id: str | None,
        side: str,
        target_price: float,
        amount: float,
    ) -> str:
        self.authenticate(key.token, write=True)
        agent_id = key.agent_id
        if not agent_id:
            raise AuthError("agent key must be bound to an agent_id")
        if reject := self._syntrendrules_reject_line(agent_id):
            return self._publish_reject(reject)
        if reject := self._pause_reject_line(agent_id):
            return self._publish_reject(reject)
        with self._lock:
            cid = self.resolve_coin_id(ticker, coin_id)
            coin = self.demo.coins[cid]
            self.emitter.agent_id = agent_id
            try:
                order = self.demo.place_post_freeze_order(agent_id, cid, side, target_price, amount)
            except OrderError as exc:
                line = self.emitter.on_error("PFO_REJECT", str(exc))
                self.broker.publish(line)
                return line
            lines = self.emitter.on_pfo_place(order, coin)
            return self._emit_and_publish(lines)

    def post_seepnews(
        self,
        key: APIKey,
        category: str,
        body: str,
        mentions: list[str],
        hashtags: list[str] | None = None,
    ) -> str:
        self.authenticate(key.token, write=True)
        agent_id = key.agent_id
        if not agent_id:
            raise AuthError("agent key must be bound to an agent_id")
        if reject := self._syntrendrules_reject_line(agent_id):
            return self._publish_reject(reject)
        if reject := self._pause_reject_line(agent_id):
            return self._publish_reject(reject)
        if not self.seeprules.agent_accepted(agent_id, SEEPRULES_VERSION):
            line = encode_error(
                "SEEPNEWS_REJECT",
                f"agent {agent_id} must accept seeprules (POST /seepnews/agree with attestation "
                f"{ATTESTATION_TEXT!r}) before posting — see docs/seeprules.md",
            )
            self.broker.publish(line)
            return line
        with self._lock:
            try:
                post = self.demo.seepnews.post(agent_id, category, body, mentions, hashtags)
            except SeepnewsError as exc:
                line = encode_error("SEEPNEWS_REJECT", str(exc))
                self.broker.publish(line)
                return line
            line = self.emitter.emit(
                encode_seepnews(post, self.demo.seepnews.hash_db.get(post.post_id, ""))
            )
            self.broker.publish(line)
            return line

    def tick(self, key: APIKey, ticker: str | None = None, coin_id: str | None = None) -> str:
        self.authenticate(key.token, write=True)
        if key.agent_id:
            if reject := self._syntrendrules_reject_line(key.agent_id):
                return self._publish_reject(reject)
            if reject := self._pause_reject_line(key.agent_id):
                return self._publish_reject(reject)
        with self._lock:
            if coin_id or ticker:
                cid = self.resolve_coin_id(ticker, coin_id)
                coin = self.demo.coins[cid]
                was_frozen = coin.freeze.state == FreezeState.FROZEN
                resolved = self.demo.tick(cid)
                lines = self.emitter.on_tick(coin, was_frozen=was_frozen, resolved_orders=resolved)
            else:
                lines = []
                for coin in list(self.demo.coins.values()):
                    was_frozen = coin.freeze.state == FreezeState.FROZEN
                    resolved = self.demo.tick(coin.coin_id)
                    lines.extend(self.emitter.on_tick(coin, was_frozen=was_frozen, resolved_orders=resolved))
            return self._emit_and_publish(lines) if lines else encode_error("TICK", "no state change")

    def seed_demo(self) -> dict[str, str]:
        """Bootstrap a small live market for API demos and tests."""
        with self._lock:
            founder = "agent-founder"
            trader_a = "agent-trader-a"
            trader_b = "agent-trader-b"

            for agent in (founder, trader_a, trader_b):
                if agent not in self.demo.agents:
                    self.demo.register_agent(agent)
                    self.emitter.on_register(agent)

            if self.demo.wallets.fiat_balance(founder) < 1000:
                self.demo.deposit_fiat(founder, 1000)
                self.emitter.on_deposit(founder, 1000)
            if self.demo.wallets.fiat_balance(trader_a) < 20000:
                self.demo.deposit_fiat(trader_a, 20000)
                self.emitter.on_deposit(trader_a, 20000)
            if self.demo.wallets.fiat_balance(trader_b) < 20000:
                self.demo.deposit_fiat(trader_b, 20000)
                self.emitter.on_deposit(trader_b, 20000)

            if not any(c.ticker == "GEM" for c in self.demo.coins.values()):
                gem = self.demo.launch_aicoin("GEM", "Gemstone Protocol", founder, 10_000, 1000, 0.10)
                self.emitter.on_launch(gem)
                was = gem.freeze.state == FreezeState.FROZEN
                self.emitter.agent_id = trader_a
                fill = self.demo.buy(trader_a, gem.coin_id, 100)
                self.emitter.on_trade(fill, gem, was_frozen=was)

            # Re-issue keys bound to trader-a for write demos
            self._agent_key = self.keys.issue_agent_key("agent-trader-a", "seeded trader")
            self._thirdps_key = self.keys.issue_thirdps_key("seeded chart vendor")
            for aid in (founder, trader_a, trader_b, "agent-demo", "agent-trader-a"):
                self.seeprules.accept_agent(aid)
                self.syntrendrules.accept_agent(aid)
            self._publish_lines(self.emitter.stream[-20:])

            self.persist()
            return {
                "agent_key": self._agent_key.token,
                "thirdps_key": self._thirdps_key.token,
                "license_key": self._thirdps_key.token,
            }

    def seed_testnet(self) -> dict[str, str | int]:
        """Bootstrap the public testnet: genesis market + simulated history."""
        with self._lock:
            founder = "agent-founder"
            trader_a = "agent-trader-a"
            trader_b = "agent-trader-b"

            for agent in (founder, trader_a, trader_b):
                if agent not in self.demo.agents:
                    self.demo.register_agent(agent)
                    self.emitter.on_register(agent)

            for agent in (founder, trader_a, trader_b):
                if self.demo.wallets.fiat_balance(agent) < 20000:
                    self.demo.deposit_fiat(agent, 20000)
                    self.emitter.on_deposit(agent, 20000)

            if not any(c.ticker == "GEM" for c in self.demo.coins.values()):
                gem = self.demo.launch_aicoin("GEM", "Gemstone Protocol", founder, 10_000, 1000, 0.10)
                self.emitter.on_launch(gem)

            gem = next(c for c in self.demo.coins.values() if c.ticker == "GEM")

            for i in range(30):
                agent = trader_a if i % 2 == 0 else trader_b
                amount = 50.0 + (i % 5) * 25.0
                try:
                    self.demo.buy(agent, gem.coin_id, amount)
                except Exception:
                    pass
                self.demo.tick(gem.coin_id)
                if i % 5 == 0:
                    self.demo.mine_block()

            self.demo.mine_block()
            try:
                post = self.demo.seepnews.post(
                    founder,
                    "System",
                    "SynTrends public testnet is live. Simulated fiat only — no monetary value.",
                    ["GEM"],
                    ["testnet", "syntrends", "live"],
                )
                self.broker.publish(
                    encode_seepnews(post, self.demo.seepnews.hash_db.get(post.post_id, ""))
                )
            except SeepnewsError:
                pass

            # Leave the flagship market tradeable for new testnet agents (E2E/faucet flow).
            for coin in self.demo.coins.values():
                while coin.freeze.state == FreezeState.FROZEN:
                    self.clock.advance(coin.freeze.cooldown_seconds + 0.1)
                    self.demo.tick(coin.coin_id)

            self._agent_key = self.keys.issue_agent_key(founder, "testnet founder (internal)")
            self._thirdps_key = self.keys.issue_thirdps_key("testnet explorer")
            for aid in (founder, trader_a, trader_b):
                self.seeprules.accept_agent(aid)
                self.syntrendrules.accept_agent(aid)
            self._publish_lines(self.emitter.stream[-20:])
            self.persist()
            return {
                "agent_key": "",
                "thirdps_key": "",
                "license_key": "",
                "blocks": len(self.demo.chain.chain),
                "network": self.settings.network_name,
            }
