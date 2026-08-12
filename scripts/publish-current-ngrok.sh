#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
url="$(curl --fail --silent http://127.0.0.1:4040/api/tunnels \
  | python3 -c 'import json,sys; print(next(t["public_url"] for t in json.load(sys.stdin)["tunnels"] if t["public_url"].startswith("https://")))')"
exec "$script_dir/update-api-url.sh" "$url"
