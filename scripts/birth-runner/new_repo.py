#!/usr/bin/env python3
"""Canonical L9 repository-birth engine.

This module owns the birth state machine. Concern-specific stage implementations
remain isolated in ``new_repo_legacy.py`` during PR #34, but that module is not
an independently invokable orchestrator. Both ``make new-repo`` and the dispatch
adapter enter only through the phase functions defined here:

    prepare() -> seal() -> publish()
                      `-> all()  (local/debug compatibility topology)

Production dispatch crosses a fresh-runner boundary between seal and publish.
No product-controlled process is executed by publish().

Two isolation rules hold inside the engine itself:

* PREPARE becomes the child subreaper before any product-controlled stage runs,
  so every orphaned product process reparents here instead of escaping to init.
  After validation and before the seal, every surviving descendant is killed
  and the sweep repeats until a full scan finds none. Only then does trusted
  Git seal the root, and only then does the boundary emit the PREPARE anchor.
* Every privileged Git invocation first replaces the archived ``.git/config``
  with the minimal trusted configuration and runs with a pinned environment
  that carries no publication token and no global or system Git configuration.
"""

from __future__ import annotations

import ctypes
import importlib.util
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, replace
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

# Explicit bindings for every stage-module name this engine uses directly, so
# the engine reads as ordinary Python to linters and reviewers rather than
# relying on the dynamic re-export above for its own definitions.
UTC = _stages.UTC
datetime = _stages.datetime
BirthConfig = _stages.BirthConfig
BirthError = _stages.BirthError
BirthReceipt = _stages.BirthReceipt
ORG_PROFILE_REPO = _stages.ORG_PROFILE_REPO
SHA_RE = _stages.SHA_RE
canonical_ci = _stages.canonical_ci
prov = _stages.prov
build_config = _stages.build_config
git_head = _stages.git_head
parse_args = _stages.parse_args
render_receipt = _stages.render_receipt
stage_apply_org_profile = _stages.stage_apply_org_profile
stage_assemble = _stages.stage_assemble
stage_attest = _stages.stage_attest
stage_finalize = _stages.stage_finalize
stage_preflight = _stages.stage_preflight
stage_remote_bootstrap = _stages.stage_remote_bootstrap
stage_stamp_provenance = _stages.stage_stamp_provenance
stage_validate = _stages.stage_validate
stage_verify_ci_enrollment = _stages.stage_verify_ci_enrollment
_verify_provenance = _stages._verify_provenance
_write_receipt = _stages._write_receipt

_legacy_run = _stages.run
_engine = globals()


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """The engine's single subprocess seam.

    Every stage resolves ``run`` through this module, so replacing the
    engine's ``run`` (``publish()`` installs ``control_run``; tests install a
    fake) is the one injection point. The default is the stage module's
    plain runner.
    """
    return _legacy_run(cmd, **kwargs)


def _stage_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return _engine["run"](cmd, **kwargs)


_stages.run = _stage_run

PRIVILEGED_TOKEN_ENV = "L9_BIRTH_PRIVILEGED_TOKEN"
CONTROL_PATH_ENV = "L9_BIRTH_CONTROL_PATH"
ALLOWED_PUBLISH_TOOLS = frozenset({"git", "gh"})
STRIPPED_AUTH_ENV = frozenset({"GH_TOKEN", "GITHUB_TOKEN", PRIVILEGED_TOKEN_ENV})
PR_SET_CHILD_SUBREAPER = 36
PROC = Path("/proc")

CREATE_KEY = "github.create"
CREATE_LABEL = "repository created"
PUSH_KEY = "github.push"
PUSH_LABEL = "initial push"


@dataclass(frozen=True)
class TrustedTool:
    """An executable bound before product code ran, with its file fingerprint."""

    path: str
    fingerprint: tuple[int, int, int, int]


