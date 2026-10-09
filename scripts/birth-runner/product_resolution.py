#!/usr/bin/env python3
"""Compiler-backed product resolution: the factory re-runs the pinned semantic compiler.

A compiler-backed birth (`l9.product-birth-binding/v2`) carries a ProductManifest
that an upstream semantic compiler resolved from the product's own
ProductTopology, RepositorySpec, WorkflowSpec and authority lock. The factory
does not interpret any of those: it does not know what a ProductKind is, what an
archetype requires, or when a manifest is resolved. What it CAN do is run the
same deterministic compiler, at the same exact revision, against the same exact
inputs, and refuse birth unless the result is the manifest it was handed.

    binding.compiler    which engine (repository, revision, version) and which
                        input files inside the source snapshot
    semantic-compiler.pin.json
                        which engine THIS factory admits — the only one
    verified payload    the source tree `_preflight_payload_contract` just
                        reproduced byte-for-byte against the compiled payload
                               |
                               v
    python -I -m l9_semantic_compiler product-build ...   (the engine's own CLI)
                               |
                               v
    reproduced manifest  ==  supplied manifest   (digest AND document)
    reproduced manifest carries no unresolved entry

Every disagreement refuses: a compiler that fails or cannot be proven to be the
pinned one, a manifest whose digest or body differs, an unresolved entry, an
input the payload does not name, a source tree the compiler left dirty. There
is no partial credit and no fallback to "trust the supplied manifest".

The engine is pinned, not vendored and not inferred. `semantic-compiler.pin.json`
names the repository, the exact 40-hex revision and the package version; a
checkout is admitted only when it is clean, at that HEAD, with that `origin`
and that `pyproject.toml` version, so the revision the receipt records is the
revision whose code ran. The engine runs in a child interpreter started with
`-I` (no inherited `PYTHON*` environment, no user site, no cwd on `sys.path`),
a scratch working directory and a scratch `HOME`, reading the source snapshot
and writing only into a scratch output directory.

Dependency-free at runtime, like the rest of the birth engine. The engine's own
YAML output is translated to JSON inside the child interpreter, where the
engine's dependencies are already present; this module reads JSON only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def _load_sibling(name: str):
    """Load a module that lives next to this file, wherever this file lives."""
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the birth module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# git as the provenance substrate, and the one slug/oid grammar the factory has.
prov = _load_sibling("birth_provenance")
compiler = _load_sibling("compile_birth_payload")

TEMPLATE_ROOT = Path(__file__).resolve().parents[2]
PIN_PATH = "scripts/birth-runner/semantic-compiler.pin.json"
PIN_SCHEMA = "l9.semantic-compiler-pin/v1"
MANIFEST_SCHEMA = "l9.product-manifest/v1"

# The engine inputs a binding names, in the order the engine's CLI takes them.
REQUIRED_INPUTS = ("topology", "repository_spec", "workflow_spec", "authority_lock")
OPTIONAL_INPUTS = ("contract_catalog",)
INPUT_KEYS = (*REQUIRED_INPUTS, *OPTIONAL_INPUTS)
# The engine CLI's own default, resolved against the source root when a product
# declares no local contract catalog (the engine then reads nothing from it).
DEFAULT_CONTRACT_CATALOG = "contracts/compiler-core.yaml"

ENGINE_TIMEOUT_SECONDS = 600
_VERSION_RE = re.compile(r'^\s*version\s*=\s*"([^"]+)"\s*$', re.M)
_NAME_RE = re.compile(r'^\s*name\s*=\s*"([^"]+)"\s*$', re.M)

# Runs inside the child interpreter. argv: engine_src, result_path, then the
# engine CLI's own product-build arguments. The engine writes its artifacts the
# way it always does; the manifest is then read back with the engine's own YAML
# dependency and handed to the factory as JSON, together with the exit code the
# engine's CLI returned (0 resolved, 2 unresolved).
_BOOTSTRAP = r"""
import json, sys
engine_src, result_path, output_dir = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, engine_src)
import yaml
from l9_semantic_compiler.cli import main
code = main(["product-build", "--output-dir", output_dir, *sys.argv[4:]])
with open(output_dir + "/product-manifest.yaml", "rb") as fh:
    manifest = yaml.safe_load(fh.read().decode("utf-8"))
