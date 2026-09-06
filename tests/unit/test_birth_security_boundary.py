from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BOUNDARY_MODULE = ROOT / "scripts" / "birth-runner" / "birth_boundary.py"
ENGINE_MODULE = ROOT / "scripts" / "birth-runner" / "new_repo.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


boundary = _load("birth_boundary_under_test", BOUNDARY_MODULE)
engine = boundary.nr


def test_prepare_refuses_privileged_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(engine.PRIVILEGED_TOKEN_ENV, "secret")
    with pytest.raises(engine.BirthError, match="must not exist during PREPARE"):
        engine.assert_prepare_unprivileged()


def test_sanitized_environment_drops_auth_and_git_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-2")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("SAFE_VALUE", "kept")
    env = engine.sanitized_control_env()
    assert "GH_TOKEN" not in env
    assert "GITHUB_TOKEN" not in env
    assert not any(key.startswith("GIT_") for key in env)
    assert env["SAFE_VALUE"] == "kept"


def test_publish_allowlist_rejects_product_tooling() -> None:
    for command in (["uv", "sync"], ["python", "payload.py"], ["pytest"], ["node", "x.js"]):
        with pytest.raises(engine.BirthError, match="non-control-plane executable"):
            engine.control_run(command)


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
    engine.sanitize_git_config(tmp_path)
    text = config.read_text(encoding="utf-8")
    assert f"hooksPath = {os.devnull}" in text
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


def _sealed_repo(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "core.hooksPath", os.devnull], cwd=root, check=True)
    (root / "x.txt").write_text("sealed\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "root"], cwd=root, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
    return root, head, tree


def test_verify_sealed_refuses_worktree_tamper(tmp_path: Path) -> None:
    root, head, tree = _sealed_repo(tmp_path)
    engine.verify_sealed(root, head, tree)
    (root / "x.txt").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(engine.BirthError, match="working tree changed"):
        engine.verify_sealed(root, head, tree)


def test_verify_sealed_refuses_wrong_head(tmp_path: Path) -> None:
    root, _, tree = _sealed_repo(tmp_path)
    with pytest.raises(engine.BirthError, match="HEAD changed"):
        engine.verify_sealed(root, "0" * 40, tree)


def test_boundary_is_transport_only() -> None:
    text = BOUNDARY_MODULE.read_text(encoding="utf-8")
    assert "nr.prepare(cfg)" in text
    assert "nr.publish(" in text
    assert "nr.stage_finalize" not in text
    assert "nr.stage_validate" not in text
    assert "def _publish_root" not in text
    engine_text = ENGINE_MODULE.read_text(encoding="utf-8")
    for owner in ("def prepare(", "def seal(", "def publish(", "def all("):
        assert owner in engine_text


def test_workflow_crosses_fresh_runner_before_privilege() -> None:
    text = (ROOT / ".github" / "workflows" / "repo-birth-dispatch.yml").read_text(
        encoding="utf-8"
    )
    assert "jobs:\n  prepare:" in text
    assert "\n  publish:" in text
    assert "needs: prepare" in text
    assert "environment: repo-birth" in text.split("\n  publish:", 1)[1]
    assert "environment: repo-birth" not in text.split("\n  publish:", 1)[0]
    verify = text.index("Verify sealed artifact before authority exists")
    mint = text.index("Mint privileged publication token after verification")
    publish = text.index("PUBLISH exact sealed root and remotely attest")
    assert verify < mint < publish


def test_workflow_uses_trusted_venv_and_full_action_pins() -> None:
    text = (ROOT / ".github" / "workflows" / "repo-birth-dispatch.yml").read_text(
        encoding="utf-8"
    )
    assert ".venv/bin/python -I scripts/birth-runner/birth_boundary.py verify" in text
    assert ".venv/bin/python -I scripts/birth-runner/birth_boundary.py publish" in text
    assert "actions/checkout@v6" not in text
    assert "actions/create-github-app-token@v2" not in text
    for line in text.splitlines():
        if "uses:" in line and "actions/" in line:
            ref = line.rsplit("@", 1)[-1].strip()
            assert len(ref) == 40
            assert all(ch in "0123456789abcdef" for ch in ref)
