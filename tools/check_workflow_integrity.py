#!/usr/bin/env python3
"""Museum workflow integrity probe (fail-closed stubs stay green)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    required = (
        "Makefile",
        "Repo.mk",
        "tools/l9_repo/Makefile.template",
        ".l9/repo-workflow.json",
        ".l9/repo-workflow.schema.json",
        "MANIFEST.sha256",
    )
    missing = [rel for rel in required if not (ROOT / rel).is_file()]
    if missing:
        for rel in missing:
            print(f"integrity FAIL: missing {rel}")
        return 1
    template = (ROOT / "tools/l9_repo/Makefile.template").read_bytes()
    makefile = (ROOT / "Makefile").read_bytes()
    if makefile != template:
        print("integrity FAIL: Makefile drift from Makefile.template")
        return 1
    print("integrity OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
