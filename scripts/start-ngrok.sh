#!/usr/bin/env bash
set -euo pipefail

ngrok_bin="$(command -v ngrok 2>/dev/null || true)"
if [[ -z "$ngrok_bin" && -x "$HOME/.local/bin/ngrok" ]]; then
  ngrok_bin="$HOME/.local/bin/ngrok"
fi
if [[ -z "$ngrok_bin" ]]; then
  echo "ngrok is not installed. Install it from https://ngrok.com/download" >&2
  exit 1
fi

curl --fail --silent --show-error http://127.0.0.1:8000/api/health >/dev/null
echo "Backend health check passed. Starting ngrok for 127.0.0.1:8000..."
echo "The HTTPS URL is also available from http://127.0.0.1:4040/api/tunnels"
exec "$ngrok_bin" http http://127.0.0.1:8000
