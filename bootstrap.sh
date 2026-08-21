#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "bootstrap: python3 is required" >&2
  exit 1
fi

exec python3 -m tools.l9_repo --workspace "$ROOT" setup
