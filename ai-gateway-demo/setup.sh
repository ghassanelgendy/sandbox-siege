#!/usr/bin/env bash
# Usage: ./setup.sh [API_KEY]
# If no argument is given, you'll be prompted (input hidden, not echoed).
set -euo pipefail
cd "$(dirname "$0")"

if [ -n "${1:-}" ]; then
  KEY="$1"
else
  read -rsp "Enter AI_GATEWAY_API_KEY: " KEY
  echo
fi

if [ -z "$KEY" ]; then
  echo "error: no key provided" >&2
  exit 1
fi

printf 'AI_GATEWAY_API_KEY=%s\n' "$KEY" > .env.local
chmod 600 .env.local

npm install

echo
echo "Setup complete. Run: npm start"
