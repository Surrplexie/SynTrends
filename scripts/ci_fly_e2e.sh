#!/usr/bin/env bash
# CI entrypoint: wake Fly (optional), wait for testnet, run full E2E (+ optional pause check).
#
# Secrets / env (GitHub Actions):
#   FLY_API_TOKEN     — wake scaled-to-zero app before E2E
#   SYNTRENDS_URL     — default https://syntrends-testnet.fly.dev
#   FLY_APP           — default syntrends-testnet
#   E2E_WAIT_SECONDS  — default 180 (cold start)
#   E2E_CHECK_PAUSE   — set 1 to verify owner pause/resume in the same run

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

URL="${SYNTRENDS_URL:-https://testnet.syntrends.com}"
APP="${FLY_APP:-syntrends-testnet}"
export SYNTRENDS_URL="$URL"

if [[ -n "${FLY_API_TOKEN:-}" ]]; then
  echo "== Wake Fly app ${APP} =="
  flyctl scale count 1 -a "$APP" --yes
else
  echo "== FLY_API_TOKEN not set — skipping fly scale (app must already be running) =="
fi

echo "== Wait for testnet =="
if ! bash scripts/ci_wait_testnet.sh; then
  if [[ "$URL" != "https://syntrends-testnet.fly.dev" ]]; then
    echo "== Primary wait failed; retrying fly.dev fallback =="
    export SYNTRENDS_URL="https://syntrends-testnet.fly.dev"
    URL="$SYNTRENDS_URL"
    bash scripts/ci_wait_testnet.sh
  else
    exit 1
  fi
fi

E2E_ARGS=(--base-url "$URL")
if [[ "${E2E_CHECK_PAUSE:-0}" == "1" ]]; then
  E2E_ARGS+=(--check-pause)
fi

echo "== Run E2E =="
python -m demo.e2e_testnet "${E2E_ARGS[@]}"
