#!/usr/bin/env bash
# Wait until a deployed testnet responds to /health and /status (testnet env).
#
#   SYNTRENDS_URL=https://syntrends-testnet.fly.dev E2E_WAIT_SECONDS=180 ./scripts/ci_wait_testnet.sh

set -euo pipefail

URL="${SYNTRENDS_URL:-https://testnet.syntrends.com}"
URL="${URL%/}"
WAIT="${E2E_WAIT_SECONDS:-180}"
INTERVAL="${E2E_WAIT_INTERVAL:-5}"

deadline=$((SECONDS + WAIT))
last_err=""

echo "Waiting for testnet at ${URL} (timeout ${WAIT}s)..."

while (( SECONDS < deadline )); do
  if health=$(curl -fsS --max-time 25 "${URL}/health" 2>&1); then
    ready_code=$(curl -sS -o /tmp/st_ready_wait.json -w "%{http_code}" --max-time 25 "${URL}/ready" || echo "000")
    if [[ "$ready_code" != "200" ]]; then
      last_err="GET /ready returned ${ready_code}"
      echo "  retry in ${INTERVAL}s (${last_err})"
      sleep "$INTERVAL"
      continue
    fi
    if status_json=$(curl -fsS --max-time 25 "${URL}/status" 2>&1); then
      if python -c "import json,sys; d=json.loads(sys.argv[1]); sys.exit(0 if d.get('env')=='testnet' else 1)" "$status_json"; then
        blocks=$(python -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('block_height', d.get('blocks','?')))" "$status_json")
        echo "OK  ${URL}  env=testnet  block_height=${blocks} ready=true"
        exit 0
      fi
      last_err="status env is not testnet"
    else
      last_err="GET /status failed"
    fi
  else
    last_err="GET /health failed: ${health}"
  fi
  echo "  retry in ${INTERVAL}s (${last_err})"
  sleep "$INTERVAL"
done

echo "TIMEOUT: testnet not ready at ${URL} after ${WAIT}s — last: ${last_err}" >&2
exit 1
