#!/usr/bin/env python3
"""Compile a BirthPayload: which bytes, from which immutable source snapshot.

A birthing agent does not author a payload. It invokes this compiler against a
clean checkout of the actual source repository, and the compiler emits evidence:

    l9.birth-payload/v1   the source snapshot (repository, revision, tree)
                          the classification derived from the ownership contract
                          the Python packages found under src/
                          every file, path-sorted, with the sha256 of its bytes
                          one manifest digest over all of it

That is the whole contract. It is a MANIFEST, NOT A SECOND REPOSITORY: file
contents stay in the source tree and birth copies them from there. The compiled
payload only proves which bytes it authorized.

What is deliberately absent is as much of the design as what is present. No
capabilities, no desired CI, no repo class, no template version, no organization
policy, no target repository name, no birth timestamp, no absence declarations,
no per-file ownership classification. Every one of those either belongs to
another authority or is derivable from the files this manifest names, and
duplicating it here would create two truths for one question.

Absence needs no declaration. Under an authoritative payload,
`payload-ownership.yaml` already makes a `product` surface the source does not
supply mean "this product does not have one" — so a `"Dockerfile": absent` entry
would be a second way to say something the manifest already says by omission.

The digest is `birth_provenance.manifest_digest`, not a second hashing protocol.
One algorithm, three callers: this compiler, the birth receipt, and any human
with `sha256sum` who does not trust either.

Two proofs come out of one birth and are never merged:

    payload manifest_sha256   what exactly did the product SOURCE contribute?
    receipt  manifest_sha256   what exactly was the repository BORN containing?

    compile_birth_payload.py --source DIR [--out FILE] [--require-mode MODE]

Dependency-free at runtime, like the rest of the birth engine. The published
JSON Schema in `schemas/birth-payload.schema.json` is the contract for external
readers; `validate_payload_document` below is the mechanical gate, and
`tests/unit/test_birth_payload_compiler.py` holds the two to the same verdicts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path


def _load_sibling(name: str):
    """Load a module that lives next to this file, wherever this file lives.

    Not a bare `import`: that resolves for free when the script is executed
    directly (sys.path[0] is the script's directory) and fails when a fixture,
    a renamed tree, or a test harness loads this file by path instead.
    """
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


# The compiler that WRITES the manifest digest and the receipt that carries one
# share a module deliberately: two copies of a digest algorithm are two digests.
prov = _load_sibling("birth_provenance")
ownership_contract = _load_sibling("payload_ownership")

TEMPLATE_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "l9.birth-payload/v1"
SCHEMA_PATH = "scripts/birth-runner/schemas/birth-payload.schema.json"
MODES = ("authoritative", "additive")

SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
OID_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REMOTE_RE = re.compile(r"[:/]([A-Za-z0-9][A-Za-z0-9._-]*)/([A-Za-z0-9][A-Za-z0-9._-]*?)(?:\.git)?$")


class PayloadCompileError(RuntimeError):
    """A payload could not be compiled, or could not be trusted once compiled."""


# ─────────────────────────────────────────────────────────────────────────────
# The immutable source snapshot
# ─────────────────────────────────────────────────────────────────────────────


def assert_immutable_snapshot(source: Path) -> None:
    """A payload is compiled from a committed, clean tree or not at all (BP-004).

    Compiling from moving bytes produces a manifest that was never true of any
    commit: the hashes describe whatever the working tree happened to contain
    during the walk, and the revision pinned beside them describes something
    else. There is no partial credit here — a dirty tree is a refusal, not a
    warning, because every downstream proof is derived from this one.
    """
    if not source.is_dir():
        raise PayloadCompileError(f"source is not a directory: {source}")
    if not prov.is_git_repo(source):
        raise PayloadCompileError(
            f"source is not a git checkout: {source} — an authoritative payload is "
            "compiled from an immutable snapshot, and only git can pin one"
        )
    if not prov.has_commits(source):
        raise PayloadCompileError(
            f"source has no commits: {source} — there is no revision to compile against"
        )
    dirty = [
        line for line in prov.git(source, "status", "--porcelain").splitlines() if line.strip()
    ]
    if dirty:
        shown = ", ".join(line.strip()[:60] for line in dirty[:8])
        raise PayloadCompileError(
            f"source worktree is dirty ({len(dirty)} path(s)): {shown} — commit or stash "
            "first. A payload compiled from uncommitted files pins a revision that does "
            "not describe the bytes it hashed."
        )


def source_revision(source: Path) -> tuple[str, str]:
    """`(commit sha, tree sha)` for the snapshot, both full 40-character oids."""
    revision = prov.git(source, "rev-parse", "HEAD").strip()
    tree_sha = prov.git(source, "rev-parse", "HEAD^{tree}").strip()
    for label, value in (("revision", revision), ("tree", tree_sha)):
        if not OID_RE.match(value):
            raise PayloadCompileError(f"source {label} is not a full object id: {value!r}")
    return revision, tree_sha


def source_repository(source: Path, override: str | None = None) -> str:
    """The source's own `owner/name`, from `origin` unless explicitly given.

    Source truth, not target truth: this names where the product bytes came
    from. The repository being BORN is a birth-request input (`REPO`), and
    putting it here would make the compiled payload describe two repositories.
    """
    if override:
        slug = override.strip()
        if not SLUG_RE.match(slug):
            raise PayloadCompileError(f"--source-repository {slug!r} is not owner/name")
        return slug
    try:
        url = prov.git(source, "remote", "get-url", "origin").strip()
    except prov.ProvenanceError as exc:
        raise PayloadCompileError(
            f"source has no `origin` remote, so its identity cannot be resolved: {exc} — "
            "pass --source-repository owner/name"
        ) from exc
    match = REMOTE_RE.search(url)
    if not match:
        raise PayloadCompileError(
            f"cannot read owner/name out of origin url {url!r} — pass --source-repository"
        )
    return f"{match.group(1)}/{match.group(2)}"


def _assert_usable_path(source: Path, rel: str) -> None:
    """One tracked path, checked for the shapes that make a manifest a lie."""
    if rel.startswith("/") or "\\" in rel or "\0" in rel:
        raise PayloadCompileError(f"unusable path in source: {rel!r}")
    if any(part in ("", ".", "..") for part in rel.split("/")):
        raise PayloadCompileError(f"unusable path in source: {rel!r}")
    path = source / rel
    if path.is_symlink():
        _assert_symlink_stays_inside(source, rel, path)
        return
    if not path.exists():
        raise PayloadCompileError(f"tracked path is missing from the source tree: {rel}")
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode):
        raise PayloadCompileError(
            f"{rel} is not a regular file or a symlink — a payload manifest covers "
            "file bytes, and a device, socket, or fifo has none to cover"
        )


def _assert_symlink_stays_inside(source: Path, rel: str, path: Path) -> None:
    """A symlink may point anywhere it likes, as long as it stays in the payload.

    One that escapes the source root is a file the manifest cannot describe:
    birth would copy the link, and what it resolves to on the machine that
    assembles the newborn is not what was hashed here.
    """
    target = os.readlink(path)
    resolved = Path(os.path.normpath(os.path.join(str((source / rel).parent), target)))
    root = Path(os.path.normpath(str(source)))
    if not (resolved == root or root in resolved.parents):
        raise PayloadCompileError(
            f"symlink {rel} -> {target} escapes the source root — a payload cannot "
            "authorize bytes that live outside the snapshot it pinned"
        )


def _assert_no_case_collisions(paths: list[str]) -> None:
    """Two paths differing only in case collapse into one on macOS and Windows.

    Which of the two bytes survive assembly is then decided by copy order rather
    than by the manifest, so the newborn cannot match the digest that authorized
    it. Fail while both are still visible.
    """
    seen: dict[str, str] = {}
    for rel in paths:
        key = rel.lower()
        if key in seen:
            raise PayloadCompileError(
                f"paths collide case-insensitively: {seen[key]} and {rel} — one of them "
                "would be lost on a case-insensitive filesystem"
            )
        seen[key] = rel


def source_files(source: Path) -> dict[str, bytes]:
    """Every payload-contributing file in the snapshot, path -> the bytes git stores.

    Defined over `git ls-files`, so it is exactly what a commit of this tree
    would carry — a gitignored build artifact lying in the work directory cannot
    put a path in the manifest that assembly will never copy.

    Machine state is excluded here for the same reason the overlay excludes it:
    the manifest must equal the bytes birth copies, and the overlay does not
    copy `__pycache__`. Two different answers to "what is in the payload" is the
    whole failure this contract exists to remove.
    """
    tracked = prov.git_tracked_paths(source)
    excluded = {rel for rel in tracked if ownership_contract.is_machine_state(Path(rel))}
    kept = [rel for rel in tracked if rel not in excluded]
    if not kept:
        raise PayloadCompileError(f"source snapshot contains no files: {source}")
    _assert_no_case_collisions(kept)
    for rel in kept:
        _assert_usable_path(source, rel)
    claimed = sorted(set(kept) & set(prov.ENGINE_OWNED_PATHS))
    if claimed:
        raise PayloadCompileError(
            f"source claims engine-owned birth paths: {claimed} — birth provenance is "
            "written by the birth engine, after the payload, and is never supplied by a "
            "product tree"
        )
    return prov.worktree_manifest(source, exclude=excluded)


# ─────────────────────────────────────────────────────────────────────────────
# Compilation
# ─────────────────────────────────────────────────────────────────────────────


def compile_payload(
    source: Path,
    *,
    template_src: Path,
    source_repository_override: str | None = None,
    require_mode: str | None = None,
) -> dict[str, object]:
    """Compile the BirthPayload for a source snapshot. Evidence only.

    The mode is PROPOSED here from the ownership contract's `repository_shape`.
    The birth engine re-derives it from the same contract rather than trusting
    this field, so a hand-edited `mode` cannot promote a fragment into an
    authoritative payload that deletes product surfaces.
    """
    if require_mode is not None and require_mode not in MODES:
        raise PayloadCompileError(f"unknown --require-mode {require_mode!r}: expect one of {MODES}")

    source = source.resolve()
    assert_immutable_snapshot(source)
    revision, tree_sha = source_revision(source)
    repository = source_repository(source, source_repository_override)

    try:
        ownership = ownership_contract.load_ownership(template_src)
    except ownership_contract.OwnershipContractError as exc:
        raise PayloadCompileError(str(exc)) from exc

    matched = ownership_contract.matched_shape(source, ownership)
    authoritative = ownership_contract.is_repository_payload(source, ownership)
    mode = "authoritative" if authoritative else "additive"
    if require_mode is not None and mode != require_mode:
        missing = sorted(set(ownership["repository_shape"]) - set(matched))
        raise PayloadCompileError(
            f"--require-mode {require_mode} but the source compiles as {mode}"
            + (f" — repository_shape paths absent: {', '.join(missing)}" if missing else "")
        )

    files = source_files(source)
    document: dict[str, object] = {
        "schema": SCHEMA,
        "source": {"repository": repository, "revision": revision, "tree_sha": tree_sha},
        "mode": mode,
        "repository_shape": {"matched": matched},
        "packages": {"python": ownership_contract.payload_package_dirs(source)},
        "files": [
            {"path": rel, "sha256": hashlib.sha256(body).hexdigest()}
            for rel, body in sorted(files.items())
        ],
        "manifest_sha256": prov.manifest_digest(files),
    }
    # A compiler that emits a document its own validator rejects is worse than
    # one that fails: the rejection then lands on the birth, one layer away from
    # the mistake.
    assert_valid_payload_document(document)
    return document


def render_payload(document: dict[str, object]) -> str:
    """Pretty on disk, canonical for the digest. The digest never reads this."""
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# The document contract, enforced without a schema library
# ─────────────────────────────────────────────────────────────────────────────


def _check_str(
    errors: list[str], doc: dict, key: str, pattern: re.Pattern[str], where: str
) -> None:
    value = doc.get(key)
    if not isinstance(value, str) or not pattern.match(value):
        errors.append(f"{where}.{key} is not a valid {pattern.pattern}")


def _check_str_list(errors: list[str], doc: dict, key: str, where: str) -> None:
    value = doc.get(key)
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        errors.append(f"{where}.{key} is not a list of non-empty strings")
    elif len(set(value)) != len(value):
        errors.append(f"{where}.{key} contains duplicates")


def _check_object(errors: list[str], doc: dict, key: str, allowed: tuple[str, ...]) -> dict:
    value = doc.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} is not an object")
        return {}
    extra = sorted(set(value) - set(allowed))
    if extra:
        errors.append(f"{key} carries unknown key(s): {', '.join(extra)}")
    return value


def _check_files(errors: list[str], doc: dict) -> None:
    entries = doc.get("files")
    if not isinstance(entries, list) or not entries:
        errors.append("files is not a non-empty array")
        return
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"files[{index}] is not an object")
            continue
        extra = sorted(set(entry) - {"path", "sha256"})
        if extra:
            errors.append(f"files[{index}] carries unknown key(s): {', '.join(extra)}")
        path = entry.get("path")
        if not isinstance(path, str) or not _usable_manifest_path(path):
            errors.append(f"files[{index}].path is not a repository-relative path: {path!r}")
        elif path in seen:
            errors.append(f"files[{index}].path is a duplicate: {path}")
        else:
            seen.add(path)
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not SHA256_RE.match(digest):
            errors.append(f"files[{index}].sha256 is not a sha256 hex digest")


def _usable_manifest_path(path: str) -> bool:
    if not path or path.startswith("/") or "\\" in path or "\0" in path:
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def validate_payload_document(document: object) -> list[str]:
    """Every way this document fails the contract, or an empty list.

    Reports all of them rather than the first: a compiled payload is produced by
    a machine, and an operator fixing one field at a time through six round
    trips is how a fail-closed gate gets switched off.
    """
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["payload is not a JSON object"]
    schema = document.get("schema")
    if schema != SCHEMA:
        # Version first and alone. Every other rule below is v1's; reporting
        # them against an unrecognized schema would describe a contract the
        # document never claimed to satisfy.
        return [f"unrecognized payload schema {schema!r}: this birth engine reads {SCHEMA}"]
    allowed = (
        "schema",
        "source",
        "mode",
        "repository_shape",
        "packages",
        "files",
        "manifest_sha256",
    )
    extra = sorted(set(document) - set(allowed))
    if extra:
        errors.append(f"payload carries unknown key(s): {', '.join(extra)}")

    source = _check_object(errors, document, "source", ("repository", "revision", "tree_sha"))
    if source:
        _check_str(errors, source, "repository", SLUG_RE, "source")
        _check_str(errors, source, "revision", OID_RE, "source")
        _check_str(errors, source, "tree_sha", OID_RE, "source")

    if document.get("mode") not in MODES:
        errors.append(f"mode is not one of {MODES}")

    shape = _check_object(errors, document, "repository_shape", ("matched",))
    if shape:
        _check_str_list(errors, shape, "matched", "repository_shape")

    packages = _check_object(errors, document, "packages", ("python",))
    if packages:
        _check_str_list(errors, packages, "python", "packages")

    _check_files(errors, document)
    _check_str(errors, document, "manifest_sha256", SHA256_RE, "payload")
    return errors


def assert_valid_payload_document(document: object) -> None:
    errors = validate_payload_document(document)
    if errors:
        raise PayloadCompileError("malformed birth payload: " + "; ".join(errors))


def load_payload(path: Path) -> dict[str, object]:
    """Read and validate a compiled payload from disk."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PayloadCompileError(f"cannot read birth payload {path}: {exc}") from exc
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PayloadCompileError(f"birth payload {path} is not JSON: {exc}") from exc
    assert_valid_payload_document(document)
    assert isinstance(document, dict)
    return document


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="compile_birth_payload.py",
        description="Compile an l9.birth-payload/v1 contract from a clean source checkout.",
    )
    parser.add_argument("--source", required=True, help="clean checkout of the source repository")
    parser.add_argument(
        "--template-src",
        default=str(TEMPLATE_ROOT),
        help="l9-repo-template checkout that owns payload-ownership.yaml",
    )
    parser.add_argument("--out", default=None, help="write the payload here (default: stdout)")
    parser.add_argument(
        "--source-repository",
        default=None,
        help="owner/name of the SOURCE, when it has no origin remote",
    )
    parser.add_argument(
        "--require-mode",
        default=None,
        choices=list(MODES),
        help="fail unless the source compiles as this mode",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        document = compile_payload(
            Path(args.source).expanduser(),
            template_src=Path(args.template_src).expanduser().resolve(),
            source_repository_override=args.source_repository,
            require_mode=args.require_mode,
        )
    except (PayloadCompileError, prov.ProvenanceError) as exc:
        print(f"PAYLOAD COMPILE FAIL: {exc}", file=sys.stderr)
        return 2

    rendered = render_payload(document)
    if args.out:
        out = Path(args.out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    source = document["source"]
    assert isinstance(source, dict)
    files = document["files"]
    assert isinstance(files, list)
    print(
        f"PAYLOAD COMPILE: PASS  {source['repository']}@{str(source['revision'])[:12]}  "
        f"{document['mode']}  {len(files)} file(s)  "
        f"manifest sha256:{str(document['manifest_sha256'])[:12]}"
        + (f"  -> {args.out}" if args.out else ""),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
