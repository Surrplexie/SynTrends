"""Export / restore the app_snapshot JSON blob (Phase L ops).

Uses DATABASE_URL (Postgres or SQLite). Does not talk to a running HTTP server.

    # Local ship DB
    set DATABASE_URL=sqlite:///C:/Users/.../st/data/testnet_live.db
    python scripts/backup_snapshot.py export -o backups/testnet.json
    python scripts/backup_snapshot.py restore -i backups/testnet.json

    # After restore on Fly: restart the app so it reloads the snapshot
    #   fly apps restart syntrends-testnet
    # Or re-seed instead of restore:
    #   fly ssh console -a syntrends-testnet -C "python -m demo.seed_testnet"

See docs/OPS.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from api.persistence import Persistence  # noqa: E402


def _db_url(explicit: str | None) -> str:
    url = (explicit or os.environ.get("DATABASE_URL", "")).strip()
    if not url:
        print("DATABASE_URL is required (or pass --database-url)", file=sys.stderr)
        sys.exit(2)
    return url


def cmd_export(args: argparse.Namespace) -> None:
    url = _db_url(args.database_url)
    store = Persistence(url)
    if not store.ping():
        print("ERROR: database not reachable", file=sys.stderr)
        sys.exit(1)
    snap = store.load()
    if snap is None:
        print("ERROR: no snapshot row (empty DB — seed first)", file=sys.stderr)
        sys.exit(1)

    envelope = {
        "format": "syntrends-app-snapshot/v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "database_backend": "postgres" if store._is_pg else "sqlite",
        "meta": store.snapshot_meta(),
        "snapshot": snap,
    }
    payload = json.dumps(envelope, indent=2)
    if args.output == "-":
        sys.stdout.write(payload)
        if not payload.endswith("\n"):
            sys.stdout.write("\n")
        print(f"Wrote stdout ({len(payload.encode('utf-8'))} bytes) meta={envelope['meta']}", file=sys.stderr)
        return
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size} bytes)")
    print(f"  meta={envelope['meta']}")


def cmd_restore(args: argparse.Namespace) -> None:
    url = _db_url(args.database_url)
    path = Path(args.input)
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "snapshot" in raw:
        snap = raw["snapshot"]
    elif isinstance(raw, dict) and "demo" in raw:
        snap = raw
    else:
        print("ERROR: unrecognized backup format (expected envelope or raw export_snapshot)", file=sys.stderr)
        sys.exit(1)

    store = Persistence(url)
    if not store.ping():
        print("ERROR: database not reachable", file=sys.stderr)
        sys.exit(1)
    if not args.yes:
        print(f"About to overwrite app_snapshot in {url}")
        print("Re-run with --yes to confirm.")
        sys.exit(2)
    store.save(snap)
    print("Restore complete. Restart the app process so it reloads from DB:")
    print("  fly apps restart syntrends-testnet")
    print("  # or locally: stop/start ship_testnet / run_testnet")


def cmd_meta(args: argparse.Namespace) -> None:
    url = _db_url(args.database_url)
    store = Persistence(url)
    print(json.dumps({"ping": store.ping(), "meta": store.snapshot_meta()}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="SynTrends app_snapshot backup/restore")
    parser.add_argument("--database-url", default=None, help="Override DATABASE_URL")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_export = sub.add_parser("export", help="Write snapshot JSON to a file (or - for stdout)")
    p_export.add_argument("-o", "--output", required=True, help="Path, or - for stdout")
    p_export.set_defaults(func=cmd_export)

    p_restore = sub.add_parser("restore", help="Load snapshot JSON into DATABASE_URL")
    p_restore.add_argument("-i", "--input", required=True)
    p_restore.add_argument("--yes", action="store_true", help="Confirm overwrite")
    p_restore.set_defaults(func=cmd_restore)

    p_meta = sub.add_parser("meta", help="Show snapshot metadata + ping")
    p_meta.set_defaults(func=cmd_meta)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
