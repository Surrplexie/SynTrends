"""Phase L — readiness, enriched status, backup snapshot tooling."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.persistence import Persistence
from api.service import SynTrendsAPIService
from api.web_app import app
from chain.clock import ManualClock


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_ready_endpoint_ok_without_persistence(client: TestClient):
    resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is True
    assert data["persistence_ok"] is True
    assert "block_height" in data
    assert "agents_paused" in data


def test_status_includes_ops_fields(client: TestClient):
    data = client.get("/status").json()
    assert "persistence" in data
    assert "agents_paused" in data
    assert data["ready"] is True


def test_readiness_503_when_persistence_ping_fails():
    svc = SynTrendsAPIService(clock=ManualClock())
    bad = MagicMock()
    bad.ping.return_value = False
    bad.snapshot_meta.return_value = {
        "enabled": True,
        "backend": "postgres",
        "has_snapshot": False,
        "updated_at": None,
        "error": "connection refused",
    }
    svc.persistence = bad
    body, code = svc.readiness()
    assert code == 503
    assert body["ready"] is False
    assert body["persistence_ok"] is False


def test_persistence_ping_and_meta_sqlite(tmp_path: Path):
    db = tmp_path / "ops.db"
    url = f"sqlite:///{db.as_posix()}"
    store = Persistence(url)
    assert store.ping() is True
    meta = store.snapshot_meta()
    assert meta["enabled"] is True
    assert meta["has_snapshot"] is False

    store.save({
        "demo": {},
        "owners": {},
        "keys": [],
        "faucet_last": {},
        "seeprules": {},
        "syntrendrules": {},
        "agent_pause": {},
    })
    meta2 = store.snapshot_meta()
    assert meta2["has_snapshot"] is True
    assert meta2["updated_at"] is not None


def test_backup_snapshot_roundtrip(tmp_path: Path, monkeypatch):
    import scripts.backup_snapshot as bs

    db = tmp_path / "backup.db"
    url = f"sqlite:///{db.as_posix()}"
    store = Persistence(url)
    payload = {
        "demo": {"note": "phase-l"},
        "owners": {"owners": [], "email_index": {}},
        "keys": [],
        "faucet_last": {},
        "seeprules": {},
        "syntrendrules": {},
        "agent_pause": {},
    }
    store.save(payload)

    out = tmp_path / "snap.json"
    monkeypatch.setenv("DATABASE_URL", url)
    ns = type("NS", (), {"database_url": None, "output": str(out)})()
    bs.cmd_export(ns)
    assert out.is_file()
    envelope = json.loads(out.read_text(encoding="utf-8"))
    assert envelope["format"] == "syntrends-app-snapshot/v1"
    assert envelope["snapshot"]["demo"]["note"] == "phase-l"

    db2 = tmp_path / "restore.db"
    url2 = f"sqlite:///{db2.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url2)
    ns2 = type("NS", (), {"database_url": None, "input": str(out), "yes": True})()
    bs.cmd_restore(ns2)
    restored = Persistence(url2).load()
    assert restored["demo"]["note"] == "phase-l"
