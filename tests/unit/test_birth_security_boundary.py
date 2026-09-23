from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BOUNDARY_MODULE = ROOT / "scripts" / "birth-runner" / "birth_boundary.py"
ENGINE_MODULE = ROOT / "scripts" / "birth-runner" / "new_repo.py"
LEGACY_MODULE = ROOT / "scripts" / "birth-runner" / "new_repo_legacy.py"
WORKFLOW = ROOT / ".github" / "workflows" / "repo-birth-dispatch.yml"

# The child-subreaper flag and the /proc process table are Linux kernel
# facilities; the dispatch workflow runs on ubuntu-latest and CI is Linux. On
# any other platform the engine records the sweep as SKIP and the direct path
# remains local/debug only, so there is no contract to discriminate there.
linux_only = pytest.mark.skipif(
    sys.platform != "linux",
    reason="child-subreaper isolation and /proc process tables exist only on Linux",
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
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
    monkeypatch.setenv(engine.PRIVILEGED_TOKEN_ENV, "secret-3")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("SAFE_VALUE", "kept")
    env = engine.sanitized_control_env()
    assert "GH_TOKEN" not in env
    assert "GITHUB_TOKEN" not in env
    assert engine.PRIVILEGED_TOKEN_ENV not in env
    assert not any(key.startswith("GIT_") for key in env)
    assert env["SAFE_VALUE"] == "kept"


def test_trusted_git_env_pins_out_global_and_system_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/product/gitconfig")
    monkeypatch.setenv(engine.PRIVILEGED_TOKEN_ENV, "secret")
    env = engine.trusted_git_env()
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert engine.PRIVILEGED_TOKEN_ENV not in env
    assert "GH_TOKEN" not in env


def test_publish_allowlist_rejects_product_tooling() -> None:
    commands = (["uv", "sync"], ["python", "payload.py"], ["pytest"], ["node", "x.js"])
    for command in commands:
        with pytest.raises(engine.BirthError, match="non-control-plane executable"):
            engine.control_run(command)


def _fake_tool(directory: Path, name: str) -> Path:
    tool = directory / name
    # PATH is pinned to the control directory inside control_run, so the dump
    # tool must be addressed absolutely.
    tool.write_text('#!/bin/sh\n/usr/bin/env > "$1"\nexit 0\n', encoding="utf-8")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    return tool


def test_control_run_hands_publication_token_only_to_gh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    _fake_tool(trusted, "git")
    _fake_tool(trusted, "gh")
    monkeypatch.setenv(engine.CONTROL_PATH_ENV, str(trusted))
    monkeypatch.setenv(engine.PRIVILEGED_TOKEN_ENV, "fake-publication-token")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/product/gitconfig")
    git_env = tmp_path / "git.env"
    gh_env = tmp_path / "gh.env"
    engine.control_run(["git", str(git_env)], env={"GH_TOKEN": "smuggled", "GIT_DIR": "/x"})
    engine.control_run(["gh", str(gh_env)])
    git_seen = git_env.read_text(encoding="utf-8")
    gh_seen = gh_env.read_text(encoding="utf-8")
    assert "fake-publication-token" not in git_seen
    assert "smuggled" not in git_seen
    assert "GIT_DIR=" not in git_seen
    assert "GIT_CONFIG_GLOBAL=/product/gitconfig" not in git_seen
    assert f"GIT_CONFIG_GLOBAL={os.devnull}" in git_seen
    assert "GH_TOKEN=fake-publication-token" in gh_seen
    assert f"{engine.PRIVILEGED_TOKEN_ENV}=" not in gh_seen


def test_control_tool_resolution_ignores_hostile_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted = tmp_path / "trusted"
    hostile = tmp_path / "hostile"
    trusted.mkdir()
    hostile.mkdir()
    for root in (trusted, hostile):
        tool = root / "git"
        tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv(engine.CONTROL_PATH_ENV, str(trusted))
    monkeypatch.setenv("PATH", f"{hostile}{os.pathsep}{trusted}")
    assert engine._resolve_control_tool("git") == str((trusted / "git").resolve())


def test_control_tool_resolution_requires_prebound_trust_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(engine.CONTROL_PATH_ENV, raising=False)
    with pytest.raises(engine.BirthError, match="must be bound before privileged PUBLISH"):
        engine._resolve_control_tool("git")


def test_control_tool_resolution_rejects_missing_trusted_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    monkeypatch.setenv(engine.CONTROL_PATH_ENV, str(trusted))
    with pytest.raises(engine.BirthError, match="trusted gh executable is not present"):
        engine._resolve_control_tool("gh")


def test_bind_git_refuses_executable_inside_mutable_birth_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hostile = tmp_path / "runner-temp" / "bin"
    hostile.mkdir(parents=True)
    tool = hostile / "git"
    tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner-temp"))
    monkeypatch.setenv("PATH", str(hostile))
    with pytest.raises(engine.BirthError, match="mutable birth root"):
        engine.bind_git()


def test_bound_git_refuses_to_run_after_the_file_changed(tmp_path: Path) -> None:
    fake = tmp_path / "git"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    tool = engine.TrustedTool(path=str(fake), fingerprint=engine._fingerprint(fake))
    engine._git(tool, ["--version"], cwd=tmp_path)
    time.sleep(0.01)
    fake.write_text("#!/bin/sh\necho swapped\nexit 0\n", encoding="utf-8")
    with pytest.raises(engine.BirthError, match="changed after binding"):
        engine._git(tool, ["--version"], cwd=tmp_path)


def test_git_config_sanitizer_disables_hooks_and_removes_hostile_local_config(
    tmp_path: Path,
) -> None:
    git = tmp_path / ".git"
    git.mkdir()
    config = git / "config"
    config.write_text(
        "[core]\n"
        "\thooksPath = .git/hooks\n"
        "\tfsmonitor = ./product-script\n"
        "[credential]\n"
        "\thelper = !hostile\n"
        "[alias]\n"
        "\tpush = !hostile\n"
        "[include]\n"
        "\tpath = ../product.inc\n",
        encoding="utf-8",
    )
    (git / "config.worktree").write_text("[core]\n\tfsmonitor = ./other\n", encoding="utf-8")
    engine.sanitize_git_config(tmp_path)
    text = config.read_text(encoding="utf-8")
    assert f"hooksPath = {os.devnull}" in text
    assert "fsmonitor = false" in text
    assert "credential" not in text
    assert "alias" not in text
    assert "include" not in text
    assert "hostile" not in text
    assert "product-script" not in text
    assert not (git / "config.worktree").exists()


def test_git_config_sanitizer_refuses_gitfile_roots(tmp_path: Path) -> None:
    (tmp_path / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    with pytest.raises(engine.BirthError, match="no .git directory"):
        engine.sanitize_git_config(tmp_path)


def _handoff(tmp_path: Path) -> dict[str, object]:
    return {
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


def test_handoff_digest_detects_tamper(tmp_path: Path) -> None:
    schema = json.loads(boundary.SCHEMA.read_text(encoding="utf-8"))
    value = _handoff(tmp_path)
    assert schema["properties"]["schema"]["const"] == value["schema"]
    value["handoff_digest"] = boundary._sha256(value)
    boundary._validate_handoff(value)
    value["description"] = "Tampered"
    with pytest.raises(boundary.BoundaryError, match="digest mismatch"):
        boundary._validate_handoff(value)


def test_external_anchor_detects_self_consistent_artifact_rewrite(tmp_path: Path) -> None:
    value = _handoff(tmp_path)
    value["handoff_digest"] = boundary._sha256(value)
    trusted_digest = str(value["handoff_digest"])
    value["description"] = "Attacker rewrote artifact"
    value.pop("handoff_digest")
    value["handoff_digest"] = boundary._sha256(value)
    boundary._validate_handoff(value)
    with pytest.raises(boundary.BoundaryError, match="trusted PREPARE output"):
        boundary._assert_expected(str(value["handoff_digest"]), trusted_digest, "handoff digest")


def test_sealed_root_resolution_never_trusts_recorded_or_traversing_paths(
    tmp_path: Path,
) -> None:
    base = tmp_path / "runner-temp"
    sealed = base / "births" / "example"
    sealed.mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    handoff = _handoff(elsewhere)
    assert boundary._resolve_root(handoff, None, base) == sealed.resolve()
    assert boundary._resolve_root(handoff, sealed, base) == sealed.resolve()
    with pytest.raises(boundary.BoundaryError, match="must stay inside"):
        boundary._resolve_root(handoff, elsewhere, base)
    for repository in ("Quantum-L9/..", "Quantum-L9/../../etc", "/absolute", "Quantum-L9/"):
        handoff["repository"] = repository
        with pytest.raises(boundary.BoundaryError, match="plain owner/name"):
            boundary._resolve_root(handoff, None, base)
    handoff["repository"] = "Quantum-L9/missing"
    with pytest.raises(boundary.BoundaryError, match="not materialized"):
        boundary._resolve_root(handoff, None, base)


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


@pytest.mark.skipif(os.name == "nt", reason="the counterexample is a POSIX shell fsmonitor hook")
def test_verify_sealed_rebuilds_config_before_archived_git_config_can_execute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduce the audit counterexample, then prove privileged verify defeats it."""
    root, head, tree = _sealed_repo(tmp_path)
    marker = tmp_path / "product-observed.txt"
    hook = root / "fsmon.sh"
    hook.write_text(
        "#!/bin/sh\n"
        f'printf "ran token=%s\\n" "${engine.PRIVILEGED_TOKEN_ENV}" >> "{marker}"\n'
        'printf "/"\n',
        encoding="utf-8",
    )
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "with hook"], cwd=root, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
    subprocess.run(["git", "config", "core.fsmonitor", "./fsmon.sh"], cwd=root, check=True)
    monkeypatch.setenv(engine.PRIVILEGED_TOKEN_ENV, "fake-publication-token")

    # Counterexample: plain git status with the archived config runs the script
    # and the script sees the publication token.
    subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True)
    assert "token=fake-publication-token" in marker.read_text(encoding="utf-8")
    marker.unlink()

    engine.verify_sealed(root, head, tree)
    assert not marker.exists()
    config = (root / ".git" / "config").read_text(encoding="utf-8")
    assert "fsmon.sh" not in config
    assert "fsmonitor = false" in config


def test_verify_sealed_refuses_root_without_git_directory(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    with pytest.raises(engine.BirthError, match="no .git directory"):
        engine.verify_sealed(root, "0" * 40, "0" * 40)


def _spawn_surviving_daemon(marker: Path) -> None:
    """Model a payload whose validation leaves a background process behind."""
    script = marker.parent / "daemon.sh"
    script.write_text('#!/bin/sh\necho $$ > "$1"\nexec sleep 300\n', encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    subprocess.run(
        [
            "sh",
            "-c",
            'setsid "$1" "$2" </dev/null >/dev/null 2>&1 & exit 0',
            "sh",
            str(script),
            str(marker),
        ],
        check=True,
    )
    for _ in range(100):
        if marker.is_file() and marker.read_text(encoding="utf-8").strip():
            return
        time.sleep(0.01)
    raise AssertionError("daemon never reported its pid")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return Path(f"/proc/{pid}").is_dir() and "zombie" not in Path(f"/proc/{pid}/status").read_text(
        encoding="utf-8"
    )


@linux_only
def test_isolation_sweep_terminates_surviving_product_descendants(tmp_path: Path) -> None:
    engine._become_subreaper()
    marker = tmp_path / "daemon.pid"
    _spawn_surviving_daemon(marker)
    daemon = int(marker.read_text(encoding="utf-8").strip())
    assert _alive(daemon)
    assert daemon in engine.product_descendants()
    killed = engine.terminate_product_descendants()
    assert killed >= 1
    assert engine.product_descendants() == []
    assert not _alive(daemon)


def _cfg(tmp_path: Path, *, remote: bool) -> object:
    return engine.BirthConfig(
        org="Quantum-L9",
        repo="example",
        pkg="example",
        desc="Example",
        work_dir=tmp_path,
        payload=None,
        payload_contract=None,
        template_src=tmp_path,
        org_profile_src=tmp_path,
        repo_class=engine.BIRTH_PROFILE_CLASS,
        remote=remote,
        private=True,
        keep=True,
        receipt_path=None,
        bootstrap_timeout=1,
    )


@linux_only
def test_prepare_terminates_product_descendants_before_seal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "daemon.pid"
    observed: dict[str, object] = {}

    def noop(*_args, **_kwargs) -> None:
        return None

    def validate_with_survivor(_cfg, _receipt) -> None:
        _spawn_surviving_daemon(marker)

    def seal_observing_descendants(_cfg, _receipt, *, git=None) -> dict[str, str]:
        observed["descendants"] = engine.product_descendants()
        observed["git"] = git
        return {"root_commit_sha": "a" * 40, "root_tree_sha": "b" * 40}

    receipt = engine.BirthReceipt()
    monkeypatch.setattr(engine, "new_receipt", lambda _cfg: receipt)
    for stage in ("stage_preflight", "stage_assemble", "stage_finalize", "stage_stamp_provenance"):
        monkeypatch.setattr(engine, stage, noop)
    monkeypatch.setattr(engine, "stage_apply_org_profile", lambda _cfg, _receipt: {"name": "x"})
    monkeypatch.setattr(engine, "stage_validate", validate_with_survivor)
    monkeypatch.setattr(engine, "seal", seal_observing_descendants)
    monkeypatch.setattr(engine, "_write_receipt", noop)

    engine.prepare(_cfg(tmp_path, remote=False))

    daemon = int(marker.read_text(encoding="utf-8").strip())
    assert observed["descendants"] == []
    assert isinstance(observed["git"], engine.TrustedTool)
    assert not _alive(daemon)
    isolation = [stage for stage in receipt.stages if stage.key == "prepare.isolation"]
    assert isolation
    assert isolation[0].status == "PASS"


@linux_only
def test_boundary_refuses_anchor_and_handoff_while_product_descendant_survives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "daemon.pid"
    anchor = tmp_path / "github-output"
    anchor.write_text("", encoding="utf-8")
    handoff = tmp_path / "work" / "birth-handoff.json"
    receipt = engine.BirthReceipt()

    def prepare_with_survivor(_cfg):
        engine._become_subreaper()
        _spawn_surviving_daemon(marker)
        return receipt, {"name": "x"}, {"root_commit_sha": "a" * 40, "root_tree_sha": "b" * 40}

    cfg = _cfg(tmp_path / "work" / "births", remote=False)
    monkeypatch.setattr(engine, "parse_args", lambda argv: argv)
    monkeypatch.setattr(engine, "build_config", lambda _argv: cfg)
    monkeypatch.setattr(engine, "prepare", prepare_with_survivor)
    monkeypatch.setenv("GITHUB_OUTPUT", str(anchor))
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    args = argparse.Namespace(
        repo="example",
        pkg="example",
        desc="Example",
        org="Quantum-L9",
        payload=None,
        payload_contract=None,
        work_dir=tmp_path / "work" / "births",
        template_src=tmp_path,
        org_profile_src=tmp_path,
        repo_class=engine.BIRTH_PROFILE_CLASS,
        private=True,
        bootstrap_timeout=1,
        handoff=handoff,
    )
    try:
        with pytest.raises(engine.BirthError, match="product descendants are still alive"):
            boundary.prepare(args)
    finally:
        engine.terminate_product_descendants()
    assert anchor.read_text(encoding="utf-8") == ""
    assert not handoff.exists()


def test_boundary_confines_handoff_path_to_the_trusted_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner-temp"))
    (tmp_path / "runner-temp").mkdir()
    inside = boundary._confine(
        tmp_path / "runner-temp" / "birth-handoff.json",
        boundary._trusted_base(tmp_path),
        "handoff path",
    )
    assert inside == (tmp_path / "runner-temp" / "birth-handoff.json").resolve()
    with pytest.raises(boundary.BoundaryError, match="must stay inside"):
        boundary._confine(
            tmp_path / "runner-temp" / ".." / "escape.json",
            boundary._trusted_base(tmp_path),
            "handoff path",
        )


def test_boundary_hides_github_output_before_product_execution() -> None:
    source = BOUNDARY_MODULE.read_text(encoding="utf-8")
    hide = source.index('os.environ.pop("GITHUB_OUTPUT", None)')
    product_execution = source.index("nr.prepare(cfg)")
    guard = source.index('nr.assert_no_product_descendants("PREPARE anchor")')
    anchor = source.index("_write_prepare_anchor(handoff, github_output)")
    assert hide < product_execution < guard < anchor


def test_engine_isolates_before_product_stages_and_sweeps_before_seal() -> None:
    source = ENGINE_MODULE.read_text(encoding="utf-8")
    prepare_body = source[source.index("def prepare(") :]
    bind = prepare_body.index("git = bind_git(cfg)")
    subreaper = prepare_body.index("isolated = _become_subreaper()")
    first_stage = prepare_body.index("stage_preflight(cfg, receipt)")
    validate = prepare_body.index("stage_validate(cfg, receipt)")
    sweep = prepare_body.index("terminate_product_descendants()")
    seal = prepare_body.index("seal(cfg, receipt, git=git)")
    assert bind < subreaper < first_stage < validate < sweep < seal


def test_boundary_ast_contains_no_effect_orchestration() -> None:
    tree = ast.parse(BOUNDARY_MODULE.read_text(encoding="utf-8"))
    forbidden_imports = {"subprocess", "shutil", "socket", "urllib", "requests"}
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & forbidden_imports)
    source = BOUNDARY_MODULE.read_text(encoding="utf-8")
    forbidden_markers = (
        "stage_finalize",
        "stage_validate",
        "def publish_root",
        "QUARANTINED_PARTIAL_CREATE",
        "PUBLISH_FAILED_NO_REMOTE",
    )
    for marker in forbidden_markers:
        assert marker not in source


def test_engine_is_only_transition_owner() -> None:
    engine_text = ENGINE_MODULE.read_text(encoding="utf-8")
    boundary_text = BOUNDARY_MODULE.read_text(encoding="utf-8")
    for owner in ("prepare", "seal", "publish", "all"):
        assert f"def {owner}(" in engine_text
    assert "nr.prepare(cfg)" in boundary_text
    assert "nr.publish(" in boundary_text
    assert len(boundary_text.splitlines()) < len(engine_text.splitlines())


def test_legacy_module_has_no_executable_birth_path() -> None:
    tree = ast.parse(LEGACY_MODULE.read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "main" not in defined
    assert "stage_create" not in defined
    for node in tree.body:
        if isinstance(node, ast.If):
            assert "__main__" not in ast.dump(node.test)
    source = LEGACY_MODULE.read_text(encoding="utf-8")
    normalized = " ".join(source.split())
    assert "__main__" not in source
    assert "stage_create(" not in source
    assert '"gh", "repo", "create"' not in normalized
    assert "def publish_root" not in source


def test_legacy_module_executed_directly_births_nothing(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            "-I",
            str(LEGACY_MODULE),
            "--repo",
            "example",
            "--pkg",
            "example",
            "--desc",
            "Example",
            "--work-dir",
            str(work),
            "--no-remote",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "GH_TOKEN": "fake-publication-token"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "BIRTH" not in proc.stdout + proc.stderr
    assert "birth receipt" not in proc.stdout
    assert list(work.iterdir()) == []


def test_direct_remote_path_hides_token_during_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path, remote=True)
    receipt = engine.BirthReceipt()

    def fake_prepare(local_cfg):
        assert local_cfg.remote is False
        assert engine.PRIVILEGED_TOKEN_ENV not in os.environ
        assert "GH_TOKEN" not in os.environ
        return receipt, {}, {"root_commit_sha": "a" * 40, "root_tree_sha": "b" * 40}

    def fake_publish(_cfg, _receipt, _profile, *, root_sha, tree_sha):
        assert root_sha == "a" * 40
        assert tree_sha == "b" * 40
        assert os.environ[engine.PRIVILEGED_TOKEN_ENV] == "secret"
        return receipt

    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setattr(engine, "prepare", fake_prepare)
    monkeypatch.setattr(engine, "publish", fake_publish)
    monkeypatch.setattr(engine, "_trusted_control_path", lambda: "/usr/bin")
    assert engine.all(cfg) is receipt
    assert os.environ["GH_TOKEN"] == "secret"
    assert engine.PRIVILEGED_TOKEN_ENV not in os.environ


def test_publish_verifies_with_control_git_before_any_privileged_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, head, tree = _sealed_repo(tmp_path)
    subprocess.run(["git", "config", "core.fsmonitor", "./product-script"], cwd=root, check=True)
    cfg = engine.BirthConfig(
        org="Quantum-L9",
        repo="repo",
        pkg="example",
        desc="Example",
        work_dir=tmp_path,
        payload=None,
        payload_contract=None,
        template_src=tmp_path,
        org_profile_src=tmp_path,
        repo_class=engine.BIRTH_PROFILE_CLASS,
        remote=True,
        private=True,
        keep=True,
        receipt_path=None,
        bootstrap_timeout=1,
    )
    receipt = engine.BirthReceipt()
    order: list[str] = []
    real_git = Path(subprocess.check_output(["sh", "-c", "command -v git"], text=True).strip())
    control = tmp_path / "control"
    control.mkdir()
    # A symlink would resolve outside the control root and be refused; the
    # trusted tool must be a real file inside it.
    (control / "git").write_text(f'#!/bin/sh\nexec "{real_git.resolve()}" "$@"\n', encoding="utf-8")
    (control / "git").chmod((control / "git").stat().st_mode | stat.S_IXUSR)
    (control / "gh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (control / "gh").chmod((control / "gh").stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv(engine.CONTROL_PATH_ENV, str(control))
    monkeypatch.setenv(engine.PRIVILEGED_TOKEN_ENV, "secret")

    real_verify = engine.verify_sealed

    def observing_verify(path, root_sha, tree_sha, *, git=None):
        order.append("verify")
        assert isinstance(git, engine.TrustedTool)
        assert git.path == str((control / "git").resolve())
        real_verify(path, root_sha, tree_sha, git=git)

    def stop_publish(*_args, **_kwargs):
        order.append("publish_root")
        raise engine.BirthError("stop before any remote call")

    monkeypatch.setattr(engine, "verify_sealed", observing_verify)
    monkeypatch.setattr(engine, "publish_root", stop_publish)
    monkeypatch.setattr(engine, "_write_receipt", lambda *_a, **_k: None)
    with pytest.raises(engine.BirthError, match="stop before any remote call"):
        engine.publish(cfg, receipt, {}, root_sha=head, tree_sha=tree)
    assert order == ["verify", "publish_root"]
    assert "product-script" not in (root / ".git" / "config").read_text(encoding="utf-8")


def test_workflow_crosses_fresh_runner_before_privilege_and_binds_tools() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "jobs:\n  prepare:" in text
    assert "\n  publish:" in text
    assert "needs: prepare" in text
    assert "environment: repo-birth" in text.split("\n  publish:", 1)[1]
    assert "environment: repo-birth" not in text.split("\n  publish:", 1)[0]
    verify = text.index("Verify sealed artifact against PREPARE job outputs")
    bind = text.index("Bind trusted control-plane executables before authority exists")
    mint = text.index("Mint privileged publication token after verification")
    publish = text.index("PUBLISH exact sealed root and remotely attest")
    assert verify < bind < mint < publish
    assert 'export PATH="$L9_BIRTH_CONTROL_PATH"' in text


def test_workflow_separates_source_and_publish_authority() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    prepare_text, publish_text = text.split("\n  publish:", 1)
    assert "BIRTH_SOURCE_APP_ID" in prepare_text
    assert "BIRTH_SOURCE_APP_PRIVATE_KEY" in prepare_text
    assert "permission-contents: read" in prepare_text
    assert "BIRTH_APP_ID" not in prepare_text
    assert "BIRTH_APP_PRIVATE_KEY" not in prepare_text
    assert "BIRTH_APP_ID" in publish_text
    assert "permission-administration: write" in publish_text


def test_workflow_anchors_from_prepare_step_not_later_artifact_read() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "id: prepare_birth" in text
    assert "steps.prepare_birth.outputs.handoff_digest" in text
    assert "steps.prepare_birth.outputs.root_sha" in text
    assert "steps.prepare_birth.outputs.tree_sha" in text
    assert "Anchor sealed state outside uploaded artifact" not in text


def test_workflow_run_blocks_take_no_inline_expressions() -> None:
    """Every ``${{ }}`` value reaches a shell through ``env:``, never by splicing."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    offenders = [
        f"{job_name}:{step.get('name') or step.get('id')}"
        for job_name, job in document["jobs"].items()
        for step in job["steps"]
        if "run" in step and "${{" in step["run"]
    ]
    assert offenders == []


def test_workflow_uses_trusted_venv_and_full_action_pins() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert ".venv/bin/python -I scripts/birth-runner/birth_boundary.py verify" in text
    assert ".venv/bin/python -I scripts/birth-runner/birth_boundary.py publish" in text
    for line in text.splitlines():
        if "uses:" in line and "actions/" in line:
            ref = line.rsplit("@", 1)[-1].strip()
            assert len(ref) == 40
            assert all(ch in "0123456789abcdef" for ch in ref)
