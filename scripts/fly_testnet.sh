#!/usr/bin/env bash
# Fly.io testnet helpers — always-on public beta (park is emergency-only).
#
#   ./scripts/fly_testnet.sh status|ensure|health|certs|deploy
#   ./scripts/fly_testnet.sh park confirm
#
# Requires: flyctl in PATH (https://fly.io/docs/flyctl/install/)

set -euo pipefail

APP="${FLY_APP:-syntrends-testnet}"
URL="${SYNTRENDS_URL:-https://testnet.syntrends.com}"
FALLBACK_URL="${SYNTRENDS_FALLBACK_URL:-https://syntrends-testnet.fly.dev}"
CONFIG="${FLY_CONFIG:-deploy/fly.testnet.toml}"
CERT_HOST="${SYNTRENDS_CERT_HOST:-testnet.syntrends.com}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
URL="${URL%/}"
FALLBACK_URL="${FALLBACK_URL%/}"

require_fly() {
  command -v fly >/dev/null 2>&1 || {
    echo "fly CLI not found. Install: https://fly.io/docs/flyctl/install/" >&2
    exit 1
  }
}

health_at() {
  local target="$1"
  if curl -fsS --max-time 30 "$target/health" >/dev/null && \
     status_json="$(curl -fsS --max-time 30 "$target/status")"; then
    env="$(echo "$status_json" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('env','?'))")"
    blocks="$(echo "$status_json" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('block_height', d.get('blocks','?')))")"
    agents="$(echo "$status_json" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('agents','?'))")"
    faucet="$(echo "$status_json" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('faucet_enabled','?'))")"
    echo "OK  $target  env=$env block_height=$blocks agents=$agents faucet=$faucet"
    return 0
  fi
  echo "FAIL $target — not reachable" >&2
  return 1
}

health() {
  if health_at "$URL"; then
    return 0
  fi
  if [[ "$URL" != "$FALLBACK_URL" ]]; then
    echo "Retrying fallback $FALLBACK_URL ..." >&2
    health_at "$FALLBACK_URL" && return 0
  fi
  echo "Hint: run './scripts/fly_testnet.sh ensure' then check DNS/certs for ${CERT_HOST}." >&2
  return 1
}

portal_at() {
  local target="$1"
  local code
  code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 30 "$target/owners/" || echo "000")"
  if [[ "$code" == "200" ]]; then
    echo "OK  $target/owners/  HTTP 200"
    return 0
  fi
  echo "FAIL $target/owners/ HTTP ${code}" >&2
  return 1
}

usage() {
  cat <<EOF
Fly testnet helpers ($APP)

  health   curl primary /health + /owners/ (fallback to fly.dev)
  status   fly status + health
  ensure   scale count 1 (always-on); wait for health
  start    alias of ensure
  certs    fly certs add/show for ${CERT_HOST}
  deploy   fly deploy with deploy/fly.testnet.toml
  park     EMERGENCY: scale to 0 — requires: park confirm

Default policy through Nov 1: keep the app up.

Examples:
  ./scripts/fly_testnet.sh ensure
  ./scripts/fly_testnet.sh health
  python scripts/launch_check.py
EOF
}

ensure_up() {
  require_fly
  echo "Ensuring $APP is running (scale count 1, always-on)…"
  fly scale count 1 -a "$APP" --yes
  echo "Waiting for /health…"
  deadline=$((SECONDS + 90))
  while (( SECONDS < deadline )); do
    sleep 3
    health && exit 0
  done
  echo "Machine started but health check timed out. Try: ./scripts/fly_testnet.sh health" >&2
  exit 1
}

cmd="${1:-help}"
arg2="${2:-}"

case "$cmd" in
  help|-h|--help)
    usage
    ;;
  health)
    h=0
    health || h=1
    p=0
    portal_at "$URL" || {
      if [[ "$URL" != "$FALLBACK_URL" ]]; then
        portal_at "$FALLBACK_URL" || p=1
      else
        p=1
      fi
    }
    exit $(( h || p ))
    ;;
  status)
    require_fly
    fly status -a "$APP"
    echo ""
    health
    ;;
  certs)
    require_fly
    echo "Requesting certificate for ${CERT_HOST} on ${APP} …"
    fly certs add "$CERT_HOST" -a "$APP" || true
    fly certs show "$CERT_HOST" -a "$APP"
    echo ""
    echo "Point DNS for ${CERT_HOST} at this app, then: fly certs check ${CERT_HOST} -a ${APP}"
    echo "Until DNS is live, health falls back to ${FALLBACK_URL}"
    ;;
  park)
    require_fly
    if [[ "$arg2" != "confirm" ]]; then
      echo "Park is emergency-only. Public beta default is always-on (min_machines_running=1)." >&2
      echo "To stop compute billing anyway: ./scripts/fly_testnet.sh park confirm" >&2
      exit 2
    fi
    echo "Parking $APP (scale count 0)…"
    fly scale count 0 -a "$APP" --yes
    echo "Parked. Restore with: ./scripts/fly_testnet.sh ensure"
    ;;
  start|ensure)
    ensure_up
    ;;
  deploy)
    require_fly
    [[ -f "$CONFIG" ]] || { echo "Config not found: $CONFIG" >&2; exit 1; }
    fly deploy -c "$CONFIG"
    echo ""
    echo "Config keeps min_machines_running=1 / auto_stop=off. Do not park after deploy."
    health || true
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
