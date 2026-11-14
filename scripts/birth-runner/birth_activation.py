#!/usr/bin/env python3
"""ACTIVATE: the post-PUBLISH stage that makes a published newborn an active node.

PUBLISH ends with a sealed root on GitHub and nothing else. A node is not active
until its metadata is governed and its topology is compiled from what it
actually is, and both of those are facts ABOUT a published commit:

    1. emit   .l9/meta-authority.yaml   l9.meta-authority/v2, bound to the
                                         organization Semantic Foundation the
                                         birth used and to the node's product
    2. apply  l9-meta-injector apply .  governed write of .l9/metadata-index.jsonl
    3. check  l9-meta-injector check .  read-only; must exit 0
    4. commit                            -> the post-injection SHA
    5. model  repository-model-cli.js    Repository Model bundle of THAT SHA,
                                         --semantics-root <full .github checkout>
                                         --require-semantic-binding
    6. topology compile-packet / validate-packet / inspect-packet /
                verify-determinism       over exactly that bundle
    7. commit  the topology packet under PACKET_DIR, for later world-model
               ingestion (ingestion is not this stage's business)

The branch that carries 4 and 7 becomes the newborn's first pull request, which
is also the event the organization required workflow evaluates: activation is
what earns `BORN`, not a separate ceremony.

This module is the ONE call site of the meta-injector and the topology compiler
in the factory. Both are pinned in `activation.pin.json` to an exact commit;
nothing here reads a moving branch. The workflow job that runs it
(`repo-birth-dispatch.yml` `activate`) owns the network and the token; this
module owns the order and refuses on the first failure, so a newborn is never
left with half an activation committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
PIN_PATH = HERE / "activation.pin.json"
PIN_SCHEMA = "l9.birth-activation-pin/v1"

META_AUTHORITY_PATH = ".l9/meta-authority.yaml"
METADATA_INDEX_PATH = ".l9/metadata-index.jsonl"
# Governed home of the committed topology packet in a node repository.
PACKET_DIR = ".l9/topology-packet"
TOPOLOGY_PATH = "product-topology.yaml"

FOUNDATION_REPOSITORY = "Quantum-L9/.github"
FOUNDATION_RELEASES = Path("docs/semantic-foundation")
SEMANTICS_DIR = Path("semantics")
# The Foundation ledgers a node binds. The dependency set the injector itself
# binds, with the node archetype ledger in place of the dependency one.
NODE_LEDGERS = (
    "l9.authority-model/global@1",
    "l9.artifact-model/global@1",
    "l9.artifact-header-model/global@1",
    "l9.vocabulary/global@1",
    "l9.identity-model/global@1",
    "l9.product-kinds/global@1",
    "l9.node-archetypes/global@1",
)
ARTIFACT_ID_LINE = re.compile(r"^artifact_id:\s*(\S+)\s*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_DIR = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
# l9.meta-authority/v2 `product.id` admits no dot; see `product_binding`.
PRODUCT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SLUG_RE = re.compile(r"^[^/\s]+/[^/\s]+$")


class ActivationError(RuntimeError):
    """Activation refused. Nothing after the failing step ran."""


# ───────────────────────────── pins ─────────────────────────────


def load_pin(path: Path = PIN_PATH) -> dict[str, dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("schema") != PIN_SCHEMA:
        raise ActivationError(f"{path.name} is not {PIN_SCHEMA}")
    pins: dict[str, dict[str, Any]] = {}
    for key in ("meta_injector", "constellation_topology"):
        pin = doc.get(key)
        if (
            not isinstance(pin, dict)
            or not SLUG_RE.match(str(pin.get("repository") or ""))
            or not SHA_RE.match(str(pin.get("revision") or ""))
        ):
            raise ActivationError(f"{path.name} has no usable {key!r} pin")
        pins[key] = pin
    return pins


def assert_checkout_at(root: Path, revision: str, label: str) -> None:
    head = _git(root, "rev-parse", "HEAD")
    if head != revision:
        raise ActivationError(f"{label} checkout is at {head}, the pin names {revision}")
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ActivationError(f"{label} checkout is dirty")


# ───────────────────────────── authority ─────────────────────────────


def _ledger_digests(semantics: Path) -> dict[str, list[str]]:
    """`artifact_id -> [sha256 of each claiming file]`, the injector's own algorithm."""
    claims: dict[str, list[str]] = {}
    for path in sorted(semantics.iterdir()):
        if path.suffix != ".yaml" or path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        for line in data.decode("utf-8").splitlines():
            match = ARTIFACT_ID_LINE.match(line)
            if match:
                claims.setdefault(match.group(1), []).append(
                    "sha256:" + hashlib.sha256(data).hexdigest()
                )
                break
    return claims


