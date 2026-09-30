"""Phase E persistence — SQLite (default file) or PostgreSQL via DATABASE_URL."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any
from urllib.parse import unquote, urlparse


class Persistence:
    """Single-row JSON snapshot store. Disabled when ``database_url`` is None."""

    def __init__(self, database_url: str | None) -> None:
        self.database_url = database_url
        self._is_pg = bool(database_url and database_url.startswith("postgres"))

    @property
    def enabled(self) -> bool:
        return bool(self.database_url)

    def _sqlite_path(self) -> str:
        assert self.database_url
        url = self.database_url
        if url.startswith("sqlite://"):
            path = url.removeprefix("sqlite://")
            if path.startswith("/"):
                return path
            return path  # relative path
        return url

    def _connect_sqlite(self) -> sqlite3.Connection:
        path = self._sqlite_path()
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_snapshot ("
            "id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        return conn

    def _ensure_schema_pg(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS app_snapshot ("
                "id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)"
            )

    def _connect_pg(self):
        import psycopg

        conn = psycopg.connect(self.database_url)
        conn.autocommit = True
        self._ensure_schema_pg(conn)
        return conn

    def save(self, snapshot: dict[str, Any]) -> None:
        if not self.enabled:
            return
        payload = json.dumps(snapshot)
        now = time.time()
        if self._is_pg:
            import psycopg

            with psycopg.connect(self.database_url) as conn:
                with conn.cursor() as cur:
                    self._ensure_schema_pg(conn)
                    cur.execute(
                        "INSERT INTO app_snapshot (id, payload, updated_at) VALUES (1, %s, %s) "
                        "ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = EXCLUDED.updated_at",
                        (payload, now),
                    )
                conn.commit()
        else:
            conn = self._connect_sqlite()
            try:
                conn.execute(
                    "INSERT INTO app_snapshot (id, payload, updated_at) VALUES (1, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                    (payload, now),
                )
                conn.commit()
            finally:
                conn.close()

    def load(self) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        if self._is_pg:
            import psycopg

            with psycopg.connect(self.database_url) as conn:
                with conn.cursor() as cur:
                    self._ensure_schema_pg(conn)
                    cur.execute("SELECT payload FROM app_snapshot WHERE id = 1")
                    row = cur.fetchone()
                    if not row:
                        return None
                    data = row[0]
                    return json.loads(data) if isinstance(data, str) else data
        conn = self._connect_sqlite()
        try:
            row = conn.execute("SELECT payload FROM app_snapshot WHERE id = 1").fetchone()
            if not row:
                return None
            return json.loads(row[0])
        finally:
            conn.close()

    def ping(self) -> bool:
        """Return True if the store is reachable (or persistence is disabled)."""
        if not self.enabled:
            return True
        try:
            if self._is_pg:
                import psycopg

                with psycopg.connect(self.database_url) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
                return True
            conn = self._connect_sqlite()
            try:
                conn.execute("SELECT 1").fetchone()
                return True
            finally:
                conn.close()
        except Exception:
            return False

    def snapshot_meta(self) -> dict[str, Any]:
        """Ops metadata for the single-row snapshot (no payload)."""
        if not self.enabled:
            return {"enabled": False, "backend": None, "has_snapshot": False, "updated_at": None}
        backend = "postgres" if self._is_pg else "sqlite"
        try:
            if self._is_pg:
                import psycopg

                with psycopg.connect(self.database_url) as conn:
                    with conn.cursor() as cur:
                        self._ensure_schema_pg(conn)
                        cur.execute("SELECT updated_at FROM app_snapshot WHERE id = 1")
                        row = cur.fetchone()
                        if not row:
                            return {
                                "enabled": True,
                                "backend": backend,
                                "has_snapshot": False,
                                "updated_at": None,
                            }
                        return {
                            "enabled": True,
                            "backend": backend,
                            "has_snapshot": True,
                            "updated_at": float(row[0]),
                        }
            conn = self._connect_sqlite()
            try:
                row = conn.execute(
                    "SELECT updated_at FROM app_snapshot WHERE id = 1"
                ).fetchone()
                if not row:
                    return {
                        "enabled": True,
                        "backend": backend,
                        "has_snapshot": False,
                        "updated_at": None,
                    }
                return {
                    "enabled": True,
                    "backend": backend,
                    "has_snapshot": True,
                    "updated_at": float(row[0]),
                }
            finally:
                conn.close()
        except Exception as exc:
            return {
                "enabled": True,
                "backend": backend,
                "has_snapshot": False,
                "updated_at": None,
                "error": str(exc),
            }


def database_url_from_env(env_value: str | None) -> str | None:
    if not env_value:
        return None
    return env_value.strip()
