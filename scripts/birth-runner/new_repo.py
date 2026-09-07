#!/usr/bin/env python3
"""Canonical L9 repository-birth engine.

This module owns the birth state machine. Concern-specific stage implementations
remain isolated in ``new_repo_legacy.py`` during PR #34, but that module is not
an independently invokable orchestrator. Both ``make new-repo`` and the dispatch
adapter enter only through the phase functions defined here:

    prepare() -> seal() -> publish()
                     \-> all()  (local/debug compatibility topology)

Production dispatch crosses a fresh-runner boundary between seal and publish.
No product-controlled process is executed by publish().
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any


def _load_stages():
    path = Path(__file__).resolve().parent / "new_repo_legacy.py"
    spec = importlib.util.spec_from_file_location("l9_birth_stages", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load birth stages at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_stages = _load_stages()
for _name in dir(_stages):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_stages, _name)

PRIVILEGED_TOKEN_ENV = "L9_BIRTH_PRIVILEGED_TOKEN"
CONTROL_PATH_ENV = "L9_BIRTH_CONTROL_PATH"
ALLOWED_PUBLISH_TOOLS = frozenset({"git", "gh"})


def new_receipt(cfg: BirthConfig) -> BirthReceipt:
    receipt = BirthReceipt(
        org=cfg.org,
        repository=cfg.repo,
        package=cfg.pkg,
        description=cfg.desc,
        payload=str(cfg.payload) if cfg.payload else "",
        workdir=str(cfg.dest),
        born_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    receipt.template_sha = git_head(cfg.template_src)
    version_file = cfg.template_src / prov.TEMPLATE_VERSION_PATH
    if version_file.is_file():
        receipt.template_version = version_file.read_text(encoding="utf-8").strip()
    return receipt


def assert_prepare_unprivileged() -> None:
    if (os.environ.get(PRIVILEGED_TOKEN_ENV) or "").strip():
        raise BirthError(
            f"{PRIVILEGED_TOKEN_ENV} must not exist during PREPARE; "
            "publication authority is introduced only after seal"
        )


def sanitized_control_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key not in {"GH_TOKEN", "GITHUB_TOKEN"}
    }
    if extra:
        env.update(extra)
    return env


def sanitize_git_config(root: Path) -> None:
    config = root / ".git" / "config"
    if not config.is_file():
        raise BirthError("prepared repository has no .git/config")
    filemode = "true" if os.name != "nt" else "false"
    config.write_text(
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        f"\tfilemode = {filemode}\n"
        "\tbare = false\n"
        "\tlogallrefupdates = true\n"
        f"\thooksPath = {os.devnull}\n",
        encoding="utf-8",
    )


def seal(cfg: BirthConfig, receipt: BirthReceipt) -> dict[str, str]:
    """Seal the validated newborn into one root commit before privilege exists."""
    assert_prepare_unprivileged()
    sanitize_git_config(cfg.dest)
    run(["git", "add", "-A"], cwd=cfg.dest, env=sanitized_control_env())
    message = "\n".join(
        [
            f"chore: birth {cfg.slug} from l9-repo-template@{receipt.template_sha[:12]}",
            "",
            *prov.commit_trailers(receipt.birth_receipt),
        ]
    )
    run(
        [
            "git",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "user.name=L9 Birth Runner",
            "-c",
            "user.email=noreply@quantum-l9.invalid",
            "commit",
            "-q",
            "-m",
            message,
        ],
        cwd=cfg.dest,
        env=sanitized_control_env(),
    )
    root_sha = run(
        ["git", "rev-parse", "HEAD"], cwd=cfg.dest, env=sanitized_control_env()
    ).stdout.strip()
    tree_sha = run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=cfg.dest, env=sanitized_control_env()
    ).stdout.strip()
    parents = run(
        ["git", "rev-list", "--parents", "-n", "1", "HEAD"],
        cwd=cfg.dest,
        env=sanitized_control_env(),
    ).stdout.split()
    if len(parents) != 1:
        raise BirthError("sealed birth commit is not a root commit")
    if run(
        ["git", "status", "--porcelain"], cwd=cfg.dest, env=sanitized_control_env()
    ).stdout.strip():
        raise BirthError("prepared repository is dirty after root seal")
    receipt.head_sha = root_sha
    _verify_provenance(cfg, receipt, "seal.provenance", "sealed birth record proved")
    return {"root_commit_sha": root_sha, "root_tree_sha": tree_sha}


def prepare(
    cfg: BirthConfig, receipt: BirthReceipt | None = None
) -> tuple[BirthReceipt, dict[str, Any], dict[str, str]]:
    """Run every product-controlled stage, validate, and seal exact Git state."""
    assert_prepare_unprivileged()
    receipt = receipt or new_receipt(cfg)
    stage_preflight(cfg, receipt)
    stage_assemble(cfg, receipt)
    stage_finalize(cfg, receipt)
    profile = stage_apply_org_profile(cfg, receipt)
    stage_stamp_provenance(cfg, receipt, profile)
    stage_validate(cfg, receipt)
    sealed = seal(cfg, receipt)
    receipt.state = "SEALED"
    _write_receipt(cfg, receipt)
    return receipt, profile, sealed


def verify_sealed(root: Path, root_sha: str, tree_sha: str) -> None:
    """Verify PREPARE output as untrusted data on the fresh publish runner."""
    env = sanitized_control_env()
    head = run(["git", "rev-parse", "HEAD"], cwd=root, env=env).stdout.strip()
    if head != root_sha:
        raise BirthError("prepared HEAD changed after seal")
    tree = run(["git", "rev-parse", "HEAD^{tree}"], cwd=root, env=env).stdout.strip()
    if tree != tree_sha:
        raise BirthError("prepared tree changed after seal")
    if run(["git", "status", "--porcelain"], cwd=root, env=env).stdout.strip():
        raise BirthError("prepared working tree changed after seal")
    hooks = run(
        ["git", "config", "--local", "--get", "core.hooksPath"],
        cwd=root,
        check=False,
        env=env,
    )
    if hooks.returncode != 0 or (hooks.stdout or "").strip() != os.devnull:
        raise BirthError("prepared repository does not disable Git hooks")


def _resolve_control_tool(tool: str) -> str:
    if tool not in ALLOWED_PUBLISH_TOOLS:
        raise BirthError(f"PUBLISH refused non-control-plane executable: {tool}")
    roots = [
        Path(value).resolve()
        for value in os.environ.get(CONTROL_PATH_ENV, "").split(os.pathsep)
        if value
    ]
    if not roots:
        raise BirthError(f"{CONTROL_PATH_ENV} must be bound before privileged PUBLISH")
    for root in roots:
        candidate = (root / tool).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise BirthError(f"trusted {tool} executable is not present in {CONTROL_PATH_ENV}")


def control_run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    tool = Path(cmd[0]).name
    executable = _resolve_control_tool(tool)
    merged = sanitized_control_env()
    merged["PATH"] = os.environ.get(CONTROL_PATH_ENV, "")
    token = (os.environ.get(PRIVILEGED_TOKEN_ENV) or "").strip()
    if token:
        merged["GH_TOKEN"] = token
    if env:
        merged.update({key: value for key, value in env.items() if key not in {"GH_TOKEN", "PATH"}})
    proc = subprocess.run(
        [executable, *cmd[1:]],
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=capture,
        text=True,
        env=merged,
    )
    if check and proc.returncode != 0:
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip()
        raise BirthError(f"{' '.join(cmd)} failed ({proc.returncode})\n{detail[-1600:]}")
    return proc


def _remote_head_control(slug: str) -> str | None:
    proc = control_run(
        ["gh", "api", f"repos/{slug}/commits/main", "--jq", ".sha"], check=False
    )
    value = (proc.stdout or "").strip()
    return value if SHA_RE.match(value) else None


def publish_root(cfg: BirthConfig, receipt: BirthReceipt, root_sha: str) -> None:
    """Create/recover the remote and publish only the exact sealed root."""
    existing = control_run(["gh", "repo", "view", cfg.slug, "--json", "name"], check=False)
    if existing.returncode == 0:
        head = _remote_head_control(cfg.slug)
        if head == root_sha:
            receipt.record("github.create", "repository created", "PASS", "already exact")
            receipt.record("github.push", "initial push", "PASS", root_sha[:12])
            return
        state = "QUARANTINED_PARTIAL_CREATE" if head is None else "CONFLICT"
        receipt.state = state
        raise BirthError(f"{cfg.slug} already exists but sealed root cannot be proven ({state})")

    visibility = "--private" if cfg.private else "--public"
    proc = control_run(
        [
            "gh",
            "repo",
            "create",
            cfg.slug,
            visibility,
            "--description",
            cfg.desc,
            "--source",
            str(cfg.dest),
            "--remote",
            "origin",
            "--push",
        ],
        check=False,
    )
    if proc.returncode == 0:
        receipt.record("github.create", "repository created", "PASS", cfg.slug)
        receipt.record("github.push", "initial push", "PASS", root_sha[:12])
        return
    probe = control_run(["gh", "repo", "view", cfg.slug, "--json", "name"], check=False)
    if probe.returncode != 0:
        receipt.state = "PUBLISH_FAILED_NO_REMOTE"
        raise BirthError("publication failed and target repository is absent; safe to retry")
    head = _remote_head_control(cfg.slug)
    if head == root_sha:
        receipt.record(
            "github.create", "repository created", "PASS", "recovered after command failure"
        )
        receipt.record("github.push", "initial push", "PASS", root_sha[:12])
        return
    receipt.state = "QUARANTINED_PARTIAL_CREATE"
    raise BirthError(
        "repository exists after failed publication but exact sealed root is not present"
    )


def publish(
    cfg: BirthConfig,
    receipt: BirthReceipt,
    profile: dict[str, Any],
    *,
    root_sha: str,
    tree_sha: str,
) -> BirthReceipt:
    """Publish and remotely attest a previously sealed root."""
    if not (os.environ.get(PRIVILEGED_TOKEN_ENV) or "").strip():
        raise BirthError(f"{PRIVILEGED_TOKEN_ENV} is required for PUBLISH")
    _resolve_control_tool("git")
    _resolve_control_tool("gh")
    verify_sealed(cfg.dest, root_sha, tree_sha)
    original_run = _stages.run
    _stages.run = control_run
    try:
        publish_root(cfg, receipt, root_sha)
        receipt.state = canonical_ci.PROVISIONAL
        stage_remote_bootstrap(cfg, receipt, profile)
        stage_verify_ci_enrollment(cfg, receipt)
        stage_attest(cfg, receipt, profile)
        receipt.state = (
            canonical_ci.PROVISIONAL if not receipt.failed else canonical_ci.QUARANTINED
        )
        receipt.ci["state"] = receipt.state
    except (BirthError, prov.ProvenanceError, canonical_ci.CanonicalCIError) as exc:
        receipt.record("birth.error", "birth", "FAIL", str(exc).splitlines()[0][:120])
        if receipt.state == canonical_ci.PROVISIONAL:
            receipt.state = canonical_ci.QUARANTINED
        receipt.ci["state"] = receipt.state
        raise
    finally:
        _stages.run = original_run
        _write_receipt(cfg, receipt)
    return receipt


def _trusted_control_path() -> str:
    """Capture trusted tool locations before any product-controlled execution."""
    tools: list[str] = []
    for name in ("git", "gh"):
        resolved = shutil.which(name)
        if not resolved:
            raise BirthError(f"{name} not found on PATH")
        tools.append(str(Path(resolved).resolve().parent))
    return os.pathsep.join(dict.fromkeys(tools))


def all(cfg: BirthConfig) -> BirthReceipt:
    """Local/debug compatibility topology using the same canonical phases.

    Production must use the fresh-runner workflow. For the direct Makefile path,
    capture publication authority and trusted control tools before PREPARE, remove
    all publication credentials from the environment while product code runs,
    then restore authority only after the sealed root exists.
    """
    control_path = _trusted_control_path()
    saved = {
        PRIVILEGED_TOKEN_ENV: os.environ.pop(PRIVILEGED_TOKEN_ENV, None),
        "GH_TOKEN": os.environ.pop("GH_TOKEN", None),
        "GITHUB_TOKEN": os.environ.pop("GITHUB_TOKEN", None),
    }
    local_cfg = replace(cfg, remote=False) if cfg.remote else cfg
    try:
        receipt, profile, sealed = prepare(local_cfg)
    finally:
        # PREPARE never receives publication credentials, even if validation
        # launches descendants. Restore them only after PREPARE has terminated.
        pass

    if not cfg.remote:
        receipt.record("github.create", "repository created", "SKIP", "--no-remote")
        receipt.state = canonical_ci.LOCAL
        _write_receipt(cfg, receipt)
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value
        return receipt

    token = saved[PRIVILEGED_TOKEN_ENV] or saved["GH_TOKEN"] or saved["GITHUB_TOKEN"]
    if not token:
        raise BirthError(
            "remote all() requires GitHub publication authority; "
            "production callers should use the two-job dispatch boundary"
        )
    os.environ[PRIVILEGED_TOKEN_ENV] = token
    os.environ[CONTROL_PATH_ENV] = control_path
    try:
        return publish(
            cfg,
            receipt,
            profile,
            root_sha=sealed["root_commit_sha"],
            tree_sha=sealed["root_tree_sha"],
        )
    finally:
        os.environ.pop(PRIVILEGED_TOKEN_ENV, None)
        os.environ.pop(CONTROL_PATH_ENV, None)
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def main(argv: list[str] | None = None) -> int:
    try:
        cfg = build_config(parse_args(argv))
        receipt = all(cfg)
    except (BirthError, prov.ProvenanceError, canonical_ci.CanonicalCIError) as exc:
        print(f"BIRTH FAIL: {exc}", file=sys.stderr)
        return 1
    print(render_receipt(receipt))
    return 1 if receipt.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
