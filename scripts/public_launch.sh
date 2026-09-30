#!/usr/bin/env bash
# Phase N — public launch helpers (ops).
#   ./scripts/public_launch.sh print-cutover|check|check-strict|wake|urls
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URLS="$ROOT/ops/public_urls.json"
PRIMARY="$(python -c "import json;print(json.load(open(r'$URLS'))['public_testnet']['primary'])")"
FALLBACK="$(python -c "import json;print(json.load(open(r'$URLS'))['public_testnet']['fallback'])")"
APP="$(python -c "import json;print(json.load(open(r'$URLS'))['fly_app'])")"
CORS="$(python -c "import json;print(json.load(open(r'$URLS'))['cors_origins_csv'])")"
WEBHOOK="$(python -c "import json;print(json.load(open(r'$URLS'))['public_testnet']['persona_webhook'])")"
ACTION="${1:-check}"

show_urls() {
  echo "primary:  $PRIMARY"
  echo "fallback: $FALLBACK"
  echo "fly app:  $APP"
  echo "webhook:  $WEBHOOK"
}

case "$ACTION" in
  urls) show_urls ;;
  print-cutover)
    show_urls
    echo
    echo "# 1) TLS / DNS"
    echo "fly certs add testnet.syntrends.com -a $APP"
    echo "fly certs check testnet.syntrends.com -a $APP"
    echo
    echo "# 2) CORS + Persona"
    echo "fly secrets set CORS_ORIGINS=\"$CORS\" \\"
    echo "  KYC_PROVIDER=persona \\"
    echo "  PERSONA_API_KEY=... PERSONA_WEBHOOK_SECRET=... \\"
    echo "  PERSONA_TEMPLATE_ID=... PERSONA_ENVIRONMENT=sandbox \\"
    echo "  -a $APP"
    echo
    echo "# 3) Persona webhook: $WEBHOOK"
    echo "# 4) SYNTRENDS_URL=$PRIMARY ./scripts/ops_check.sh && python scripts/launch_check.py --require-persona"
    echo "Full runbook: docs/PUBLIC_LAUNCH.md"
    ;;
  wake)
    "$ROOT/scripts/fly_testnet.sh" start
    SYNTRENDS_URL="$PRIMARY" "$ROOT/scripts/ops_check.sh"
    ;;
  check)
    cd "$ROOT"
    python scripts/launch_check.py --base-url "$PRIMARY" --also-fallback
    ;;
  check-strict)
    cd "$ROOT"
    python scripts/launch_check.py --base-url "$PRIMARY" --require-persona --require-packages
    ;;
  *)
    echo "usage: $0 print-cutover|check|check-strict|wake|urls" >&2
    exit 2
    ;;
esac
