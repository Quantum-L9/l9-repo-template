#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

for tool in python3 make; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "bootstrap: $tool is required" >&2
    exit 1
  fi
done

# Repository Execution V2: setup is the make-v1 facade phase (Repo.mk repo-setup).
exec make -C "$ROOT" setup
