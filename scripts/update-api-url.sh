#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 https://your-api.ngrok-free.app" >&2
  exit 2
fi

api_url="${1%/}"
if [[ ! "$api_url" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?$ ]]; then
  echo "API URL must be a valid HTTPS origin without a path." >&2
  exit 2
fi

gh auth status >/dev/null
repo="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
gh variable set VITE_API_BASE_URL --repo "$repo" --body "$api_url"
gh workflow run pages.yml --repo "$repo" --ref main

pages_url="https://$(cut -d/ -f1 <<<"$repo").github.io/$(cut -d/ -f2 <<<"$repo")/"
echo "API URL: $api_url"
echo "Pages workflow: triggered for $repo@main"
echo "GitHub Pages: $pages_url"
