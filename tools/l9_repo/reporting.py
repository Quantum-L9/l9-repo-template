from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(
        r"(?i)\b((?:github_)?token|password|passwd|secret|api[_-]?key)\s*([=:])\s*([^\s]+)"
    ),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)(https?://[^:/\s]+:)[^@/\s]+(@)"),
)


def redact_text(text: str) -> str:
    redacted = text
    redacted = _SECRET_PATTERNS[0].sub(r"\1[REDACTED]", redacted)
    redacted = _SECRET_PATTERNS[1].sub(r"\1\2[REDACTED]", redacted)
    for pattern in _SECRET_PATTERNS[2:5]:
        redacted = pattern.sub("[REDACTED]", redacted)
    redacted = _SECRET_PATTERNS[5].sub(r"\1[REDACTED]\2", redacted)
    return redacted


@dataclass(frozen=True)
class StepEvidence:
    name: str
    command: tuple[str, ...]
    exit_code: int
    classification: str
    blocking: bool
    stdout: str = ""
    stderr: str = ""


def _payload(
    *,
    files: Sequence[str],
    change_source: str,
    base_ref: str | None,
    head_ref: str | None,
    findings: Sequence[dict[str, object]],
    steps: Sequence[StepEvidence],
    overall_exit_code: int,
    subject_sha: str,
    policy_sha256: str,
) -> dict[str, object]:
    return {
        "schema": "l9.repo-agent-check-evidence/v2",
        "subject": {
            "git_revision": subject_sha,
            "policy_sha256": policy_sha256,
        },
        "change_context": {
            "source": change_source,
            "base_ref": base_ref,
            "head_ref": head_ref,
        },
        "changed_files": list(files),
        "companion_findings": list(findings),
        "steps": [
            {
                **asdict(step),
                "command": [redact_text(token) for token in step.command],
                "stdout": redact_text(step.stdout),
                "stderr": redact_text(step.stderr),
            }
            for step in steps
        ],
        "overall_exit_code": overall_exit_code,
        "passed": overall_exit_code == 0,
    }


def _render_markdown(payload: dict[str, object]) -> str:
    context = payload["change_context"]
    assert isinstance(context, dict)
    subject = payload["subject"]
    assert isinstance(subject, dict)
    lines = [
        "# Repository Agent Check Evidence",
        "",
        f"- **Result:** {'PASS' if payload['passed'] else 'FAIL'}",
        f"- **Exit code:** `{payload['overall_exit_code']}`",
        f"- **Git revision:** `{subject['git_revision']}`",
        f"- **Policy SHA-256:** `{subject['policy_sha256']}`",
        f"- **Change source:** `{context.get('source')}`",
        f"- **Base ref:** `{context.get('base_ref')}`",
        f"- **Head ref:** `{context.get('head_ref')}`",
        "",
        "## Changed Files",
        "",
    ]
    changed = payload["changed_files"]
    assert isinstance(changed, list)
    lines.extend([f"- `{path}`" for path in changed] or ["- none"])
    lines.extend(
        [
            "",
            "## Companion Findings",
            "",
        ]
    )
    findings = payload["companion_findings"]
    assert isinstance(findings, list)
    if findings:
        for finding in findings:
            assert isinstance(finding, dict)
            lines.append(f"### {finding.get('rule_id')}")
            lines.append("")
            lines.append(str(finding.get("message", "")))
            required_any = finding.get("required_any", [])
            missing_all = finding.get("missing_all", [])
            if required_any:
                lines.append(f"- Required any prefix: `{required_any}`")
            if missing_all:
                lines.append(f"- Missing exact paths: `{missing_all}`")
            lines.append("")
    else:
        lines.append("- none")
        lines.append("")

    lines.extend(
        [
            "## Step Results",
            "",
            "| Step | Class | Exit | Blocking | Command |",
            "|---|---|---:|---|---|",
        ]
    )
    steps = payload["steps"]
    assert isinstance(steps, list)
    for step in steps:
        assert isinstance(step, dict)
        command = (
            " ".join(str(token) for token in step.get("command", [])) or "(internal)"
        )
        command = command.replace("|", "\\|")
        lines.append(
            f"| {step.get('name')} | {step.get('classification')} | "
            f"{step.get('exit_code')} | {step.get('blocking')} | `{command}` |"
        )
    lines.append("")

    for step in steps:
        assert isinstance(step, dict)
        stdout = str(step.get("stdout", ""))
        stderr = str(step.get("stderr", ""))
        if not stdout and not stderr:
            continue
        lines.append(f"### Evidence: {step.get('name')}")
        lines.append("")
        if stdout:
            lines.extend(
                ["**stdout**", "", "<pre>", html.escape(stdout.rstrip()), "</pre>", ""]
            )
        if stderr:
            lines.extend(
                ["**stderr**", "", "<pre>", html.escape(stderr.rstrip()), "</pre>", ""]
            )
    return "\n".join(lines).rstrip() + "\n"


def write_reports(
    json_path: Path,
    markdown_path: Path,
    *,
    files: Sequence[str],
    change_source: str,
    base_ref: str | None,
    head_ref: str | None,
    findings: Sequence[dict[str, object]],
    steps: Sequence[StepEvidence],
    overall_exit_code: int,
    subject_sha: str = "unknown",
    policy_sha256: str = "unknown",
) -> None:
    payload = _payload(
        files=files,
        change_source=change_source,
        base_ref=base_ref,
        head_ref=head_ref,
        findings=findings,
        steps=steps,
        overall_exit_code=overall_exit_code,
        subject_sha=subject_sha,
        policy_sha256=policy_sha256,
    )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")


def write_report(
    path: Path,
    *,
    files: Sequence[str],
    findings: Sequence[dict[str, object]],
    steps: Sequence[StepEvidence],
    overall_exit_code: int,
) -> None:
    """Backward-compatible JSON-only wrapper used by older callers/tests."""

    write_reports(
        path,
        path.with_suffix(".md"),
        files=files,
        change_source="unknown",
        base_ref=None,
        head_ref=None,
        findings=findings,
        steps=steps,
        overall_exit_code=overall_exit_code,
        subject_sha="unknown",
        policy_sha256=hashlib.sha256(b"unknown").hexdigest(),
    )
