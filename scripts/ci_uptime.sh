#!/usr/bin/env bash
# Week-1 uptime probe: /health, /ready, /status, owner portal HTML.
# Tries primary then fly.dev fallback. No Fly token required.
#
#   ./scripts/ci_uptime.sh
#   SYNTRENDS_URL=https://testnet.syntrends.com ./scripts/ci_uptime.sh

set -euo pipefail

PRIMARY="${SYNTRENDS_URL:-https://testnet.syntrends.com}"
FALLBACK="${SYNTRENDS_FALLBACK_URL:-https://syntrends-testnet.fly.dev}"
PRIMARY="${PRIMARY%/}"
FALLBACK="${FALLBACK%/}"

probe() {
  local url="$1"
  echo "== uptime ${url} =="
  curl -fsS --max-time 25 "${url}/health" >/dev/null
  echo "OK  /health"
  local code
  code="$(curl -sS -o /tmp/st_ready_up.json -w "%{http_code}" --max-time 25 "${url}/ready" || echo "000")"
  if [[ "$code" != "200" ]]; then
    echo "FAIL /ready HTTP ${code}" >&2
    cat /tmp/st_ready_up.json 2>/dev/null || true
    return 1
  fi
  echo "OK  /ready"
  curl -fsS --max-time 25 "${url}/status" >/dev/null
  echo "OK  /status"
  code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 25 "${url}/owners/" || echo "000")"
  if [[ "$code" != "200" ]]; then
    echo "FAIL /owners/ HTTP ${code}" >&2
    return 1
  fi
  echo "OK  /owners/"
  return 0
}

if probe "$PRIMARY"; then
  exit 0
fi
echo "WARN  primary failed; trying fallback ${FALLBACK}" >&2
probe "$FALLBACK"