with open(result_path, "w", encoding="utf-8") as fh:
    json.dump({"exit_code": code, "manifest": manifest}, fh, sort_keys=True)
"""


class ProductResolutionError(RuntimeError):
    """The pinned engine could not be proven, could not run, or did not reproduce the manifest."""


# ─────────────────────────────────────────────────────────────────────────────
# The pin
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EnginePin:
    repository: str
    revision: str
    package: str
    version: str
    module: str
    source_dir: str

    @property
    def coordinate(self) -> dict[str, str]:
        return {"engine": self.repository, "revision": self.revision, "version": self.version}


def load_pin(factory_root: Path = TEMPLATE_ROOT) -> EnginePin:
    """The one engine this factory admits, read from the factory and nowhere else."""
    path = factory_root / PIN_PATH
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductResolutionError(
            f"cannot read the semantic compiler pin {path}: {exc}"
        ) from exc
    if not isinstance(document, dict) or document.get("schema") != PIN_SCHEMA:
        raise ProductResolutionError(f"{path} is not an {PIN_SCHEMA} document")
    fields: dict[str, str] = {}
    for key in ("repository", "revision", "package", "version", "module", "source_dir"):
        value = document.get(key)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ProductResolutionError(f"semantic compiler pin: {key} is not a usable token")
        fields[key] = value
    if not compiler.SLUG_RE.match(fields["repository"]):
        raise ProductResolutionError("semantic compiler pin: repository is not owner/name")
    if not compiler.OID_RE.match(fields["revision"]):
        raise ProductResolutionError("semantic compiler pin: revision is not a full object id")
    if not fields["module"].isidentifier():
        raise ProductResolutionError("semantic compiler pin: module is not an importable name")
    if "/" in fields["source_dir"] or fields["source_dir"] in ("", ".", ".."):
        raise ProductResolutionError(
            "semantic compiler pin: source_dir is not a plain directory name"
        )
    return EnginePin(**fields)


def engine_disagreements(claimed: Mapping[str, object], pin: EnginePin) -> list[str]:
    """Every way a binding's `compiler` coordinate names an engine other than the pin."""
    found: list[str] = []
    for key, expected in pin.coordinate.items():
        actual = claimed.get(key)
        if actual != expected:
            found.append(f"binding names compiler {key} {actual!r}, the factory pins {expected!r}")
    return found


# ─────────────────────────────────────────────────────────────────────────────
# The engine checkout: proven, never assumed
# ─────────────────────────────────────────────────────────────────────────────


def _project_table(pyproject: str) -> str:
    """The lines of the `[project]` table: from its header to the next table header."""
    lines: list[str] = []
    inside = False
    for line in pyproject.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            if inside:
                break
            inside = stripped == "[project]"
            continue
        if inside:
            lines.append(line)
    return "\n".join(lines)


def _git_facts(root: Path) -> tuple[Path, str, list[str], str]:
    """`(toplevel, HEAD, dirty paths, origin url)` of a checkout, or a refusal."""
    try:
        top = Path(prov.git(root, "rev-parse", "--show-toplevel").strip()).resolve()
        head = prov.git(root, "rev-parse", "HEAD").strip()
        dirty = [line for line in prov.git(root, "status", "--porcelain").splitlines() if line]
        origin = prov.git(root, "remote", "get-url", "origin").strip()
    except prov.ProvenanceError as exc:
        raise ProductResolutionError(f"semantic compiler checkout cannot be proven: {exc}") from exc
    return top, head, dirty, origin


