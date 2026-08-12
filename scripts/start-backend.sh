#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
docker compose up --build -d
curl --fail --silent --show-error --retry 20 --retry-delay 1 \
  http://127.0.0.1:8000/api/health
echo
echo "Backend is listening on host loopback only: http://127.0.0.1:8000"
