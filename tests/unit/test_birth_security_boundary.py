from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "birth-runner" / "birth_boundary.py"
SPEC = importlib.util.spec_from_file_location("birth_boundary_under_test", MODULE)
assert SPEC is not None and SPEC.loader is not None
boundary = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = boundary
SPEC.loader.exec_module(boundary)


def test_prepare_refuses_privileged_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(boundary.PRIVILEGED_TOKEN_ENV, "secret")
    with pytest.raises(boundary.BoundaryError, match="must not exist during PREPARE"):
        boundary._assert_no_privileged_token()


def test_sanitized_environment_drops_privileged_and_git_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(boundary.PRIVILEGED_TOKEN_ENV, "secret")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/tmp/hostile")
    monkeypatch.setenv("SAFE_VALUE", "kept")
    env = boundary._sanitized_env()
    assert boundary.PRIVILEGED_TOKEN_ENV not in env
    assert not any(key.startswith("GIT_") for key in env)
    assert env["SAFE_VALUE"] == "kept"


def test_publish_allowlist_rejects_product_tooling() -> None:
    for command in (["uv", "sync"], ["python", "payload.py"], ["pytest"], ["node", "x.js"]):
        with pytest.raises(boundary.BoundaryError, match="non-control-plane executable"):
            boundary._control_run(command)


def test_git_config_sanitizer_disables_hooks_and_removes_hostile_local_config(
    tmp_path: Path,
) -> None:
    git = tmp_path / ".git"
    git.mkdir()
    config = git / "config"
    config.write_text(
        "[core]\n\thooksPath = .git/hooks\n[credential]\n\thelper = !hostile\n[alias]\n\tpush = !hostile\n",
        encoding="utf-8",
    )
    boundary._sanitize_git_config(tmp_path)
    text = config.read_text(encoding="utf-8")
    assert "hooksPath = /dev/null" in text
    assert "credential" not in text
    assert "alias" not in text
    assert "hostile" not in text


def test_handoff_digest_detects_tamper(tmp_path: Path) -> None:
    schema = json.loads(boundary.SCHEMA.read_text(encoding="utf-8"))
    value = {
        "schema": "l9.repo-birth-handoff/v1",
        "request_digest": "a" * 64,
        "repository": "Quantum-L9/example",
        "package": "example",
        "description": "Example",
        "private": True,
        "repo_class": "non_constellation_python",
        "template": {"sha": "b" * 40, "version": "1.0.0"},
        "organization": {"sha": "c" * 40},
        "payload": {"mode": "none", "source": {}},
        "prepared": {
            "root_commit_sha": "d" * 40,
            "root_tree_sha": "e" * 40,
            "root_path": str(tmp_path),
            "contents_manifest_sha256": "f" * 64,
            "permanent_receipt_digest": "1" * 64,
        },
        "prepare_receipt": str(tmp_path / "receipt.json"),
        "bootstrap_timeout": 180,
        "profile": {},
        "receipt": {},
    }
    assert schema["properties"]["schema"]["const"] == value["schema"]
    value["handoff_digest"] = boundary._sha256(value)
    boundary._validate_handoff(value)
    value["description"] = "Tampered"
    with pytest.raises(boundary.BoundaryError, match="digest mismatch"):
        boundary._validate_handoff(value)


def test_workflow_mints_privileged_token_after_prepare() -> None:
    text = (ROOT / ".github" / "workflows" / "repo-birth-dispatch.yml").read_text(
        encoding="utf-8"
    )
    prepare = text.index("PREPARE, validate, and seal without privileged birth authority")
    mint = text.index("Mint privileged publication token after seal")
    publish = text.index("PUBLISH exact sealed root and remotely attest")
    assert prepare < mint < publish
    assert "actions/checkout@v6" not in text
    assert "actions/create-github-app-token@v2" not in text