def foundation_binding(org_root: Path) -> dict[str, Any]:
    """The Semantic Foundation binding of the exact `.github` revision the birth used.

    Every field is read from that checkout: the revision is its HEAD, the release
    is the newest released Foundation version present at it, the admission is
    what that release's own manifest states, and each ledger digest is the digest
    of the one file that claims the ledger. Nothing is inferred; a ledger that is
    missing or claimed twice refuses.
    """
    revision = _git(org_root, "rev-parse", "HEAD")
    releases = sorted(
        (tuple(int(x) for x in m.groups()), p.name)
        for p in (org_root / FOUNDATION_RELEASES).iterdir()
        if p.is_dir() and (m := VERSION_DIR.match(p.name))
    )
    if not releases:
        raise ActivationError(f"{FOUNDATION_REPOSITORY} has no released Semantic Foundation")
    release = releases[-1][1]
    manifest = org_root / FOUNDATION_RELEASES / release / "MANIFEST.md"
    status = ""
    if manifest.is_file():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("release status:"):
                status = line.upper()
                break
    if "CANDIDATE" in status:
        admission = "candidate"
    elif "ADMITTED" in status:
        admission = "admitted"
    else:
        admission = "Unknown"
    claims = _ledger_digests(org_root / SEMANTICS_DIR)
    ledgers: dict[str, str] = {}
    for ledger in NODE_LEDGERS:
        found = claims.get(ledger) or []
        if len(found) != 1:
            raise ActivationError(
                f"ledger {ledger} is claimed by {len(found)} file(s) at "
                f"{FOUNDATION_REPOSITORY}@{revision[:12]}; exactly one is required"
            )
        ledgers[ledger] = found[0]
    return {
        "repository": FOUNDATION_REPOSITORY,
        "revision": revision,
        "release": release,
        "admission": admission,
        "ledgers": ledgers,
    }


def product_binding(newborn: Path, slug: str) -> dict[str, str]:
    """The node's product, from its own `product-topology.yaml`.

    `l9.meta-authority/v2` admits no dot in `product.id`, so the product's
    declared `name` (the repository-safe coordinate the topology itself carries,
    `l9-state` for `l9.state`) is bound rather than a transformed id; a product
    whose name does not match the schema refuses instead of being rewritten.
    """
    path = newborn / TOPOLOGY_PATH
    if not path.is_file():
        raise ActivationError(
            f"newborn has no {TOPOLOGY_PATH}; activation binds a declared product"
        )
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    product = doc.get("product") if isinstance(doc, dict) else None
    if not isinstance(product, dict):
        raise ActivationError(f"{TOPOLOGY_PATH} declares no product")
    name = str(product.get("name") or "")
    kind = str(product.get("kind") or "")
    archetype = str(product.get("archetype_ref") or "")
    if not PRODUCT_ID_RE.match(name):
        raise ActivationError(f"product name {name!r} is not an l9.meta-authority/v2 product id")
    if kind not in ("node", "dependency"):
        raise ActivationError(f"product kind {kind!r} cannot be activated")
    if not archetype:
        raise ActivationError("product declares no archetype_ref")
    if not SLUG_RE.match(slug):
        raise ActivationError(f"repository {slug!r} is not owner/name")
    # The injector proves the bound product IS the repository it models
    # (`repository-model-cli --name` must equal `product.id`), so the product's
    # declared name has to be the repository's name; a mismatch is refused, never
    # papered over by choosing one of the two.
    if name != slug.split("/", 1)[1]:
        raise ActivationError(
            f"product name {name!r} is not the repository name {slug.split('/', 1)[1]!r}"
        )
    return {"id": name, "owner": slug, "kind": kind, "archetype": archetype}


