#!/usr/bin/env python3
"""Reconcile plugin-config.yaml with the repository it actually describes.

`plugin-config.yaml` is chassis: every repository born from this template keeps
it, and every generated Cursor rule is rendered from it. That combination makes
it the one file where a stale template value becomes an *active instruction* in
an unrelated repository — internally consistent, and semantically false.

Package-name substitution is not enough. Renaming `l9_example_pkg.app:app` to
`<product>.app:app` produces a claim about a module the product does not have,
because an authoritative payload owns `src/` and never shipped one. The identity
of the born repository is likewise not a token: `repo_name` and `domain` are
literal template values that no rename ever touched.

So this reconciles rather than substitutes. Every active claim in the config is
either derived from an authority inside this repository, or it is removed:

    repo_name          .l9/architecture.yaml -> metadata.repository
    domain             .l9/architecture.yaml -> identity.role / metadata.role
    app_entrypoint     kept only if the module it names exists in this tree
    capabilities       kept only if the evidence path declared for them exists

Absence of evidence removes the claim. It never invents one, and it never names
a product: `capability_evidence` is declared in the config beside the
capabilities it gates, so a repository with a different optional stack states
its own condition without this script learning anything about it.

Two modes, the same computation:

    --check   exit 1 if the config is not already reconciled (the semantic gate)
    (apply)   rewrite it in place, surgically, preserving comments and layout
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit("PyYAML is required. Install with: uv add --dev pyyaml") from exc

DEFAULT_CONFIG = Path("plugin-config.yaml")
ARCHITECTURE = Path(".l9/architecture.yaml")

# `<module.path>:<attr>` — the attribute is a runtime symbol this script cannot
# see, so only the module half is proved. A claim about a module that does not
# exist is the defect; a claim about an attribute inside a module that does is
# a different, product-owned problem.
ENTRYPOINT_RE = re.compile(r"^(?P<module>[A-Za-z_][A-Za-z0-9_.]*)\s*:\s*[A-Za-z_][A-Za-z0-9_]*$")


class ReconcileError(RuntimeError):
    """The config cannot be reconciled, and guessing would be worse."""


# ─────────────────────────────────────────────────────────────────────────────
# Pure computation — no I/O, unit-tested against text and a fixture tree.
# ─────────────────────────────────────────────────────────────────────────────


def repository_identity(architecture: dict[str, Any]) -> str | None:
    """The repository's own name, from the authoritative identity file."""
    metadata = architecture.get("metadata")
    if not isinstance(metadata, dict):
        return None
    slug = metadata.get("repository")
    if not isinstance(slug, str) or not slug.strip():
        return None
    return slug.strip().rsplit("/", 1)[-1] or None


def repository_domain(architecture: dict[str, Any], *, repo_name: str | None) -> str | None:
    """The repository's declared role, or its own name — never the template's.

    `identity.role` is what a repository says it is. `metadata.role` is the
    fallback for a payload that declares only the outer block. Falling back to
    the repository name is honest where neither exists: a name is a true
    statement about the repository, and the template's example domain is not.
    """
    for block in ("identity", "metadata"):
        section = architecture.get(block)
        if isinstance(section, dict):
            role = section.get("role")
            if isinstance(role, str) and role.strip():
                return role.strip()
    return repo_name


def module_relpaths(module: str, *, src_layout: bool) -> tuple[str, str]:
    """Where `a.b.c` would live, as a module and as a package."""
    parts = module.split(".")
    prefix = "src/" if src_layout else ""
    stem = "/".join(parts)
    return f"{prefix}{stem}.py", f"{prefix}{stem}/__init__.py"


def entrypoint_is_materialized(root: Path, entrypoint: str, *, src_layout: bool) -> bool:
    match = ENTRYPOINT_RE.match(entrypoint.strip())
    if match is None:
        return False
    return any(
        (root / rel).is_file()
        for rel in module_relpaths(match.group("module"), src_layout=src_layout)
    )


def package_is_materialized(root: Path, package: str, *, src_layout: bool) -> bool:
    base = root / "src" if src_layout else root
    return (base / package).is_dir()


def unsupported_capabilities(
    root: Path, capabilities: list[str], evidence: dict[str, str]
) -> list[str]:
    """Capabilities whose declared evidence path is absent from this tree.

    A capability with no declared evidence is unconditional: it is a chassis
    verb that is true wherever the chassis is. Only a capability that names its
    own condition can fail to meet it.
    """
    return [
        name
        for name in capabilities
        if isinstance(evidence.get(name), str) and not (root / evidence[name]).exists()
    ]


def _scalar_line(key: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(key)}:[ \t]*\S.*$")


def set_scalar(lines: list[str], key: str, value: str) -> list[str]:
    return [f'{key}: "{value}"' if _scalar_line(key).match(line) else line for line in lines]


def drop_scalar(lines: list[str], key: str) -> list[str]:
    return [line for line in lines if not _scalar_line(key).match(line)]


