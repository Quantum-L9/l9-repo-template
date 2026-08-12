#!/usr/bin/env python3
"""Validate local env keys for the generic museum example."""

from __future__ import annotations

import sys
from pathlib import Path

REQUIRED = ("L9_ENVIRONMENT",)


def parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def main(argv: list[str]) -> int:
    path = Path(argv[1] if len(argv) > 1 else ".env.example")
    if not path.is_file():
        print(f"missing env file: {path}", file=sys.stderr)
        return 1
    env = parse_env(path)
    missing = [k for k in REQUIRED if not env.get(k)]
    if missing:
        print(f"missing required keys: {', '.join(missing)}", file=sys.stderr)
        return 1
    if env.get("L9_ENVIRONMENT") not in {"local", "dev", "test", "staging", "prod"}:
        print("L9_ENVIRONMENT must be local|dev|test|staging|prod", file=sys.stderr)
        return 1
    print(f"preflight OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