def render_meta_authority(
    *, injector: dict[str, Any], foundation: dict[str, Any], product: dict[str, str]
) -> str:
    """Byte-stable YAML in exactly the layout the injector's parser admits."""
    lines = [
        "schema: l9.meta-authority/v2",
        "writer:",
        f"  repository: {injector['repository']}",
        # The immutable commit, never a tag name a release could move.
        f"  ref: {injector['revision']}",
        "default_carrier: central_manifest",
        "legacy_writers: forbidden",
        "inline_allow: []",
        "semantic_foundation:",
        f"  repository: {foundation['repository']}",
        f"  revision: {foundation['revision']}",
        f"  release: {foundation['release']}",
        f"  admission: {foundation['admission']}",
        "  ledgers:",
        *(f"    {k}: {v}" for k, v in foundation["ledgers"].items()),
        "product:",
        f"  id: {product['id']}",
        f"  owner: {product['owner']}",
        f"  kind: {product['kind']}",
        f"  archetype: {product['archetype']}",
    ]
    return "\n".join(lines) + "\n"


# ───────────────────────────── execution ─────────────────────────────


def _git(root: Path, *argv: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *argv], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise ActivationError(f"git {' '.join(argv)} failed: {proc.stderr.strip()[-400:]}")
    return proc.stdout.strip()


def _step(cmd: list[str], *, cwd: Path, label: str) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-1500:]
        raise ActivationError(f"{label} failed ({proc.returncode}):\n{tail}")
    return proc.stdout


@dataclass
class Activation:
    repository: str
    root_sha: str
    injected_sha: str = ""
    packet_sha: str = ""
    steps: list[dict[str, str]] = field(default_factory=list)

    def record(self, step: str, detail: str) -> None:
        self.steps.append({"step": step, "status": "PASS", "detail": detail})


