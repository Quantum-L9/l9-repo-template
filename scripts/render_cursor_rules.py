#!/usr/bin/env python3
"""Render Cursor .mdc rules from parametric templates + plugin-config.yaml.

Design goals:
- Reusable across L9 repos: repo-specific values live in plugin-config.yaml.
- Safe by default: refuse to overwrite unmanaged .mdc files unless --force is used.
- Drift-detectable: --check exits non-zero if rendered files are stale.
- Graphable: writes .cursor/rules/.render-manifest.json with template/config hashes.

Template syntax uses Python string.Template placeholders:
    ${repo_name}
    ${protected_paths_bullets}
    ${ci_gates_bullets}

A template may also declare its own precondition on the first line:

    <!-- L9_RENDER_REQUIRES: app_entrypoint -->

The named config keys must be present and non-empty or the rule is NOT
rendered, and any previously rendered copy of it is removed. A generated rule
is an instruction to an agent; a rule about a surface this repository does not
have is a false instruction, and the template is the only place that knows what
its own subject is. `plugin-config.yaml` is reconciled against the repository by
`scripts/reconcile_plugin_config.py`, so an unmet requirement means the surface
is genuinely absent rather than merely unmentioned.

This script depends on PyYAML. Add to dev dependencies if missing:
    uv add --dev pyyaml
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
import textwrap
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from string import Template
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit("PyYAML is required. Install with: uv add --dev pyyaml") from exc

RENDER_MARKER = "L9_RENDERED"
REQUIRES_RE = re.compile(r"^[ \t]*<!--[ \t]*L9_RENDER_REQUIRES:(?P<keys>[^>]*?)-->[ \t]*$", re.M)
DEFAULT_CONFIG = Path("plugin-config.yaml")
DEFAULT_TEMPLATE_DIR = Path(".cursor/rules/templates")
DEFAULT_OUTPUT_DIR = Path(".cursor/rules")
DEFAULT_MANIFEST = Path(".cursor/rules/.render-manifest.json")


@dataclass(frozen=True)
class SkippedRule:
    template_path: Path
    output_path: Path
    unmet: tuple[str, ...]

    @property
    def reason(self) -> str:
        return f"requires {', '.join(self.unmet)}"


@dataclass(frozen=True)
class RenderedRule:
    template_path: Path
    output_path: Path
    template_sha256: str
    output_sha256: str
    render_id: str
    content: str


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing config: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Config must be a YAML mapping: {path}")
    required = [
        "plugin_version",
        "repo_name",
        "domain",
        "package_name",
        "python_version",
        "protected_paths",
        "high_risk_commands",
        "ci_gates",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        raise SystemExit(f"Missing required plugin-config keys: {', '.join(missing)}")
    return data


def bullet_list(values: Any) -> str:
    if not values:
        return "- None declared"
    if not isinstance(values, list):
        values = [values]
    return "\n".join(f"- `{value}`" for value in values)


def csv_code(values: Any) -> str:
    if not values:
        return "None declared"
    if not isinstance(values, list):
        values = [values]
    return ", ".join(f"`{value}`" for value in values)


def as_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def flatten(prefix: str, value: Any, out: dict[str, str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            flatten(f"{prefix}_{key}" if prefix else str(key), child, out)
    elif isinstance(value, list):
        out[prefix] = bullet_list(value)
        out[f"{prefix}_bullets"] = bullet_list(value)
        out[f"{prefix}_csv"] = csv_code(value)
        out[f"{prefix}_json"] = as_json(value)
    else:
        out[prefix] = "" if value is None else str(value)


def build_context(config: dict[str, Any], *, config_path: Path, config_sha: str) -> dict[str, str]:
    ctx: dict[str, str] = {}
    flatten("", config, ctx)
    ctx.setdefault("app_entrypoint", "n/a")
    ctx.setdefault("venv_path", ".venv/bin/python")
    ctx.setdefault("test_isolation_pattern", "none")
    ctx["config_path"] = str(config_path)
    ctx["config_sha256"] = config_sha
    ctx["config_sha256_short"] = config_sha[:12]
    ctx["rendered_notice"] = (
        "This file is generated from .cursor/rules/templates/*.mdc.template. "
        "Do not edit directly; edit the template or plugin-config.yaml."
    )
    ctx["graph_record_json"] = as_json(config.get("graph_record", {}))
    return ctx


def managed_header(
    *, template_path: Path, template_sha: str, config_path: Path, config_sha: str
) -> str:
    render_id = sha256_text(f"{template_sha}:{config_sha}")
    return textwrap_dedent(
        f"""
        <!-- {RENDER_MARKER}
        template: {template_path.as_posix()}
        template_sha256: {template_sha}
        config: {config_path.as_posix()}
        config_sha256: {config_sha}
        render_id: {render_id}
        /{RENDER_MARKER} -->
        """
    ).lstrip()


def textwrap_dedent(value: str) -> str:
    return textwrap.dedent(value)


def output_name_for_template(template_path: Path) -> str:
    name = template_path.name
    if not name.endswith(".mdc.template"):
        raise SystemExit(f"Invalid template suffix: {template_path}")
    return name.removesuffix(".template")


def render_one(
    template_path: Path,
    output_dir: Path,
    context: dict[str, str],
    *,
    config_path: Path,
    config_sha: str,
) -> RenderedRule:
    raw = template_path.read_text(encoding="utf-8")
    template_sha = sha256_text(raw)
    body, _ = template_requirements(raw)
    rendered_body = Template(body).safe_substitute(context)
    header = managed_header(
        template_path=template_path,
        template_sha=template_sha,
        config_path=config_path,
        config_sha=config_sha,
    )
    content = f"{header}{rendered_body.rstrip()}\n"
    output_path = output_dir / output_name_for_template(template_path)
    render_id = sha256_text(f"{template_sha}:{config_sha}")
    return RenderedRule(
        template_path=template_path,
        output_path=output_path,
        template_sha256=template_sha,
        output_sha256=sha256_text(content),
        render_id=render_id,
        content=content,
    )


def template_requirements(raw: str) -> tuple[str, tuple[str, ...]]:
    """Split a template into its body and the config keys it requires."""
    keys: list[str] = []
    for match in REQUIRES_RE.finditer(raw):
        keys.extend(part for part in re.split(r"[\s,]+", match.group("keys")) if part)
    return REQUIRES_RE.sub("", raw).lstrip("\n"), tuple(dict.fromkeys(keys))


def unmet_requirements(config: dict[str, Any], keys: tuple[str, ...]) -> tuple[str, ...]:
    """The required keys this config does not actually supply."""
    return tuple(key for key in keys if not str(config.get(key, "") or "").strip())


def discover_templates(template_dir: Path) -> list[Path]:
    if not template_dir.exists():
        raise SystemExit(f"Missing template dir: {template_dir}")
    templates = sorted(template_dir.glob("*.mdc.template"))
    if not templates:
        raise SystemExit(f"No .mdc.template files found in: {template_dir}")
    return templates


def is_managed(path: Path) -> bool:
    return path.exists() and RENDER_MARKER in path.read_text(encoding="utf-8", errors="ignore")


def unified_diff(path: Path, expected: str) -> str:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    return "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=f"current/{path}",
            tofile=f"expected/{path}",
        )
    )


def write_manifest(
    path: Path,
    *,
    config_path: Path,
    config_sha: str,
    rendered: list[RenderedRule],
    skipped: list[SkippedRule],
) -> None:
    manifest = {
        "schema": "l9.cursor_rules.render_manifest.v1",
        "rendered_at": datetime.now(UTC).isoformat(),
        "renderer": "scripts/render_cursor_rules.py",
        "config": str(config_path),
        "config_sha256": config_sha,
        "rules": [
            {
                "template": str(rule.template_path),
                "output": str(rule.output_path),
                "template_sha256": rule.template_sha256,
                "output_sha256": rule.output_sha256,
                "render_id": rule.render_id,
            }
            for rule in rendered
        ],
        # A rule this repository does not qualify for is recorded, not silently
        # missing: "absent" and "never applied" are different facts.
        "skipped": [
            {
                "template": str(rule.template_path),
                "output": str(rule.output_path),
                "unmet_requirements": list(rule.unmet),
            }
            for rule in skipped
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    template_dir = Path(args.template_dir)
    output_dir = Path(args.output_dir)
    manifest_path = Path(args.manifest)

    config = load_config(config_path)
    config_sha = sha256_file(config_path)
    context = build_context(config, config_path=config_path, config_sha=config_sha)

    rendered: list[RenderedRule] = []
    skipped: list[SkippedRule] = []
    for path in discover_templates(template_dir):
        _, requires = template_requirements(path.read_text(encoding="utf-8"))
        unmet = unmet_requirements(config, requires)
        if unmet:
            skipped.append(
                SkippedRule(
                    template_path=path,
                    output_path=output_dir / output_name_for_template(path),
                    unmet=unmet,
                )
            )
            continue
        rendered.append(
            render_one(path, output_dir, context, config_path=config_path, config_sha=config_sha)
        )

    stale: list[RenderedRule] = []
    for rule in rendered:
        if (
            not rule.output_path.exists()
            or rule.output_path.read_text(encoding="utf-8") != rule.content
        ):
            stale.append(rule)

    # A skipped rule whose output is still on disk is stale in the other
    # direction: the file states a rule this repository no longer qualifies for.
    orphaned = [rule for rule in skipped if rule.output_path.exists()]

    if args.check:
        if not stale and not orphaned:
            print(f"OK: {len(rendered)} rendered Cursor rules are current", end="")
            print(f" ({len(skipped)} skipped)" if skipped else "")
            return 0
        print(
            f"DRIFT: {len(stale)} stale, {len(orphaned)} unqualified Cursor rule(s)",
            file=sys.stderr,
        )
        for rule in orphaned:
            print(f"  {rule.output_path}: {rule.reason} — remove it", file=sys.stderr)
        if args.diff:
            for rule in stale:
                print(unified_diff(rule.output_path, rule.content), file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    for rule in orphaned:
        if not is_managed(rule.output_path) and not args.force:
            raise SystemExit(
                f"Refusing to remove unmanaged file: {rule.output_path}\n"
                f"This repository does not qualify for it ({rule.reason}); "
                "run once with --force to migrate."
            )
        rule.output_path.unlink()
        print(f"removed {rule.output_path} ({rule.reason})")
    for rule in skipped:
        print(f"skipped {rule.template_path} ({rule.reason})")
    for rule in rendered:
        if rule.output_path.exists() and not is_managed(rule.output_path) and not args.force:
            raise SystemExit(
                f"Refusing to overwrite unmanaged file: {rule.output_path}\n"
                "Run once with --force to migrate existing hand-authored rules."
            )
        rule.output_path.write_text(rule.content, encoding="utf-8")
        print(f"rendered {rule.template_path} -> {rule.output_path}")

    write_manifest(
        manifest_path,
        config_path=config_path,
        config_sha=config_sha,
        rendered=rendered,
        skipped=skipped,
    )
    print(f"manifest {manifest_path}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--template-dir", default=str(DEFAULT_TEMPLATE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--check", action="store_true", help="Fail if rendered files are stale")
    parser.add_argument("--diff", action="store_true", help="Print unified diffs with --check")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing unmanaged .mdc files once during migration",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