def _fingerprint(path: Path) -> tuple[int, int, int, int]:
    info = path.stat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _mutable_birth_roots(cfg: BirthConfig | None) -> list[Path]:
    roots: list[Path] = []
    for key in ("RUNNER_TEMP", "GITHUB_WORKSPACE"):
        value = os.environ.get(key)
        if value:
            roots.append(Path(value).resolve())
    if cfg is not None:
        roots.append(cfg.work_dir.resolve())
    return roots


def bind_git(cfg: BirthConfig | None = None) -> TrustedTool:
    """Bind the Git executable before product code can influence PATH or files."""
    resolved = shutil.which("git")
    if not resolved:
        raise BirthError("git not found on PATH")
    path = Path(resolved).resolve()
    for root in _mutable_birth_roots(cfg):
        if path == root or root in path.parents:
            raise BirthError(f"refusing git executable from mutable birth root: {path}")
    return TrustedTool(path=str(path), fingerprint=_fingerprint(path))


def _assert_tool_unchanged(tool: TrustedTool) -> None:
    if _fingerprint(Path(tool.path)) != tool.fingerprint:
        raise BirthError(f"trusted executable changed after binding: {tool.path}")


def _become_subreaper() -> bool:
    """Reparent every orphaned descendant to this process (Linux only)."""
    if sys.platform != "linux":
        return False
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        raise BirthError(f"cannot become child subreaper: {os.strerror(ctypes.get_errno())}")
    return True


def _process_table() -> dict[int, list[int]]:
    children: dict[int, list[int]] = {}
    for entry in os.listdir(PROC):
        if not entry.isdigit():
            continue
        try:
            stat = (PROC / entry / "stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fields = stat.rpartition(")")[2].split()
        if len(fields) < 2:
            continue
        children.setdefault(int(fields[1]), []).append(int(entry))
    return children


def product_descendants(pid: int | None = None) -> list[int]:
    """Every process descended from ``pid`` according to /proc (Linux only)."""
    if sys.platform != "linux":
        return []
    table = _process_table()
    found: list[int] = []
    queue = [pid or os.getpid()]
    while queue:
        parent = queue.pop()
        for child in table.get(parent, []):
            found.append(child)
            queue.append(child)
    return found


def _reap_children() -> None:
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def terminate_product_descendants(*, rounds: int = 100, settle: float = 0.05) -> int:
    """SIGKILL every descendant until one full scan of /proc finds none.

    The engine is the child subreaper, so a product process that double-forked,
    called ``setsid`` or otherwise tried to outlive validation still reparents
    here and is found by the next scan. A subtree that keeps respawning past
    ``rounds`` fails the birth closed rather than sealing beside a live attacker.
    """
    killed = 0
    for _ in range(rounds):
        victims = product_descendants()
        if not victims:
            return killed
        for pid in victims:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                continue
        killed += len(victims)
        time.sleep(settle)
        _reap_children()
    raise BirthError("product descendants survived the isolation sweep")


def assert_no_product_descendants(context: str) -> None:
    alive = product_descendants()
    if alive:
        raise BirthError(f"{context}: product descendants are still alive: {alive[:8]}")


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
    """The process environment minus inherited Git state and every GitHub token.

    The privileged publication token is stripped too: only ``control_run`` hands
    it to ``gh``, so no Git child process ever carries it.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key not in STRIPPED_AUTH_ENV
    }
    if extra:
        env.update(extra)
    return env


def trusted_git_env() -> dict[str, str]:
    """Sanitized environment pinned so Git reads no global or system config."""
    env = sanitized_control_env()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def sanitize_git_config(root: Path) -> None:
    """Replace the whole local Git configuration with the trusted minimum.

    Hooks, ``core.fsmonitor``, credential helpers, aliases, includes, filters,
    and every other product-writable execution surface live in this file.
    Rewriting it is the boundary; checking individual keys is not.
    """
    git_dir = root / ".git"
    if not git_dir.is_dir():
        raise BirthError("prepared repository has no .git directory")
    config = git_dir / "config"
    if not config.is_file():
        raise BirthError("prepared repository has no .git/config")
    filemode = "true" if os.name != "nt" else "false"
    config.write_text(
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        f"\tfilemode = {filemode}\n"
        "\tbare = false\n"
        "\tlogallrefupdates = true\n"
        "\tfsmonitor = false\n"
        f"\thooksPath = {os.devnull}\n",
        encoding="utf-8",
    )
    worktree_config = git_dir / "config.worktree"
    if worktree_config.exists():
        worktree_config.unlink()


def _git(
    tool: TrustedTool, args: list[str], *, cwd: Path, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run the bound Git executable with an exact trusted environment."""
    _assert_tool_unchanged(tool)
    proc = subprocess.run(
        [tool.path, *args],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        env=trusted_git_env(),
    )
    if check and proc.returncode != 0:
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip()
        raise BirthError(f"git {' '.join(args)} failed ({proc.returncode})\n{detail[-1600:]}")
    return proc