def activate(
    *,
    newborn: Path,
    slug: str,
    org_root: Path,
    injector_root: Path,
    topology_cli: list[str],
    topology_root: Path,
    work: Path,
    author: tuple[str, str],
    pins: dict[str, dict[str, Any]] | None = None,
    verify_pins: bool = True,
) -> Activation:
    pins = pins or load_pin()
    if verify_pins:
        assert_checkout_at(injector_root, pins["meta_injector"]["revision"], "meta-injector")
        assert_checkout_at(
            topology_root, pins["constellation_topology"]["revision"], "constellation-topology"
        )
    # The topology compiler reads its own profile (`.l9/topology-profile.yaml`)
    # from its checkout: the pinned compiler's configuration, never the newborn's.
    repo_root = ["--repo-root", str(topology_root)]
    act = Activation(repository=slug, root_sha=_git(newborn, "rev-parse", "HEAD"))
    identity = ["-c", f"user.name={author[0]}", "-c", f"user.email={author[1]}"]
    inj = ["node", str(injector_root / "scripts" / "operation-cli.js")]

    authority = render_meta_authority(
        injector=pins["meta_injector"],
        foundation=foundation_binding(org_root),
        product=product_binding(newborn, slug),
    )
    (newborn / META_AUTHORITY_PATH).parent.mkdir(parents=True, exist_ok=True)
    (newborn / META_AUTHORITY_PATH).write_text(authority, encoding="utf-8")
    act.record("emit", META_AUTHORITY_PATH)

    _step([*inj, "apply", "."], cwd=newborn, label="l9-meta-injector apply")
    act.record("apply", METADATA_INDEX_PATH)
    _step([*inj, "check", "."], cwd=newborn, label="l9-meta-injector check")
    act.record("check", "exit 0")
    _git(newborn, "add", "--", META_AUTHORITY_PATH, METADATA_INDEX_PATH)
    _git(
        newborn,
        *identity,
        "commit",
        "-q",
        "-m",
        "chore(activation): governed metadata (l9-meta-injector "
        f"{pins['meta_injector']['revision'][:12]})",
    )
    act.injected_sha = _git(newborn, "rev-parse", "HEAD")
    act.record("commit", act.injected_sha)

    bundle = work / "repository-model"
    _step(
        [
            "node",
            str(injector_root / "scripts" / "repository-model-cli.js"),
            str(newborn),
            "--name",
            slug.split("/", 1)[1],
            "--revision",
            f"git:{act.injected_sha}",
            "--out",
            str(bundle),
            "--semantics-root",
            str(org_root),
            "--require-semantic-binding",
        ],
        cwd=injector_root,
        label="repository-model-cli",
    )
    act.record("model", f"git:{act.injected_sha}")

    compiled = work / "topology-packet"
    _step(
        [
            *topology_cli,
            "compile-packet",
            *repo_root,
            "--input-bundle",
            str(bundle),
            "--out",
            str(compiled),
        ],
        cwd=work,
        label="l9-topology compile-packet",
    )
    _step(
        [
            *topology_cli,
            "validate-packet",
            *repo_root,
            "--input-bundle",
            str(compiled),
            "--repository-bundle",
            str(bundle),
        ],
        cwd=work,
        label="l9-topology validate-packet",
    )
    _step(
        [*topology_cli, "inspect-packet", "--input-bundle", str(compiled)],
        cwd=work,
        label="l9-topology inspect-packet",
    )
    _step(
        [*topology_cli, "verify-determinism", *repo_root, "--input-bundle", str(bundle)],
        cwd=work,
        label="l9-topology verify-determinism",
    )
    act.record("topology", "compile/validate/inspect/verify-determinism")

    target = newborn / PACKET_DIR
    if target.exists():
        raise ActivationError(f"{PACKET_DIR} already exists in the newborn")
    for path in sorted(compiled.rglob("*")):
        if path.is_file():
            dest = target / path.relative_to(compiled)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())
    _git(newborn, "add", "--", PACKET_DIR)
    _git(
        newborn,
        *identity,
        "commit",
        "-q",
        "-m",
        f"chore(activation): topology packet of {act.injected_sha[:12]} "
        f"(l9-constellation-topology {pins['constellation_topology']['revision'][:12]})",
    )
    act.packet_sha = _git(newborn, "rev-parse", "HEAD")
    act.record("commit", act.packet_sha)
    return act


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--newborn", type=Path, required=True, help="checkout of the published root"
    )
    parser.add_argument("--repository", required=True, help="owner/name of the newborn")
    parser.add_argument(
        "--org-root", type=Path, required=True, help="full Quantum-L9/.github checkout"
    )
    parser.add_argument(
        "--injector", type=Path, required=True, help="built l9-meta-injector at the pin"
    )
    parser.add_argument("--topology-cli", required=True, help="the pinned l9-topology executable")
    parser.add_argument(
        "--topology-root",
        type=Path,
        required=True,
        help="l9-constellation-topology checkout at the pin",
    )
    parser.add_argument(
        "--work", type=Path, required=True, help="scratch directory outside the newborn"
    )
    parser.add_argument("--author-name", default="l9-repo-birth[bot]")
    parser.add_argument("--author-email", default="l9-repo-birth[bot]@users.noreply.github.com")
    parser.add_argument("--receipt", type=Path, help="write the activation receipt here")
    args = parser.parse_args(argv)
    try:
        act = activate(
            newborn=args.newborn.resolve(),
            slug=args.repository,
            org_root=args.org_root.resolve(),
            injector_root=args.injector.resolve(),
            topology_cli=[args.topology_cli],
            topology_root=args.topology_root.resolve(),
            work=args.work.resolve(),
            author=(args.author_name, args.author_email),
        )
    except ActivationError as exc:
        print(f"ACTIVATION FAIL: {exc}", file=sys.stderr)
        return 1
    receipt = json.dumps(act.__dict__, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.write_text(receipt, encoding="utf-8")
    print(receipt, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
