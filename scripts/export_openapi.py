"""Export the SynTrends Agent API OpenAPI spec to docs/openapi.json.

    python -m scripts.export_openapi
    python -m scripts.export_openapi --full   # include owner/explorer routes too

Run this whenever routes/models change so `docs/openapi.json` (published
at docs.syntrends.com in production) stays in sync. Publish alongside the
TypeScript SDK for agent developers who want to generate their own client
from the spec instead of using `sdk/typescript` directly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "openapi.json"


def main() -> None:
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="Export the full stack (agent API + owner portal + explorer), not just the agent API.",
    )
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Output path (default: docs/openapi.json)")
    args = parser.parse_args()

    if args.full:
        from api.app_factory import create_app

        app = create_app(require_owner_kyc=True, mount_web=True)
    else:
        from api.main import app

    spec = app.openapi()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(spec, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Wrote OpenAPI spec ({len(spec.get('paths', {}))} paths) -> {out_path}")


if __name__ == "__main__":
    main()