def seal(
    cfg: BirthConfig, receipt: BirthReceipt, *, git: TrustedTool | None = None
) -> dict[str, str]:
    """Seal the validated newborn into one root commit before privilege exists."""
    assert_prepare_unprivileged()
    tool = git or bind_git(cfg)
    sanitize_git_config(cfg.dest)
    _git(tool, ["add", "-A"], cwd=cfg.dest)
    message = "\n".join(
        [
            f"chore: birth {cfg.slug} from l9-repo-template@{receipt.template_sha[:12]}",
            "",
            *prov.commit_trailers(receipt.birth_receipt),
        ]
    )
    _git(
        tool,
        [
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
    )
    root_sha = _git(tool, ["rev-parse", "HEAD"], cwd=cfg.dest).stdout.strip()
    tree_sha = _git(tool, ["rev-parse", "HEAD^{tree}"], cwd=cfg.dest).stdout.strip()
    parents = _git(tool, ["rev-list", "--parents", "-n", "1", "HEAD"], cwd=cfg.dest).stdout.split()
    if len(parents) != 1:
        raise BirthError("sealed birth commit is not a root commit")
    if _git(tool, ["status", "--porcelain"], cwd=cfg.dest).stdout.strip():
        raise BirthError("prepared repository is dirty after root seal")
    receipt.head_sha = root_sha
    _verify_provenance(cfg, receipt, "seal.provenance", "sealed birth record proved")
    return {"root_commit_sha": root_sha, "root_tree_sha": tree_sha}


def prepare(
    cfg: BirthConfig, receipt: BirthReceipt | None = None
) -> tuple[BirthReceipt, dict[str, Any], dict[str, str]]:
    """Run every product-controlled stage, validate, isolate, and seal exact Git state.

    Trusted Git is bound and this process becomes the child subreaper before the
    first product-controlled stage. After validation every surviving product
    descendant is terminated; nothing product-controlled is alive when the root
    is sealed or when the boundary later emits the PREPARE anchor.
    """
    assert_prepare_unprivileged()
    git = bind_git(cfg)
    isolated = _become_subreaper()
    receipt = receipt or new_receipt(cfg)
    stage_preflight(cfg, receipt)
    stage_assemble(cfg, receipt)
    stage_finalize(cfg, receipt)
    profile = stage_apply_org_profile(cfg, receipt)
    stage_stamp_provenance(cfg, receipt, profile)
    stage_validate(cfg, receipt)
    if isolated:
        killed = terminate_product_descendants()
        receipt.record(
            "prepare.isolation",
            "product isolation",
            "PASS",
            f"{killed} surviving product process(es) terminated before seal",
        )
    else:
        receipt.record(
            "prepare.isolation",
            "product isolation",
            "SKIP",
            "no child-subreaper support on this platform; direct path only",
        )
    sealed = seal(cfg, receipt, git=git)
    receipt.state = "SEALED"
    _write_receipt(cfg, receipt)
    return receipt, profile, sealed


def verify_sealed(
    root: Path, root_sha: str, tree_sha: str, *, git: TrustedTool | None = None
) -> None:
    """Verify PREPARE output as untrusted data with trusted Git configuration.

    The archived ``.git`` directory is product-influenced data. Its configuration
    is replaced before the first Git command runs, so no archived hook, monitor,
    helper, alias, or include can execute, with or without publication authority.
    """
    sanitize_git_config(root)
    tool = git or bind_git()
    head = _git(tool, ["rev-parse", "HEAD"], cwd=root).stdout.strip()
    if head != root_sha:
        raise BirthError("prepared HEAD changed after seal")
    tree = _git(tool, ["rev-parse", "HEAD^{tree}"], cwd=root).stdout.strip()
    if tree != tree_sha:
        raise BirthError("prepared tree changed after seal")
    if _git(tool, ["status", "--porcelain"], cwd=root).stdout.strip():
        raise BirthError("prepared working tree changed after seal")
    hooks = _git(tool, ["config", "--local", "--get", "core.hooksPath"], cwd=root, check=False)
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


def control_git() -> TrustedTool:
    """The Git executable bound through the trusted control path."""
    path = Path(_resolve_control_tool("git"))
    return TrustedTool(path=str(path), fingerprint=_fingerprint(path))


def control_run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a control-plane tool; only ``gh`` ever receives the publication token."""
    tool = Path(cmd[0]).name
    executable = _resolve_control_tool(tool)
    merged = trusted_git_env()
    merged["PATH"] = os.environ.get(CONTROL_PATH_ENV, "")
    token = (os.environ.get(PRIVILEGED_TOKEN_ENV) or "").strip()
    if token and tool == "gh":
        merged["GH_TOKEN"] = token
    if env:
        merged.update(
            {
                key: value
                for key, value in env.items()
                if key not in STRIPPED_AUTH_ENV and key != "PATH" and not key.startswith("GIT_")
            }
        )
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
    proc = control_run(["gh", "api", f"repos/{slug}/commits/main", "--jq", ".sha"], check=False)
    value = (proc.stdout or "").strip()
    return value if SHA_RE.match(value) else None


def publish_root(cfg: BirthConfig, receipt: BirthReceipt, root_sha: str) -> None:
    """Create/recover the remote and publish only the exact sealed root."""
    existing = control_run(["gh", "repo", "view", cfg.slug, "--json", "name"], check=False)
    if existing.returncode == 0:
        head = _remote_head_control(cfg.slug)
        if head == root_sha:
            receipt.record(CREATE_KEY, CREATE_LABEL, "PASS", "already exact")
            receipt.record(PUSH_KEY, PUSH_LABEL, "PASS", root_sha[:12])
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
        receipt.record(CREATE_KEY, CREATE_LABEL, "PASS", cfg.slug)
        receipt.record(PUSH_KEY, PUSH_LABEL, "PASS", root_sha[:12])
        return
    probe = control_run(["gh", "repo", "view", cfg.slug, "--json", "name"], check=False)
    if probe.returncode != 0:
        receipt.state = "PUBLISH_FAILED_NO_REMOTE"
        raise BirthError("publication failed and target repository is absent; safe to retry")
    head = _remote_head_control(cfg.slug)
    if head == root_sha:
        receipt.record(CREATE_KEY, CREATE_LABEL, "PASS", "recovered after command failure")
        receipt.record(PUSH_KEY, PUSH_LABEL, "PASS", root_sha[:12])
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
    git = control_git()
    _resolve_control_tool("gh")
    # Trusted configuration is rebuilt inside verify_sealed before the first
    # privileged Git command; Git children never see the publication token.
    verify_sealed(cfg.dest, root_sha, tree_sha, git=git)
    original_run = _engine["run"]
    _engine["run"] = control_run
    try:
        publish_root(cfg, receipt, root_sha)
        receipt.state = canonical_ci.PROVISIONAL
        stage_remote_bootstrap(cfg, receipt, profile)
        stage_verify_ci_enrollment(cfg, receipt)
        stage_attest(cfg, receipt, profile)
        receipt.state = canonical_ci.PROVISIONAL if not receipt.failed else canonical_ci.QUARANTINED
        receipt.ci["state"] = receipt.state
    except (BirthError, prov.ProvenanceError, canonical_ci.CanonicalCIError) as exc:
        receipt.record("birth.error", "birth", "FAIL", str(exc).splitlines()[0][:120])
        if receipt.state == canonical_ci.PROVISIONAL:
            receipt.state = canonical_ci.QUARANTINED
        receipt.ci["state"] = receipt.state
        raise
    finally:
        _engine["run"] = original_run
        _write_receipt(cfg, receipt)
    return receipt


def _trusted_control_path() -> str:
    """Capture trusted tool locations before any product-controlled execution."""
    directories: list[str] = []
    for name in ("git", "gh"):
        resolved = shutil.which(name)
        if not resolved:
            raise BirthError(f"{name} not found on PATH")
        directories.append(str(Path(resolved).resolve().parent))
    return os.pathsep.join(dict.fromkeys(directories))


def _direct_org_profile(cfg: BirthConfig) -> BirthConfig:
    """Materialize org policy locally before direct PREPARE drops all auth."""
    if cfg.org_profile_src is not None:
        return cfg
    git = shutil.which("git")
    if not git:
        raise BirthError("git not found on PATH")
    dest = cfg.work_dir / ".direct-org-profile"
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            str(Path(git).resolve()),
            "clone",
            "--depth",
            "1",
            f"https://github.com/{ORG_PROFILE_REPO}.git",
            str(dest),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=sanitized_control_env(),
    )
    if proc.returncode != 0:
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip()
        raise BirthError(
            f"cannot materialize organization profile for direct birth: {detail[-1200:]}"
        )
    return replace(cfg, org_profile_src=dest)


def _restore_auth(saved: dict[str, str | None]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def all(cfg: BirthConfig) -> BirthReceipt:
    """Local/debug compatibility topology using the same canonical phases.

    Production must use the fresh-runner workflow. The direct path captures
    publication authority and trusted tools, strips all GitHub auth, materializes
    organization policy locally, runs PREPARE, then restores authority only after
    the exact sealed root exists.
    """
    control_path = _trusted_control_path()
    saved = {
        PRIVILEGED_TOKEN_ENV: os.environ.pop(PRIVILEGED_TOKEN_ENV, None),
        "GH_TOKEN": os.environ.pop("GH_TOKEN", None),
        "GITHUB_TOKEN": os.environ.pop("GITHUB_TOKEN", None),
    }
    try:
        prepared_cfg = _direct_org_profile(cfg) if cfg.remote else cfg
        local_cfg = replace(prepared_cfg, remote=False) if cfg.remote else prepared_cfg
        receipt, profile, sealed = prepare(local_cfg)
    except Exception:
        _restore_auth(saved)
        raise

    if not cfg.remote:
        receipt.record(CREATE_KEY, CREATE_LABEL, "SKIP", "--no-remote")
        receipt.state = canonical_ci.LOCAL
        _write_receipt(cfg, receipt)
        _restore_auth(saved)
        return receipt

    token = saved[PRIVILEGED_TOKEN_ENV] or saved["GH_TOKEN"] or saved["GITHUB_TOKEN"]
    if not token:
        _restore_auth(saved)
        raise BirthError(
            "remote all() requires GitHub publication authority; "
            "production callers should use the two-job dispatch boundary"
        )
    os.environ[PRIVILEGED_TOKEN_ENV] = token
    os.environ[CONTROL_PATH_ENV] = control_path
    publish_cfg = replace(prepared_cfg, remote=True)
    try:
        return publish(
            publish_cfg,
            receipt,
            profile,
            root_sha=sealed["root_commit_sha"],
            tree_sha=sealed["root_tree_sha"],
        )
    finally:
        os.environ.pop(CONTROL_PATH_ENV, None)
        _restore_auth(saved)


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