def _block_span(lines: list[str], parent: str, child: str) -> tuple[int, int] | None:
    """The `[start, end)` line span of `parent:` -> `child:`'s own entries."""
    in_parent = False
    for index, line in enumerate(lines):
        if re.match(rf"^{re.escape(parent)}:[ \t]*$", line):
            in_parent = True
            continue
        if in_parent and line.strip() and not line.startswith((" ", "\t")):
            return None
        if not in_parent:
            continue
        if re.match(rf"^[ \t]+{re.escape(child)}:[ \t]*$", line):
            indent = len(line) - len(line.lstrip())
            end = index + 1
            while end < len(lines):
                nxt = lines[end]
                if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= indent:
                    break
                end += 1
            return index + 1, end
    return None


def drop_list_items(lines: list[str], parent: str, child: str, values: list[str]) -> list[str]:
    """Remove `- value` entries from a nested list, leaving the rest untouched."""
    span = _block_span(lines, parent, child)
    if span is None or not values:
        return lines
    start, end = span
    wanted = {re.sub(r"^-[ \t]*", "", value.strip()).strip("\"'") for value in values}
    kept = [
        line
        for line in lines[start:end]
        if not (
            line.strip().startswith("- ")
            and line.strip().removeprefix("- ").strip().strip("\"'") in wanted
        )
    ]
    return lines[:start] + kept + lines[end:]


def drop_mapping_keys(lines: list[str], parent: str, child: str, keys: list[str]) -> list[str]:
    """Remove `key: value` entries from a nested mapping, and the mapping if emptied."""
    span = _block_span(lines, parent, child)
    if span is None or not keys:
        return lines
    start, end = span
    wanted = set(keys)
    kept = [
        line
        for line in lines[start:end]
        if line.split(":", 1)[0].strip().strip("\"'") not in wanted
    ]
    if not any(line.strip() for line in kept):
        # An emptied mapping key would be `null`, which is a different claim.
        return lines[: start - 1] + lines[end:]
    return lines[:start] + kept + lines[end:]


# ─────────────────────────────────────────────────────────────────────────────
# Reconciliation
# ─────────────────────────────────────────────────────────────────────────────


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReconcileError(f"missing {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ReconcileError(f"{path} is not a YAML mapping")
    return data


def reconcile_text(
    text: str, config: dict[str, Any], architecture: dict[str, Any], root: Path
) -> tuple[str, list[str]]:
    """Return `(reconciled text, sorted list of changes)`.

    The text is edited line by line rather than re-serialized: a YAML round-trip
    would drop every comment in the file and reformat lines nothing asked to
    change.
    """
    changes: list[str] = []
    lines = text.splitlines()
    src_layout = bool(config.get("src_layout", True))

    repo_name = repository_identity(architecture)
    if repo_name and config.get("repo_name") != repo_name:
        lines = set_scalar(lines, "repo_name", repo_name)
        changes.append(f"repo_name -> {repo_name}")

    domain = repository_domain(architecture, repo_name=repo_name)
    if domain and config.get("domain") != domain:
        lines = set_scalar(lines, "domain", domain)
        changes.append(f"domain -> {domain}")

    package = config.get("package_name")
    if isinstance(package, str) and package:
        if not package_is_materialized(root, package, src_layout=src_layout):
            raise ReconcileError(
                f"package_name {package!r} names no package in this repository — "
                "a config cannot be reconciled against a package that does not exist"
            )

    entrypoint = config.get("app_entrypoint")
    if isinstance(entrypoint, str) and entrypoint.strip():
        if not entrypoint_is_materialized(root, entrypoint, src_layout=src_layout):
            lines = drop_scalar(lines, "app_entrypoint")
            changes.append(f"app_entrypoint dropped ({entrypoint} is not in this repository)")

    graph = config.get("graph_record")
    if isinstance(graph, dict):
        capabilities = [c for c in graph.get("capabilities") or [] if isinstance(c, str)]
        evidence = graph.get("capability_evidence")
        evidence = evidence if isinstance(evidence, dict) else {}
        unsupported = unsupported_capabilities(root, capabilities, evidence)
        if unsupported:
            lines = drop_list_items(lines, "graph_record", "capabilities", unsupported)
            lines = drop_mapping_keys(lines, "graph_record", "capability_evidence", unsupported)
            for name in unsupported:
                changes.append(f"capability dropped: {name} (no {evidence[name]})")

    return "\n".join(lines) + "\n", changes


def run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    config_path = root / args.config
    architecture_path = root / args.architecture

    config = load_yaml(config_path)
    architecture = load_yaml(architecture_path)
    current = config_path.read_text(encoding="utf-8")
    reconciled, changes = reconcile_text(current, config, architecture, root)

    if reconciled == current:
        print(f"OK: {config_path.name} describes this repository")
        return 0

    if args.check:
        print(f"DRIFT: {config_path.name} claims what this repository is not", file=sys.stderr)
        for change in changes:
            print(f"  {change}", file=sys.stderr)
        print("  fix: make reconcile-config", file=sys.stderr)
        return 1

    config_path.write_text(reconciled, encoding="utf-8")
    print(f"reconciled {config_path.name}")
    for change in changes:
        print(f"  {change}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--architecture", default=str(ARCHITECTURE))
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true", help="Fail if the config is stale")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(sys.argv[1:] if argv is None else argv))
    except ReconcileError as exc:
        print(f"reconcile-config FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
