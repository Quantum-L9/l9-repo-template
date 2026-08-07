#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import Any, NoReturn

from .authority import AuthorityError, validate_authority
from .change_policy import (
    ChangePolicyError,
    ChangedFileResolution,
    companion_findings,
    resolve_changed_files,
    select_gates,
)
from .contract_wiring import ContractWiringError, validate_contract_wiring
from .locking import LockBusy, single_flight
from .push_preflight import PreflightError, verify as verify_push_preflight
from .reporting import StepEvidence, redact_text, write_reports

COMMANDS = (
    "doctor",
    "change-policy",
    "agent-check",
    "setup",
    "validate",
    "check",
    "test",
    "push",
    "pr",
    "status",
    "clean",
    "reconcile",
    "help",
)
CONFIG_PATH = pathlib.Path(".l9/repo-workflow.json")
SCHEMA_PATH = pathlib.Path(".l9/repo-workflow.schema.json")
TEMPLATE_PATH = pathlib.Path("tools/l9_repo/Makefile.template")

# Semantic version "x.y.z" has exactly three dot-separated components.
_SEMVER_COMPONENT_COUNT = 3
# A `sha256sum`-style manifest line is "<64 hex chars><two spaces><path>".
_SHA256_HEX_LENGTH = 64
_MANIFEST_FIELD_SEPARATOR = "  "
_MANIFEST_PATH_OFFSET = _SHA256_HEX_LENGTH + len(_MANIFEST_FIELD_SEPARATOR)
_MANIFEST_MIN_LINE_LENGTH = _MANIFEST_PATH_OFFSET + 1
# agent-check exits 2 when an infrastructure/configuration failure occurred.
_INFRASTRUCTURE_EXIT_CODE = 2


class AgentCheckFailure(RuntimeError):
    """Raised after all checks run and one or more findings remain."""


class WorkflowError(RuntimeError):
    """Raised when repository workflow configuration or infrastructure is invalid."""


def _fail(message: str) -> NoReturn:
    raise WorkflowError(message)


