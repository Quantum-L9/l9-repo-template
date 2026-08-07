#!/usr/bin/env python3
"""Poll an HTTP URL until status 200 or timeout."""

from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: wait_for_http.py <url> <timeout_seconds>", file=sys.stderr)
        return 2
    url = argv[1]
    timeout = float(argv[2])
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if getattr(resp, "status", 200) == 200:
                    print(f"ready: {url}")
                    return 0
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.5)
    print(f"timeout waiting for {url}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
