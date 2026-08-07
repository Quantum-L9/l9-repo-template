#!/usr/bin/env python3
"""Seed .github surfaces from pinned Quantum-L9/.github (org max-pull)."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = ROOT / ".l9" / "ci-pin"
ORG_REPO = "Quantum-L9/.github"
CORE_REPO = "Quantum-L9/l9-ci-core"
HEX40 = re.compile(r"^[0-9a-f]{40}$")

WORKFLOWS = (
    "l9-ci-pack/workflows/l9-analysis.yml",
    "l9-ci-pack/workflows/l9-lint-test.yml",
)
TEMPLATES = (
    ("templates/dependabot.yml", ".github/dependabot.yml"),
    ("templates/CODEOWNERS.repo", ".github/CODEOWNERS"),
)

FORBIDDEN_USES_LINE = (
    re.compile(r"^\s*uses:\s+\S+@main\b"),
    re.compile(r"^\s*uses:\s+\S+@v1\b"),
)
FORBIDDEN_ANY = (
    re.compile(r"workflow-templates/"),
    re.compile(r"cryptoxdog/golden-repo", re.I),
)


def load_pins() -> dict[str, str]:
    if not PIN_PATH.is_file():
        raise SystemExit("missing .l9/ci-pin")
    pins: dict[str, str] = {}
    for line in PIN_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        pins[key.strip()] = value.strip()
    sha = pins.get("ORG_GITHUB_SHA", "")
    if not HEX40.match(sha.lower()):
        raise SystemExit(f"ORG_GITHUB_SHA must be 40-char hex, got {sha!r}")
    return pins


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "l9-repo-template-sync-ci"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def raw_org(sha: str, rel: str) -> str:
    return f"https://raw.githubusercontent.com/{ORG_REPO}/{sha}/{rel}"


def list_governance(sha: str) -> list[str]:
    api = f"https://api.github.com/repos/{ORG_REPO}/contents/l9-ci-pack/governance?ref={sha}"
    data = json.loads(fetch(api).decode("utf-8"))
    names: list[str] = []
    for item in data:
        if item.get("type") == "file" and str(item.get("name", "")).endswith((".yaml", ".yml")):
            names.append(str(item["name"]))
    if not names:
        raise SystemExit("no governance YAML files found in org pack")
    return sorted(names)


def write_bytes(rel: Path, data: bytes) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"wrote {rel}")


def patch_lint_test(text: str) -> str:
    """Ensure requirements-consumer-ci.txt is installed; keep pack env defaults."""
    if "requirements-consumer-ci.txt" in text:
        return text
    marker = "if [ -f requirements-ci.txt ]; then pip install -r requirements-ci.txt; fi"
    if marker not in text:
        print(
            "warning: lint-test install needle not found; leaving workflow as-is",
            file=sys.stderr,
        )
        return text
    addition = (
        marker
        + "\n"
        + "          if [ -f requirements-consumer-ci.txt ]; then "
        + "pip install -r requirements-consumer-ci.txt; fi"
    )
    return text.replace(marker, addition)


def validate_workflow(path: Path, text: str) -> None:
    for line in text.splitlines():
        for pattern in FORBIDDEN_USES_LINE:
            if pattern.search(line):
                raise SystemExit(f"refusing forbidden uses: in {path}: {line.strip()}")
    for pattern in FORBIDDEN_ANY:
        if pattern.search(text):
            raise SystemExit(f"refusing forbidden pattern in {path}: {pattern.pattern}")


def fetch_consumer_requirements(pins: dict[str, str]) -> bytes:
    core_pin = pins.get("L9_CI_CORE_PIN", "").strip()
    candidates: list[str] = []
    if core_pin and HEX40.match(core_pin.lower()):
        candidates.append(
            f"https://raw.githubusercontent.com/{CORE_REPO}/{core_pin}/requirements-consumer-ci.txt"
        )
    candidates.append(
        f"https://raw.githubusercontent.com/{CORE_REPO}/main/requirements-consumer-ci.txt"
    )
    last_err: Exception | None = None
    for url in candidates:
        try:
            return fetch(url)
        except urllib.error.HTTPError as exc:
            last_err = exc
            continue
    raise SystemExit(f"failed to fetch requirements-consumer-ci.txt: {last_err}")


def main() -> int:
    pins = load_pins()
    sha = pins["ORG_GITHUB_SHA"]

    for name in list_governance(sha):
        rel = f"l9-ci-pack/governance/{name}"
        data = fetch(raw_org(sha, rel))
        write_bytes(Path(".github/governance") / name, data)

    for rel in WORKFLOWS:
        data = fetch(raw_org(sha, rel))
        text = data.decode("utf-8")
        dest_name = Path(rel).name
        dest = Path(".github/workflows") / dest_name
        if dest_name == "l9-lint-test.yml":
            text = patch_lint_test(text)
        validate_workflow(dest, text)
        write_bytes(dest, text.encode("utf-8"))

    for src, dest in TEMPLATES:
        data = fetch(raw_org(sha, src))
        write_bytes(Path(dest), data)

    # Core file only — pack does not ship requirements-consumer-ci.txt
    write_bytes(Path("requirements-consumer-ci.txt"), fetch_consumer_requirements(pins))

    # Optional: skip governance-caller.yml (redundant with l9-analysis caller)
    print(f"sync-ci OK from {ORG_REPO}@{sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
