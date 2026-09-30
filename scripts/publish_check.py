#!/usr/bin/env python3
"""Dry-run publish checks for syntrends (PyPI) and @syntrends/sdk (npm).

    python scripts/publish_check.py

Exit 0 = packaging looks publishable. Does not upload anything.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Avoid UnicodeEncodeError on Windows cp1252 consoles.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO = Path(__file__).resolve().parent.parent


def _fail(msg: str) -> None:
    print(f"FAIL  {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str) -> None:
    print(f"OK    {msg}")


def read_python_version() -> str:
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        _fail("pyproject.toml: missing version")
    return m.group(1)


def read_ts_version() -> str:
    data = json.loads((REPO / "sdk/typescript/package.json").read_text(encoding="utf-8"))
    return str(data["version"])


def check_versions_aligned() -> str:
    py_v = read_python_version()
    ts_v = read_ts_version()
    if py_v != ts_v:
        _fail(f"version mismatch: pyproject={py_v} package.json={ts_v}")
    _ok(f"versions aligned at {py_v}")
    return py_v


def check_changelog(version: str) -> None:
    cl = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"[{version}]" not in cl and f"## [{version}]" not in cl:
        _fail(f"CHANGELOG.md missing section for {version}")
    _ok(f"CHANGELOG mentions {version}")


def check_python_build() -> None:
    dist = REPO / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    build_dir = REPO / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    subprocess.check_call([sys.executable, "-m", "build", "--outdir", str(dist)], cwd=REPO)
    wheels = list(dist.glob("*.whl")) + list(dist.glob("*.tar.gz"))
    if not wheels:
        _fail("python build produced no artifacts")
    _ok(f"python build -> {len(wheels)} artifact(s)")
    try:
        subprocess.check_call([sys.executable, "-m", "twine", "check", *map(str, wheels)], cwd=REPO)
        _ok("twine check passed")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("WARN  twine not installed or check failed — pip install twine recommended")


def check_python_import() -> None:
    code = (
        "from syntrends import SynTrendsClient, __version__; "
        "assert SynTrendsClient; print(__version__)"
    )
    out = subprocess.check_output([sys.executable, "-c", code], cwd=REPO, text=True).strip()
    _ok(f"import syntrends works (__version__={out})")


def check_typescript() -> None:
    ts = REPO / "sdk/typescript"
    if not (ts / "node_modules").exists():
        subprocess.check_call(["npm", "install"], cwd=ts, shell=True)
    subprocess.check_call(["npm", "test"], cwd=ts, shell=True)
    _ok("typescript npm test passed")
    pkg = json.loads((ts / "package.json").read_text(encoding="utf-8"))
    main = (ts / Path(pkg["main"])).resolve()
    if not main.is_file():
        _fail(f"typescript main entry missing: {main}")
    _ok(f"typescript main exists: {pkg['main']}")
    # Stale layout from old rootDir must not ship.
    for bad in ("dist/src", "dist/test"):
        if (ts / bad).exists():
            _fail(f"stale publish path present: {bad} (run npm run clean)")
    subprocess.check_call(["npm", "run", "pack:dry"], cwd=ts, shell=True)
    _ok("npm pack --dry-run ok")


def main() -> None:
    print("== publish_check ==")
    version = check_versions_aligned()
    check_changelog(version)
    check_python_import()
    check_python_build()
    check_typescript()
    print(f"\nAll publish checks passed for {version}")
    print("Next: docs/PUBLISH.md (twine upload / npm publish or Actions workflow)")


if __name__ == "__main__":
    main()
