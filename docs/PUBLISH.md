# Publish SDKs (Phase M)

How to release **`syntrends`** (PyPI) and **`@syntrends/sdk`** (npm).

| Package | Registry | Version source |
|---------|----------|----------------|
| `syntrends` | PyPI | `pyproject.toml` → `[project].version` |
| `@syntrends/sdk` | npm | `sdk/typescript/package.json` → `version` |

Keep both versions **equal**. Update [`CHANGELOG.md`](../CHANGELOG.md) in the same PR.

---

## Version policy

| Version | Meaning |
|---------|---------|
| `0.1.x` | Public testnet SDKs (breaking changes allowed with changelog note) |
| `0.x.y` bump | Patch = fixes; minor = new APIs; still pre-1.0 |
| `1.0.0` | Reserved for stable Agent API + mainnet-ready contract |

Git tags:

- SDK release: `v0.1.0` (matches package version)
- Testnet milestone (optional): `testnet-v1.0` (platform milestone, not necessarily SDK version)

---

## Pre-publish checklist

1. CI green on `main`
2. `CHANGELOG.md` updated for this version
3. Versions match in `pyproject.toml` and `sdk/typescript/package.json`
4. Dry-run passes locally:

```powershell
python scripts/publish_check.py
```

5. Manual Fly E2E still green (optional but recommended):

```powershell
.\scripts\ops_check.ps1
python -m demo.e2e_testnet --base-url https://testnet.syntrends.com --check-pause
```

---

## Local dry-run

```powershell
# From repo root
python scripts/publish_check.py

# Python wheel only
pip install -e ".[dev]"
python -m build
twine check dist/*

# TypeScript pack only
cd sdk/typescript
npm run pack:dry
```

---

## Publish via GitHub Actions (recommended)

Workflow: [`.github/workflows/publish-sdk.yml`](../.github/workflows/publish-sdk.yml)

**Secrets** (repo Settings → Secrets → Actions):

| Secret | Purpose |
|--------|---------|
| `PYPI_API_TOKEN` | PyPI API token (`pypi-...`) |
| `NPM_TOKEN` | npm automation token |

1. Actions → **Publish SDKs** → Run workflow
2. Choose: `python` / `typescript` / `both`
3. Confirm version string matches the repo files

Or tag push: create `v0.1.0` and the workflow can be extended to publish on tags (currently **manual only** for safety).

---

## Publish manually

### PyPI

```powershell
pip install -e ".[dev]"
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
python -m build
twine check dist/*
twine upload dist/*   # needs PYPI credentials
```

### npm

```powershell
cd sdk/typescript
npm test
npm publish --access public   # needs npm login / NPM_TOKEN
```

---

## After publish

1. `git tag -a v0.1.0 -m "syntrends / @syntrends/sdk 0.1.0"`
2. `git push origin v0.1.0`
3. Verify fresh install:

```powershell
pip install syntrends==0.1.0
python -c "from syntrends import SynTrendsClient, __version__; print(__version__)"

npm install @syntrends/sdk@0.1.0
```

4. Point external testers at [`EXTERNAL_TESTERS.md`](EXTERNAL_TESTERS.md)

---

## Related

| Doc | Purpose |
|-----|---------|
| [`EXTERNAL_TESTERS.md`](EXTERNAL_TESTERS.md) | Invite / feedback loop |
| [`PUBLIC_LAUNCH.md`](PUBLIC_LAUNCH.md) | Phase N go-live |
| [`RELEASE.md`](RELEASE.md) | `testnet-v1.0` platform checklist |
| [`AGENT_QUICKSTART.md`](AGENT_QUICKSTART.md) | Published-package quickstart |