def _assert_pinned_snapshot(root: Path, pin: EnginePin) -> None:
    """Root of its own checkout, at the pinned HEAD, clean, with the pinned origin."""
    top, head, dirty, origin = _git_facts(root)
    if top != root:
        raise ProductResolutionError(
            f"semantic compiler checkout {root} is not the root of its git checkout ({top})"
        )
    if head != pin.revision:
        raise ProductResolutionError(
            f"semantic compiler checkout is at {head[:12]}, the factory pins "
            f"{pin.repository}@{pin.revision[:12]} — only the pinned engine resolves a birth"
        )
    if dirty:
        shown = ", ".join(line.strip()[:60] for line in dirty[:8])
        raise ProductResolutionError(
            f"semantic compiler checkout is dirty ({len(dirty)} path(s)): {shown} — the "
            "pinned revision must name the bytes that run"
        )
    match = compiler.REMOTE_RE.search(origin)
    slug = f"{match.group(1)}/{match.group(2)}" if match else None
    if slug != pin.repository:
        raise ProductResolutionError(
            f"semantic compiler checkout origin is {slug or origin!r}, not {pin.repository}"
        )


def _assert_pinned_package(root: Path, pin: EnginePin) -> None:
    """`pyproject.toml` declares exactly the pinned package at the pinned version."""
    try:
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    except OSError as exc:
        raise ProductResolutionError(
            f"semantic compiler checkout has no pyproject.toml: {exc}"
        ) from exc
    project = _project_table(pyproject)
    name = _NAME_RE.search(project)
    version = _VERSION_RE.search(project)
    if name is None or name.group(1) != pin.package:
        raise ProductResolutionError(
            f"semantic compiler checkout declares package {name.group(1) if name else None!r}, "
            f"the factory pins {pin.package!r}"
        )
    if version is None or version.group(1) != pin.version:
        raise ProductResolutionError(
            f"semantic compiler checkout declares version "
            f"{version.group(1) if version else None!r}, the factory pins {pin.version!r}"
        )


def prove_engine_checkout(root: Path, pin: EnginePin) -> Path:
    """A clean checkout of exactly the pinned engine, or a refusal naming why.

    The same proof `--org-profile-src` gets: a tree that merely carries the
    right files is not the pinned engine. Its `origin` must name the pinned
    repository, HEAD must be the pinned revision, nothing may be modified or
    untracked, and the package the tree declares must be the pinned package at
    the pinned version. Only then does the revision the receipt records name
    the code that actually resolved the product.
    """
    root = root.resolve()
    if not root.is_dir():
        raise ProductResolutionError(f"semantic compiler checkout is not a directory: {root}")
    if not prov.is_git_repo(root):
        raise ProductResolutionError(f"semantic compiler checkout is not a git checkout: {root}")
    _assert_pinned_snapshot(root, pin)
    _assert_pinned_package(root, pin)
    if not (root / pin.source_dir / pin.module / "__init__.py").is_file():
        raise ProductResolutionError(
            f"semantic compiler checkout carries no {pin.source_dir}/{pin.module} package"
        )
    return root


# ─────────────────────────────────────────────────────────────────────────────
# Inputs: inside the snapshot, named by the payload
# ─────────────────────────────────────────────────────────────────────────────


def usable_input_path(value: object) -> bool:
    """A repository-relative file path: no root, no `.`/`..` segment, no odd bytes."""
    if not isinstance(value, str) or not value or value.startswith("/"):
        return False
    if "\\" in value or "\0" in value or "\n" in value or "\r" in value:
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def resolve_inputs(inputs: Mapping[str, object], source_root: Path) -> dict[str, Path]:
    """Every engine input as an absolute path confined to the source snapshot."""
    source_root = source_root.resolve()
    resolved: dict[str, Path] = {}
    for key in INPUT_KEYS:
        rel = inputs.get(key)
        if rel is None and key in OPTIONAL_INPUTS:
            rel = DEFAULT_CONTRACT_CATALOG
        if not usable_input_path(rel):
            raise ProductResolutionError(
                f"compiler input {key} is not a repository-relative path: {rel!r}"
            )
        assert isinstance(rel, str)
        path = (source_root / posixpath.normpath(rel)).resolve()
        if path != source_root and source_root not in path.parents:
            raise ProductResolutionError(f"compiler input {key} escapes the source snapshot: {rel}")
        if key in REQUIRED_INPUTS and not path.is_file():
            raise ProductResolutionError(f"compiler input {key} is not a file in the source: {rel}")
        resolved[key] = path
    return resolved