def _require_dict(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        _fail(f"{path} must be an object")
    return value


def _require_bool(value: object, path: str, *, expected: bool | None = None) -> bool:
    if not isinstance(value, bool):
        _fail(f"{path} must be a boolean")
    if expected is not None and value is not expected:
        _fail(f"{path} must be {str(expected).lower()}")
    return value


def _require_string(value: object, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        _fail(f"{path} must be a {'string' if allow_empty else 'non-empty string'}")
    if "\x00" in value:
        _fail(f"{path} must not contain NUL")
    return value


def _require_int(value: object, path: str, *, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        _fail(f"{path} must be an integer >= {minimum}")
    return value


def _validate_keys(
    value: Mapping[str, object],
    path: str,
    *,
    required: set[str],
    allowed: set[str] | None = None,
) -> None:
    missing = sorted(required - set(value))
    if missing:
        _fail(f"{path} missing keys: {', '.join(missing)}")
    permitted = required if allowed is None else allowed
    extras = sorted(set(value) - permitted)
    if extras:
        _fail(f"{path} has unsupported keys: {', '.join(extras)}")


def _validate_strings(
    value: object,
    path: str,
    *,
    allow_empty_items: bool = False,
    non_empty: bool = True,
) -> list[str]:
    if not isinstance(value, list) or (non_empty and not value):
        _fail(f"{path} must be a {'non-empty ' if non_empty else ''}array")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(
            _require_string(
                item,
                f"{path}[{index}]",
                allow_empty=allow_empty_items,
            )
        )
    if len(set(result)) != len(result):
        _fail(f"{path} must not contain duplicates")
    return result


def _validate_argv(value: object, path: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list):
        _fail(f"{path} must be an argv array")
    if not allow_empty and not value:
        _fail(f"{path} must not be empty")
    return [
        _require_string(item, f"{path}[{index}]") for index, item in enumerate(value)
    ]


def _validate_argv_matrix(value: object, path: str) -> list[list[str]]:
    if not isinstance(value, list) or not value:
        _fail(f"{path} must be a non-empty array of argv arrays")
    return [
        _validate_argv(item, f"{path}[{index}]", allow_empty=False)
        for index, item in enumerate(value)
    ]


def _validate_safe_relative_path(value: object, path: str) -> str:
    text = _require_string(value, path)
    candidate = pathlib.PurePosixPath(text)
    if candidate.is_absolute() or ".." in candidate.parts or text in {".", ""}:
        _fail(f"{path} must be a safe relative path")
    return text


def validate_config_data(data: object) -> dict[str, Any]:
    root = _require_dict(data, "config")
    required = {
        "$schema",
        "schema_version",
        "metadata",
        "authority",
        "repository",
        "commands",
        "push",
        "pull_request",
        "clean_paths",
        "workspace",
        "automation",
        "change_policy",
        "agent_contracts",
        "reporting",
        "status",
    }
    _validate_keys(root, "config", required=required)
    if root["$schema"] != "./repo-workflow.schema.json":
        _fail("config.$schema must be ./repo-workflow.schema.json")
    if root["schema_version"] != 1:
        _fail("unsupported repo-workflow schema_version")

    metadata = _require_dict(root["metadata"], "metadata")
    _validate_keys(
        metadata,
        "metadata",
        required={
            "artifact_id",
            "artifact_version",
            "contract_status",
            "beneficiary",
            "authority_scope",
        },
    )
    if metadata["artifact_id"] != "l9-ci-core-repository-execution-runtime":
        _fail("metadata.artifact_id is not canonical")
    version = _require_string(metadata["artifact_version"], "metadata.artifact_version")
    parts = version.split(".")
    if len(parts) != _SEMVER_COMPONENT_COUNT or not all(
        part.isdigit() for part in parts
    ):
        _fail("metadata.artifact_version must be semantic version x.y.z")
    if metadata["contract_status"] != "authoritative":
        _fail("metadata.contract_status must be authoritative")
    if metadata["beneficiary"] != "Quantum-L9/l9-ci-core":
        _fail("metadata.beneficiary is not canonical")
    if metadata["authority_scope"] != "repository-execution":
        _fail("metadata.authority_scope is not canonical")

    authority = _require_dict(root["authority"], "authority")
    _validate_keys(
        authority,
        "authority",
        required={
            "target_authorities",
            "component_authority",
            "component_schema",
            "generated_artifacts",
            "derived_documents",
            "dependency_manifests",
        },
    )
    for key in ("target_authorities", "generated_artifacts", "derived_documents"):
        paths = _validate_strings(authority[key], f"authority.{key}")
        for index, relative in enumerate(paths):
            _validate_safe_relative_path(relative, f"authority.{key}[{index}]")
    dependencies = _require_dict(
        authority["dependency_manifests"], "authority.dependency_manifests"
    )
    _validate_keys(
        dependencies,
        "authority.dependency_manifests",
        required={"target_required", "component_bundled"},
    )
    for key in ("target_required", "component_bundled"):
        paths = _validate_strings(
            dependencies[key], f"authority.dependency_manifests.{key}"
        )
        for index, relative in enumerate(paths):
            _validate_safe_relative_path(
                relative, f"authority.dependency_manifests.{key}[{index}]"
            )

    if authority["component_authority"] != ".l9/repo-workflow.json":
        _fail("authority.component_authority must be .l9/repo-workflow.json")
    if authority["component_schema"] != ".l9/repo-workflow.schema.json":
        _fail("authority.component_schema must be .l9/repo-workflow.schema.json")

    repository = _require_dict(root["repository"], "repository")
    _validate_keys(
        repository,
        "repository",
        required={"protected_branches", "require_pull_request"},
    )
    protected = _validate_strings(
        repository["protected_branches"], "repository.protected_branches"
    )
    _require_bool(
        repository["require_pull_request"],
        "repository.require_pull_request",
        expected=True,
    )

    commands = _require_dict(root["commands"], "commands")
    command_names = {"setup", "validate", "check", "test"}
    _validate_keys(commands, "commands", required=command_names)
    for name in sorted(command_names):
        _validate_argv_matrix(commands[name], f"commands.{name}")

    push = _require_dict(root["push"], "push")
    push_keys = {
        "run_check",
        "require_clean_worktree",
        "reject_force_push",
        "reject_protected_branch",
        "set_upstream",
        "lockfile_command",
        "rebase_before_push",
    }
    _validate_keys(push, "push", required=push_keys)
    for key in (
        "run_check",
        "require_clean_worktree",
        "reject_force_push",
        "reject_protected_branch",
    ):
        _require_bool(push[key], f"push.{key}", expected=True)
    _require_bool(push["set_upstream"], "push.set_upstream")
    _require_bool(push["rebase_before_push"], "push.rebase_before_push")
    _validate_argv(push["lockfile_command"], "push.lockfile_command", allow_empty=True)

    pull_request = _require_dict(root["pull_request"], "pull_request")
    _validate_keys(
        pull_request,
        "pull_request",
        required={"base", "draft_by_default"},
    )
    base = _require_string(pull_request["base"], "pull_request.base")
    if base not in protected:
        _fail("pull_request.base must be a configured protected branch")
    _require_bool(pull_request["draft_by_default"], "pull_request.draft_by_default")

    clean_paths = _validate_strings(root["clean_paths"], "clean_paths", non_empty=False)
    for index, item in enumerate(clean_paths):
        _validate_safe_relative_path(item, f"clean_paths[{index}]")

    workspace = _require_dict(root["workspace"], "workspace")
    _validate_keys(workspace, "workspace", required={"default", "allow_override"})
    if workspace["default"] != ".":
        _fail("workspace.default must be .")
    _require_bool(
        workspace["allow_override"],
        "workspace.allow_override",
        expected=True,
    )

    automation = _require_dict(root["automation"], "automation")
    _validate_keys(automation, "automation", required={"lock"})
    lock = _require_dict(automation["lock"], "automation.lock")
    _validate_keys(lock, "automation.lock", required={"name", "stale_after_seconds"})
    lock_name = _require_string(lock["name"], "automation.lock.name")
    if lock_name in {".", ".."} or pathlib.PurePath(lock_name).name != lock_name:
        _fail("automation.lock.name must be a safe simple file name")
    _require_int(lock["stale_after_seconds"], "automation.lock.stale_after_seconds")

    change_policy = _require_dict(root["change_policy"], "change_policy")
    _validate_keys(
        change_policy,
        "change_policy",
        required={"gate_order", "gates", "companion_rules"},
    )
    gate_order = _validate_strings(
        change_policy["gate_order"], "change_policy.gate_order"
    )
    gates = _require_dict(change_policy["gates"], "change_policy.gates")
    if set(gate_order) != set(gates):
        _fail("change_policy.gate_order must name every gate exactly once")
    for gate_id in gate_order:
        gate = _require_dict(gates[gate_id], f"change_policy.gates.{gate_id}")
        _validate_keys(
            gate,
            f"change_policy.gates.{gate_id}",
            required={"match_any_prefix", "blocking", "commands"},
        )
        _validate_strings(
            gate["match_any_prefix"],
            f"change_policy.gates.{gate_id}.match_any_prefix",
            allow_empty_items=True,
        )
        _require_bool(gate["blocking"], f"change_policy.gates.{gate_id}.blocking")
        _validate_argv_matrix(
            gate["commands"], f"change_policy.gates.{gate_id}.commands"
        )

    rules = change_policy["companion_rules"]
    if not isinstance(rules, list) or not rules:
        _fail("change_policy.companion_rules must be a non-empty array")
    seen_rules: set[str] = set()
    for index, raw in enumerate(rules):
        rule = _require_dict(raw, f"change_policy.companion_rules[{index}]")
        allowed = {
            "id",
            "match_any_prefix",
            "require_any_prefix",
            "require_all_paths",
            "message",
        }
        required_rule = {"id", "match_any_prefix", "message"}
        _validate_keys(
            rule,
            f"change_policy.companion_rules[{index}]",
            required=required_rule,
            allowed=allowed,
        )
        rule_id = _require_string(
            rule["id"], f"change_policy.companion_rules[{index}].id"
        )
        if rule_id in seen_rules:
            _fail(f"duplicate companion rule id: {rule_id}")
        seen_rules.add(rule_id)
        _validate_strings(
            rule["match_any_prefix"],
            f"change_policy.companion_rules[{index}].match_any_prefix",
            allow_empty_items=True,
        )
        has_requirement = False
        if "require_any_prefix" in rule:
            _validate_strings(
                rule["require_any_prefix"],
                f"change_policy.companion_rules[{index}].require_any_prefix",
                allow_empty_items=True,
            )
            has_requirement = True
        if "require_all_paths" in rule:
            paths = _validate_strings(
                rule["require_all_paths"],
                f"change_policy.companion_rules[{index}].require_all_paths",
            )
            for path_index, relative in enumerate(paths):
                _validate_safe_relative_path(
                    relative,
                    f"change_policy.companion_rules[{index}].require_all_paths[{path_index}]",
                )
            has_requirement = True
        if not has_requirement:
            _fail(
                f"change_policy.companion_rules[{index}] must declare require_any_prefix or require_all_paths"
            )
        _require_string(
            rule["message"], f"change_policy.companion_rules[{index}].message"
        )

    agent_contracts = _require_dict(root["agent_contracts"], "agent_contracts")
    _validate_keys(
        agent_contracts,
        "agent_contracts",
        required={"required_files", "reference_requirements"},
    )
    required_files = _validate_strings(
        agent_contracts["required_files"], "agent_contracts.required_files"
    )
    for index, relative in enumerate(required_files):
        _validate_safe_relative_path(
            relative, f"agent_contracts.required_files[{index}]"
        )
    reference_requirements = agent_contracts["reference_requirements"]
    if not isinstance(reference_requirements, list) or not reference_requirements:
        _fail("agent_contracts.reference_requirements must be a non-empty array")
    for index, raw in enumerate(reference_requirements):
        requirement = _require_dict(
            raw, f"agent_contracts.reference_requirements[{index}]"
        )
        _validate_keys(
            requirement,
            f"agent_contracts.reference_requirements[{index}]",
            required={"target", "instruction_files"},
        )
        _validate_safe_relative_path(
            requirement["target"],
            f"agent_contracts.reference_requirements[{index}].target",
        )
        instruction_files = _validate_strings(
            requirement["instruction_files"],
            f"agent_contracts.reference_requirements[{index}].instruction_files",
        )
        for file_index, relative in enumerate(instruction_files):
            _validate_safe_relative_path(
                relative,
                f"agent_contracts.reference_requirements[{index}].instruction_files[{file_index}]",
            )

    reporting = _require_dict(root["reporting"], "reporting")
    _validate_keys(
        reporting,
        "reporting",
        required={
            "agent_check_json",
            "agent_check_markdown",
            "capture_limit_chars",
        },
    )
    _validate_safe_relative_path(
        reporting["agent_check_json"], "reporting.agent_check_json"
    )
    _validate_safe_relative_path(
        reporting["agent_check_markdown"], "reporting.agent_check_markdown"
    )
    _require_int(
        reporting["capture_limit_chars"],
        "reporting.capture_limit_chars",
        minimum=1000,
    )

    status = _require_dict(root["status"], "status")
    _validate_keys(status, "status", required={"fetch_remote"})
    _require_bool(status["fetch_remote"], "status.fetch_remote")
    return root


def verify_checksum_manifest(
    root: pathlib.Path, relative: str = "MANIFEST.sha256"
) -> None:
    manifest = root / relative
    if manifest.is_symlink() or not manifest.is_file():
        _fail(f"missing checksum manifest: {manifest}")
    errors: list[str] = []
    seen: set[str] = set()
    entries = 0
    for line_number, raw in enumerate(
        manifest.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw.strip():
            continue
        if (
            len(raw) < _MANIFEST_MIN_LINE_LENGTH
            or raw[_SHA256_HEX_LENGTH:_MANIFEST_PATH_OFFSET]
            != _MANIFEST_FIELD_SEPARATOR
        ):
            errors.append(f"{relative}:{line_number}: malformed checksum entry")
            continue
        entries += 1
        digest, name = raw[:_SHA256_HEX_LENGTH], raw[_MANIFEST_PATH_OFFSET:]
        if name in seen:
            errors.append(f"{relative}:{line_number}: duplicate path {name}")
            continue
        seen.add(name)
        if any(ch not in "0123456789abcdef" for ch in digest):
            errors.append(f"{relative}:{line_number}: invalid sha256 digest")
            continue
        candidate = pathlib.PurePosixPath(name)
        if candidate.is_absolute() or ".." in candidate.parts or name in {"", "."}:
            errors.append(f"{relative}:{line_number}: unsafe path {name!r}")
            continue
        path = root / candidate
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            resolved = path.resolve()
        if path.is_symlink() or root.resolve() not in resolved.parents:
            errors.append(f"{relative}:{line_number}: unsafe or symlinked file {name}")
            continue
        if not path.is_file():
            errors.append(f"{relative}:{line_number}: missing file {name}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            errors.append(f"{relative}:{line_number}: checksum mismatch for {name}")
    if entries == 0:
        errors.append(f"{relative}: checksum manifest is empty")
    if errors:
        _fail("checksum manifest validation failed: " + "; ".join(errors))


class RepositoryWorkflow:
    def __init__(self, root: pathlib.Path) -> None:
        self.root = root.resolve()

    def run(
        self,
        argv: Sequence[str],
        *,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(argv),
            cwd=self.root,
            text=True,
            capture_output=capture,
            check=check,
        )

    def git(
        self,
        *args: str,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return self.run(["git", *args], capture=capture, check=check)

    def config(self) -> dict[str, Any]:
        path = self.root / CONFIG_PATH
        if not path.is_file():
            _fail(f"missing {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            _fail(f"invalid {path}: {error}")
        return validate_config_data(data)

    def command_matrix(self, name: str) -> list[list[str]]:
        return _validate_argv_matrix(
            self.config()["commands"][name], f"commands.{name}"
        )

    @staticmethod
    def render_argv(argv: Sequence[str]) -> list[str]:
        return [sys.executable if token == "@python" else token for token in argv]

    def invoke(self, name: str) -> None:
        for configured_argv in self.command_matrix(name):
            argv = self.render_argv(configured_argv)
            print("+", " ".join(argv), flush=True)
            self.run(argv)

    def branch(self) -> str:
        return self.git("branch", "--show-current", capture=True).stdout.strip()

    def status_porcelain(self) -> str:
        return self.git("status", "--porcelain", capture=True).stdout.strip()

    def worktree_fingerprint(self) -> str:
        digest = hashlib.sha256()
        for argv in (
            ("git", "diff", "--binary", "HEAD"),
            ("git", "ls-files", "--others", "--exclude-standard", "-z"),
        ):
            result = subprocess.run(
                list(argv), cwd=self.root, capture_output=True, check=False
            )
            if result.returncode != 0:
                _fail(
                    result.stderr.decode("utf-8", errors="replace").strip()
                    or "unable to fingerprint worktree"
                )
            digest.update(len(result.stdout).to_bytes(8, "big"))
            digest.update(result.stdout)
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=self.root,
            capture_output=True,
            check=False,
        )
        for raw in sorted(path for path in untracked.stdout.split(b"\0") if path):
            try:
                relative = raw.decode("utf-8")
            except UnicodeDecodeError as error:
                _fail(f"non-UTF-8 untracked path: {error}")
            path = self.root / relative
            digest.update(raw)
            if path.is_symlink():
                digest.update(b"SYMLINK")
                digest.update(path.readlink().as_posix().encode("utf-8"))
            elif path.is_file():
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def git_path(self, name: str) -> pathlib.Path:
        value = self.git("rev-parse", "--git-path", name, capture=True).stdout.strip()
        path = pathlib.Path(value)
        return path if path.is_absolute() else (self.root / path).resolve()

    def _lock_settings(self) -> tuple[pathlib.Path, int]:
        lock = self.config()["automation"]["lock"]
        return self.git_path(lock["name"]), lock["stale_after_seconds"]

    def _ensure_repository_root(self) -> None:
        result = self.git("rev-parse", "--show-toplevel", capture=True, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            _fail(
                result.stderr.strip()
                or f"workspace is not a Git repository root: {self.root}"
            )
        actual = pathlib.Path(result.stdout.strip()).resolve()
        if actual != self.root:
            _fail(f"workspace is not repository root: {self.root} != {actual}")

    def _comparison_ref(self, base_ref: str | None = None) -> str:
        if base_ref:
            return base_ref
        return f"origin/{self.config()['pull_request']['base']}"

    def _resolve_changes(
        self,
        *,
        explicit: Sequence[str] = (),
        base_ref: str | None = None,
        head_ref: str = "HEAD",
    ) -> ChangedFileResolution:
        return resolve_changed_files(
            self.root,
            explicit=explicit,
            base_ref=self._comparison_ref(base_ref),
            head_ref=head_ref,
        )

    def doctor(self) -> None:
        self._ensure_repository_root()
        config = self.config()
        required_tools = {"git", "gh"}
        for name in ("setup", "validate", "check", "test"):
            required_tools.update(
                argv[0] for argv in config["commands"][name] if argv[0] != "@python"
            )
        for gate in config["change_policy"]["gates"].values():
            required_tools.update(
                argv[0] for argv in gate["commands"] if argv[0] != "@python"
            )
        lockfile = config["push"]["lockfile_command"]
        if lockfile:
            required_tools.add(lockfile[0])
        missing = sorted(tool for tool in required_tools if not shutil.which(tool))
        if missing:
            _fail("missing tools: " + ", ".join(missing))
        self.run(["gh", "auth", "status"])
        print("doctor: PASS")

    def change_policy(
        self,
        *,
        explicit: Sequence[str] = (),
        base_ref: str | None = None,
        head_ref: str = "HEAD",
    ) -> None:
        self._ensure_repository_root()
        resolution = self._resolve_changes(
            explicit=explicit,
            base_ref=base_ref,
            head_ref=head_ref,
        )
        policy = self.config()["change_policy"]
        findings = companion_findings(policy, resolution.files)
        payload = {
            "schema": "l9.repo-change-policy/v1",
            "change_context": {
                "source": resolution.source,
                "base_ref": resolution.base_ref,
                "head_ref": resolution.head_ref,
            },
            "changed_files": list(resolution.files),
            "selected_gates": [
                gate.gate_id for gate in select_gates(policy, resolution.files)
            ],
            "companion_findings": [
                {
                    "rule_id": finding.rule_id,
                    "message": finding.message,
                    "changed": list(finding.changed),
                    "required_any": list(finding.required_any),
                    "missing_all": list(finding.missing_all),
                }
                for finding in findings
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        if findings:
            raise AgentCheckFailure(
                f"change policy found {len(findings)} blocking companion finding(s)"
            )

    @staticmethod
    def _bounded(text: str, limit: int) -> str:
        text = redact_text(text)
        if len(text) <= limit:
            return text
        return text[:limit] + f"\n... output truncated at {limit} characters ...\n"

    def agent_check(
        self,
        *,
        explicit: Sequence[str] = (),
        base_ref: str | None = None,
        head_ref: str = "HEAD",
    ) -> None:
        self._ensure_repository_root()
        config = self.config()
        resolution = self._resolve_changes(
            explicit=explicit,
            base_ref=base_ref,
            head_ref=head_ref,
        )
        policy = config["change_policy"]
        initial_subject_sha = self.git("rev-parse", "HEAD", capture=True).stdout.strip()
        initial_policy_sha256 = hashlib.sha256(
            (self.root / CONFIG_PATH).read_bytes()
        ).hexdigest()
        initial_worktree_fingerprint = self.worktree_fingerprint()
        companion = companion_findings(policy, resolution.files)
        steps: list[StepEvidence] = []
        finding_failures = len(companion)
        infrastructure_failures = 0
        capture_limit = config["reporting"]["capture_limit_chars"]

        try:
            self.structural_validate()
            steps.append(StepEvidence("structural-validate", tuple(), 0, "pass", True))
        except (WorkflowError, ContractWiringError) as error:
            infrastructure_failures += 1
            steps.append(
                StepEvidence(
                    "structural-validate",
                    tuple(),
                    2,
                    "infrastructure",
                    True,
                    stderr=str(error),
                )
            )

        def run_matrix(
            name: str,
            matrix: Sequence[Sequence[str]],
            *,
            blocking: bool = True,
        ) -> None:
            nonlocal finding_failures, infrastructure_failures
            for index, configured in enumerate(matrix, start=1):
                argv = self.render_argv(configured)
                print("+", " ".join(argv), flush=True)
                try:
                    result = self.run(argv, capture=True, check=False)
                    stdout = self._bounded(result.stdout, capture_limit)
                    stderr = self._bounded(result.stderr, capture_limit)
                    if stdout:
                        print(stdout, end="" if stdout.endswith("\n") else "\n")
                    if stderr:
                        print(
                            stderr,
                            file=sys.stderr,
                            end="" if stderr.endswith("\n") else "\n",
                        )
                    if result.returncode == 0:
                        classification = "pass"
                    elif result.returncode in {2, 126, 127}:
                        classification = "infrastructure"
                        if blocking:
                            infrastructure_failures += 1
                    else:
                        classification = "finding"
                        if blocking:
                            finding_failures += 1
                    steps.append(
                        StepEvidence(
                            f"{name}:{index}",
                            tuple(argv),
                            result.returncode,
                            classification,
                            blocking,
                            stdout=stdout,
                            stderr=stderr,
                        )
                    )
                except OSError as error:
                    infrastructure_failures += int(blocking)
                    steps.append(
                        StepEvidence(
                            f"{name}:{index}",
                            tuple(argv),
                            127,
                            "infrastructure",
                            blocking,
                            stderr=str(error),
                        )
                    )

        run_matrix("validate", config["commands"]["validate"])
        for gate in select_gates(policy, resolution.files):
            run_matrix(
                f"change-gate:{gate.gate_id}",
                gate.commands,
                blocking=gate.blocking,
            )
        run_matrix("check", config["commands"]["check"])
        run_matrix("test", config["commands"]["test"])

        final_subject_sha = self.git("rev-parse", "HEAD", capture=True).stdout.strip()
        final_policy_sha256 = hashlib.sha256(
            (self.root / CONFIG_PATH).read_bytes()
        ).hexdigest()
        final_worktree_fingerprint = self.worktree_fingerprint()
        integrity_errors: list[str] = []
        if final_subject_sha != initial_subject_sha:
            integrity_errors.append("HEAD changed during agent-check")
        if final_policy_sha256 != initial_policy_sha256:
            integrity_errors.append(
                "repository workflow policy changed during agent-check"
            )
        if final_worktree_fingerprint != initial_worktree_fingerprint:
            integrity_errors.append("worktree content changed during agent-check")
        if integrity_errors:
            infrastructure_failures += 1
            steps.append(
                StepEvidence(
                    "non-mutation-check",
                    tuple(),
                    2,
                    "infrastructure",
                    True,
                    stderr="; ".join(integrity_errors),
                )
            )
        else:
            steps.append(StepEvidence("non-mutation-check", tuple(), 0, "pass", True))

        finding_payloads: list[dict[str, object]] = [
            {
                "rule_id": finding.rule_id,
                "message": finding.message,
                "changed": list(finding.changed),
                "required_any": list(finding.required_any),
                "missing_all": list(finding.missing_all),
            }
            for finding in companion
        ]
        if infrastructure_failures:
            overall_exit_code = _INFRASTRUCTURE_EXIT_CODE
        elif finding_failures:
            overall_exit_code = 1
        else:
            overall_exit_code = 0

        json_path = self.root / config["reporting"]["agent_check_json"]
        markdown_path = self.root / config["reporting"]["agent_check_markdown"]
        subject_sha = initial_subject_sha
        policy_sha256 = initial_policy_sha256
        write_reports(
            json_path,
            markdown_path,
            files=resolution.files,
            change_source=resolution.source,
            base_ref=resolution.base_ref,
            head_ref=resolution.head_ref,
            findings=finding_payloads,
            steps=steps,
            overall_exit_code=overall_exit_code,
            subject_sha=subject_sha,
            policy_sha256=policy_sha256,
        )
        evidence = f"{json_path} and {markdown_path}"
        if overall_exit_code == _INFRASTRUCTURE_EXIT_CODE:
            raise WorkflowError(
                f"agent-check encountered {infrastructure_failures} infrastructure/configuration failure(s); evidence: {evidence}"
            )
        if overall_exit_code == 1:
            raise AgentCheckFailure(
                f"agent-check found {finding_failures} blocking finding(s); evidence: {evidence}"
            )
        print(f"agent-check: PASS; evidence: {evidence}")

    def setup(self) -> None:
        self._ensure_repository_root()
        self.invoke("setup")

    def validate(self) -> None:
        self._ensure_repository_root()
        self.structural_validate()
        self.invoke("validate")
        print("validate: PASS")

    def check(self) -> None:
        self._ensure_repository_root()
        self.invoke("check")

    def test(self) -> None:
        self._ensure_repository_root()
        self.invoke("test")

    def structural_validate(self) -> None:
        config = self.config()
        schema_path = self.root / SCHEMA_PATH
        if not schema_path.is_file():
            _fail(f"missing {schema_path}")
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            _fail(f"invalid {schema_path}: {error}")
        if schema.get("$id") != "https://quantum-l9.dev/schemas/repo-workflow/v1":
            _fail("unexpected repo-workflow schema identity")
        try:
            import jsonschema

            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.Draft202012Validator(schema).validate(config)
        except ModuleNotFoundError:
            _fail("jsonschema is required for structural validation; run make setup")
        except Exception as error:
            _fail(f"repo-workflow schema validation failed: {error}")
        verify_checksum_manifest(self.root)
        template = self.root / TEMPLATE_PATH
        makefile = self.root / "Makefile"
        if not template.is_file():
            _fail(f"missing {template}")
        if not makefile.is_file() or makefile.read_bytes() != template.read_bytes():
            _fail("Makefile drift: run make reconcile")
        try:
            validate_contract_wiring(self.root, config["agent_contracts"])
            validate_authority(self.root, config)
        except (ContractWiringError, AuthorityError) as error:
            _fail(str(error))

    def clean(self) -> None:
        self._ensure_repository_root()
        root = self.root.resolve()
        for relative in self.config()["clean_paths"]:
            path = (root / relative).resolve()
            if path == root or root not in path.parents:
                _fail(f"unsafe clean path: {relative}")
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()

    def _assert_push_state(self, protected: set[str]) -> str:
        branch = self.branch()
        if not branch:
            _fail("detached HEAD: push refused")
        if branch in protected:
            _fail(f"protected branch {branch}: push refused")
        for marker in (
            "MERGE_HEAD",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "BISECT_LOG",
            "sequencer",
            "rebase-merge",
            "rebase-apply",
        ):
            if self.git_path(marker).exists():
                _fail("merge/rebase in progress: push refused")
        if self.status_porcelain():
            _fail("dirty worktree: push refused")
        return branch

    def _run_push_gates(self, config: dict[str, Any]) -> None:
        self.agent_check()
        verify_push_preflight(self.root, config["push"]["lockfile_command"])

    def _push_unlocked(self) -> dict[str, str]:
        self._ensure_repository_root()
        config = self.config()
        protected = set(config["repository"]["protected_branches"])
        branch = self._assert_push_state(protected)
        self.git("fetch", "--prune", "origin")
        remote = self.git(
            "rev-parse",
            "--verify",
            f"origin/{branch}",
            capture=True,
            check=False,
        )
        if remote.returncode == 0:
            counts = self.git(
                "rev-list",
                "--left-right",
                "--count",
                f"origin/{branch}...HEAD",
                capture=True,
            ).stdout.split()
            behind = int(counts[0]) if counts else 0
            if behind:
                if not config["push"]["rebase_before_push"]:
                    _fail("remote branch has commits not in local HEAD: push refused")
                self.git("rebase", f"origin/{branch}")
                self._assert_push_state(protected)

        self._run_push_gates(config)
        if self.status_porcelain():
            _fail("validation changed the worktree: push refused")
        upstream = self.git(
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
            capture=True,
            check=False,
        )
        if upstream.returncode == 0:
            self.git("push")
        elif config["push"]["set_upstream"]:
            self.git("push", "--set-upstream", "origin", branch)
        else:
            self.git("push", "origin", branch)
        sha = self.git("rev-parse", "HEAD", capture=True).stdout.strip()
        payload = {"branch": branch, "sha": sha, "remote": f"origin/{branch}"}
        print(json.dumps(payload, sort_keys=True))
        return payload

    def push(self) -> None:
        path, stale_after = self._lock_settings()
        try:
            with single_flight(path, stale_after=stale_after):
                self._push_unlocked()
        except (LockBusy, PreflightError) as error:
            _fail(str(error))

    def pr(self) -> None:
        path, stale_after = self._lock_settings()
        try:
            with single_flight(path, stale_after=stale_after):
                self._push_unlocked()
                config = self.config()["pull_request"]
                existing = self.run(
                    ["gh", "pr", "view", "--json", "url"],
                    capture=True,
                    check=False,
                )
                if existing.returncode == 0:
                    print(existing.stdout.strip())
                    return
                command = ["gh", "pr", "create", "--fill", "--base", config["base"]]
                if config["draft_by_default"]:
                    command.append("--draft")
                self.run(command)
        except (LockBusy, PreflightError) as error:
            _fail(str(error))

    def _ref_exists(self, ref: str) -> bool:
        return (
            self.git("rev-parse", "--verify", ref, capture=True, check=False).returncode
            == 0
        )

    def status(self) -> None:
        self._ensure_repository_root()
        config = self.config()
        branch = self.branch()
        sha = self.git("rev-parse", "HEAD", capture=True).stdout.strip()
        fetch_result: subprocess.CompletedProcess[str] | None = None
        if config["status"]["fetch_remote"]:
            try:
                fetch_result = self.git(
                    "fetch", "--prune", "origin", capture=True, check=False
                )
            except OSError as error:
                fetch_result = subprocess.CompletedProcess(
                    ["git", "fetch"], 127, "", str(error)
                )
        freshness = (
            "fresh"
            if fetch_result is not None and fetch_result.returncode == 0
            else "unknown_offline"
        )
        candidate_refs = []
        if branch:
            candidate_refs.append(f"origin/{branch}")
        candidate_refs.append(f"origin/{config['pull_request']['base']}")
        comparison_ref = next(
            (ref for ref in candidate_refs if self._ref_exists(ref)), None
        )
        ahead: int | None = None
        behind: int | None = None
        if comparison_ref:
            counts = self.git(
                "rev-list",
                "--left-right",
                "--count",
                f"{comparison_ref}...HEAD",
                capture=True,
                check=False,
            )
            if counts.returncode == 0:
                values = counts.stdout.split()
                if len(values) == 2:
                    behind = int(values[0])
                    ahead = int(values[1])

        try:
            pull_request = self.run(
                ["gh", "pr", "view", "--json", "url,state,statusCheckRollup"],
                capture=True,
                check=False,
            )
            pr_payload = (
                json.loads(pull_request.stdout)
                if pull_request.returncode == 0
                else None
            )
        except (OSError, json.JSONDecodeError):
            pr_payload = None

        payload: dict[str, object] = {
            "branch": branch,
            "sha": sha,
            "dirty": bool(self.status_porcelain()),
            "remote_freshness": freshness,
            "comparison_ref": comparison_ref,
            "comparison_source": (
                "unavailable"
                if comparison_ref is None
                else ("live" if freshness == "fresh" else "cached")
            ),
            "ahead": ahead,
            "behind": behind,
            "fetch_error": (
                None
                if fetch_result is None or fetch_result.returncode == 0
                else (fetch_result.stderr.strip() or "fetch failed")
            ),
            "pr": pr_payload,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))

    def reconcile(self) -> None:
        self._ensure_repository_root()
        path, stale_after = self._lock_settings()
        try:
            with single_flight(path, stale_after=stale_after):
                source = self.root / TEMPLATE_PATH
                if not source.is_file():
                    _fail(f"missing {source}")
                (self.root / "Makefile").write_bytes(source.read_bytes())
                print("Makefile reconciled")
        except LockBusy as error:
            _fail(str(error))

    def help(self) -> None:
        print("Common targets: " + " ".join(COMMANDS))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="l9-repo")
    parser.add_argument("--workspace", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("command", choices=COMMANDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    workflow = RepositoryWorkflow(arguments.workspace)
    try:
        if arguments.command == "agent-check":
            workflow.agent_check(
                explicit=arguments.changed_file,
                base_ref=arguments.base_ref,
                head_ref=arguments.head_ref,
            )
        elif arguments.command == "change-policy":
            workflow.change_policy(
                explicit=arguments.changed_file,
                base_ref=arguments.base_ref,
                head_ref=arguments.head_ref,
            )
        else:
            method_name = arguments.command.replace("-", "_")
            getattr(workflow, method_name)()
    except AgentCheckFailure as error:
        print(str(error), file=sys.stderr)
        return 1
    except (WorkflowError, ChangePolicyError, ContractWiringError) as error:
        print(str(error), file=sys.stderr)
        return _INFRASTRUCTURE_EXIT_CODE
    except subprocess.CalledProcessError as error:
        return error.returncode or 1
    except OSError as error:
        print(str(error), file=sys.stderr)
        return _INFRASTRUCTURE_EXIT_CODE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
