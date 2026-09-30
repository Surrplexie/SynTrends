#!/usr/bin/env bash
# Ops probe — health + ready + status summary (Phase L).
#
#   SYNTRENDS_URL=https://syntrends-testnet.fly.dev ./scripts/ops_check.sh

set -euo pipefail

URL="${SYNTRENDS_URL:-https://testnet.syntrends.com}"
URL="${URL%/}"
FAIL=0

echo "== Ops check ${URL} =="

if ! health=$(curl -fsS --max-time 25 "${URL}/health"); then
  echo "FAIL /health"
  exit 1
fi
echo "OK  /health  ${health}"

code=$(curl -sS -o /tmp/st_ready.json -w "%{http_code}" --max-time 25 "${URL}/ready" || echo "000")
if [[ "$code" != "200" ]]; then
  echo "FAIL /ready HTTP ${code}"
  cat /tmp/st_ready.json 2>/dev/null || true
  FAIL=1
else
  echo "OK  /ready  HTTP 200"
fi

if ! status=$(curl -fsS --max-time 25 "${URL}/status"); then
  echo "FAIL /status"
  exit 1
fi

python - "$status" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
print(
    f"OK  /status env={d.get('env')} network={d.get('network')} "
    f"block_height={d.get('block_height')} agents={d.get('agents')} "
    f"paused={d.get('agents_paused')} ready={d.get('ready')} "
    f"kyc={d.get('kyc_provider')} persistence_ok={d.get('persistence_ok')}"
)
if d.get("persistence"):
    print(f"    persistence={d['persistence']}")
PY

exit "$FAIL"