# ─────────────────────────────────────────────────────────────────────────────
# Reproduction
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Reproduction:
    """What the pinned engine produced from the exact inputs."""

    manifest: dict[str, object]
    exit_code: int

    @property
    def unresolved(self) -> list[object]:
        value = self.manifest.get("unresolved")
        return list(value) if isinstance(value, list) else [value]

    @property
    def resolved(self) -> bool:
        return self.exit_code == 0 and self.unresolved == []


def _snapshot_state(source_root: Path) -> tuple[str, str]:
    try:
        return (
            prov.git(source_root, "rev-parse", "HEAD").strip(),
            prov.git(source_root, "status", "--porcelain"),
        )
    except prov.ProvenanceError as exc:
        raise ProductResolutionError(f"source snapshot cannot be read: {exc}") from exc


def _engine_env(scratch: Path) -> dict[str, str]:
    """A from-scratch environment: PATH to find nothing it needs, HOME in scratch."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(scratch),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
    }
    for key in ("SYSTEMROOT", "TEMP", "TMP"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def reproduce_manifest(
    *,
    engine_root: Path,
    pin: EnginePin,
    source_root: Path,
    inputs: Mapping[str, object],
    python: str | None = None,
) -> Reproduction:
    """Run the pinned engine's product-build against the snapshot; return its manifest.

    The engine's own CLI is invoked, with the exact paths the binding names, in
    a child interpreter that inherits nothing from this process but PATH. The
    source snapshot must be a git checkout and must be exactly as it was once
    the engine has finished: HEAD unchanged, nothing modified, nothing left
    behind. A compiler that writes into the product tree would make the
    reproduced payload and the reproduced manifest describe different bytes.
    """
    source_root = source_root.resolve()
    if not prov.is_git_repo(source_root):
        raise ProductResolutionError(
            f"source snapshot is not a git checkout: {source_root} — product resolution is "
            "reproduced only against an immutable snapshot"
        )
    before = _snapshot_state(source_root)
    paths = resolve_inputs(inputs, source_root)
    engine_src = engine_root.resolve() / pin.source_dir
    scratch = Path(tempfile.mkdtemp(prefix="l9-product-resolution-"))
    try:
        output_dir = scratch / "build"
        result_path = scratch / "result.json"
        # -I: nothing inherited from this process's Python environment.
        # -B: no bytecode written into the engine checkout, so the checkout
        #     that was proven clean is still clean when the next proof runs.
        argv = [
            python or sys.executable,
            "-I",
            "-B",
            "-c",
            _BOOTSTRAP,
            str(engine_src),
            str(result_path),
            str(output_dir),
            "--topology",
            str(paths["topology"]),
            "--repository-spec",
            str(paths["repository_spec"]),
            "--workflow-spec",
            str(paths["workflow_spec"]),
            "--authority-lock",
            str(paths["authority_lock"]),
            "--contract-catalog",
            str(paths["contract_catalog"]),
        ]
        try:
            proc = subprocess.run(
                argv,
                cwd=str(scratch),
                env=_engine_env(scratch),
                capture_output=True,
                text=True,
                check=False,
                timeout=ENGINE_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProductResolutionError(f"semantic compiler could not be run: {exc}") from exc
        if not result_path.is_file():
            detail = ((proc.stderr or "") + (proc.stdout or "")).strip()
            raise ProductResolutionError(
                f"semantic compiler failed ({proc.returncode}) before producing a manifest: "
                f"{detail[-1200:]}"
            )
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProductResolutionError(f"semantic compiler result is unreadable: {exc}") from exc
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    after = _snapshot_state(source_root)
    if after != before:
        raise ProductResolutionError(
            "the semantic compiler changed the source snapshot while resolving it — a "
            "manifest reproduced from a moving tree proves nothing"
        )
    manifest = result.get("manifest") if isinstance(result, dict) else None
    code = result.get("exit_code") if isinstance(result, dict) else None
    if not isinstance(manifest, dict) or not isinstance(code, int):
        raise ProductResolutionError(
            "semantic compiler result does not carry a manifest and exit code"
        )
    return Reproduction(manifest=_json_round_trip(manifest), exit_code=code)


def _json_round_trip(document: Mapping[str, object]) -> dict[str, object]:
    """One canonical in-memory form on both sides of the comparison."""
    return json.loads(json.dumps(document, sort_keys=True))


# ─────────────────────────────────────────────────────────────────────────────
# Comparison
# ─────────────────────────────────────────────────────────────────────────────


def manifest_disagreements(reproduced: Reproduction, supplied: Mapping[str, object]) -> list[str]:
    """Every way the engine's answer differs from the manifest the birth was handed.

    All of them, not the first: a bundle is produced by a machine, and a gate
    that must be re-run to learn each fact is a gate that gets switched off.
    """
    found: list[str] = []
    produced = reproduced.manifest
    if produced.get("schema") != MANIFEST_SCHEMA:
        found.append(
            f"the pinned engine produced {produced.get('schema')!r}, not {MANIFEST_SCHEMA}"
        )
    if supplied.get("schema") != MANIFEST_SCHEMA:
        found.append(f"the supplied manifest is {supplied.get('schema')!r}, not {MANIFEST_SCHEMA}")
    if reproduced.exit_code != 0:
        found.append(
            f"the pinned engine exited {reproduced.exit_code}: the product did not resolve"
        )
    unresolved = reproduced.unresolved
    if unresolved:
        shown = "; ".join(str(entry)[:80] for entry in unresolved[:6])
        found.append(
            f"the pinned engine left {len(unresolved)} unresolved entr"
            f"{'y' if len(unresolved) == 1 else 'ies'}: {shown}"
        )
    produced_digest = produced.get("manifest_digest")
    supplied_digest = supplied.get("manifest_digest")
    if produced_digest != supplied_digest:
        found.append(
            f"manifest digest disagreement: the pinned engine resolves {produced_digest!r}, "
            f"the supplied manifest declares {supplied_digest!r}"
        )
    expected = _json_round_trip(supplied)
    if produced != expected:
        keys = sorted(
            key
            for key in set(produced) | set(expected)
            if produced.get(key, _MISSING) != expected.get(key, _MISSING)
        )
        found.append(
            "manifest document disagreement: the supplied manifest differs from the "
            f"reproduced one at {', '.join(keys) or 'the document root'}"
        )
    return found


_MISSING = object()


@dataclass(frozen=True)
class Resolution:
    """Evidence that the supplied manifest is what the pinned engine resolves."""

    engine: dict[str, str]
    manifest_digest: str
    inputs: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "engine": dict(self.engine),
            "manifest_digest": self.manifest_digest,
            "inputs": dict(self.inputs),
        }


def resolve_product(
    *,
    engine_root: Path,
    claimed_compiler: Mapping[str, object],
    source_root: Path,
    supplied_manifest: Mapping[str, object],
    factory_root: Path = TEMPLATE_ROOT,
    python: str | None = None,
) -> Resolution:
    """The whole proof, in order: pin, identity, checkout, reproduction, agreement."""
    pin = load_pin(factory_root)
    mismatches = engine_disagreements(claimed_compiler, pin)
    if mismatches:
        raise ProductResolutionError("; ".join(mismatches))
    inputs = claimed_compiler.get("inputs")
    if not isinstance(inputs, dict):
        raise ProductResolutionError("binding names no compiler inputs")
    engine = prove_engine_checkout(engine_root, pin)
    reproduction = reproduce_manifest(
        engine_root=engine, pin=pin, source_root=source_root, inputs=inputs, python=python
    )
    disagreements = manifest_disagreements(reproduction, supplied_manifest)
    if disagreements:
        raise ProductResolutionError("; ".join(disagreements))
    return Resolution(
        engine=pin.coordinate,
        manifest_digest=str(reproduction.manifest["manifest_digest"]),
        inputs={key: str(inputs[key]) for key in INPUT_KEYS if key in inputs},
    )
