"""End-to-end local birth: stages 1-5, no remote, no network.

This is the acceptance test for `make new-repo`. It asserts the property the
whole orchestrator exists to provide: when the command returns PASS the
repository is *born* — identity stamped everywhere, lock resolved for its own
name, org birth profile applied, and the full product gate green — rather than
"created, now go do seven other things".

Skipped when `uv` is absent: stage 3 resolves a real lock, and faking that
would test the fake.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BIRTH_RUNNER = REPO / "scripts" / "birth-runner"
RUNNER = BIRTH_RUNNER / "new_repo.py"
_SPEC = importlib.util.spec_from_file_location("l9_birth_new_repo_it", RUNNER)
assert _SPEC is not None
assert _SPEC.loader is not None
new_repo = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = new_repo
_SPEC.loader.exec_module(new_repo)
prov = new_repo.prov

# A birth takes ~40s and only means something in a pristine template checkout.
# Two things must never run it:
#   1. A repository born FROM the template. It carries this file, but its
#      `src/l9_example_pkg` is gone, so a birth from it would fail preflight —
#      correctly, and uselessly.
#   2. A nested gate. `make pr-check` re-runs pytest, and the birth orchestrator
#      runs the newborn's own `pytest -q` in stage 5. Either would recurse.
_PRISTINE_TEMPLATE = (REPO / "src" / "l9_example_pkg").is_dir()

pytestmark = [
    pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed on runner PATH"),
    pytest.mark.skipif(
        not _PRISTINE_TEMPLATE,
        reason="not a pristine l9-repo-template checkout — birth acceptance does not apply",
    ),
    pytest.mark.skipif(
        os.environ.get("L9_SKIP_BIRTH_ACCEPTANCE") == "1",
        reason="L9_SKIP_BIRTH_ACCEPTANCE=1 — nested gate, would recurse",
    ),
]


# Stage 4 materializes the applicable org files by running the ORGANIZATION's
# own `ops/build-seed-payload.js`, so a birth needs a real Quantum-L9/.github
# checkout — not a stand-in. A hand-written fake builder would prove only that
# the fake works, which is the opposite of what an acceptance test is for.
def _real_org_checkout() -> Path | None:
    """A genuine Quantum-L9/.github working tree, or None.

    Looks at `L9_ORG_GITHUB_SRC` first, then the usual sibling checkout. The
    marker of "genuine" is that it carries the payload builder this birth will
    actually execute.
    """
    candidates = []
    env_src = os.environ.get("L9_ORG_GITHUB_SRC")
    if env_src:
        candidates.append(Path(env_src))
    candidates.append(REPO.parent / ".github")
    for root in candidates:
        if (root / "ops" / "build-seed-payload.js").is_file() and (
            root / "policies" / "repo-classes.yml"
        ).is_file():
            return root.resolve()
    return None


ORG_SRC = _real_org_checkout()

pytestmark.append(
    pytest.mark.skipif(
        ORG_SRC is None,
        reason=(
            "no Quantum-L9/.github checkout found (set L9_ORG_GITHUB_SRC or place one "
            "beside this repo) — birth materializes org files with the org's own builder"
        ),
    )
)


def _birth(
    tmp_path: Path,
    *extra: str,
    repo: str = "l9-birth-acceptance",
    pkg: str = "l9_birth_acceptance",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["L9_SKIP_BIRTH_ACCEPTANCE"] = "1"
    return subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--repo",
            repo,
            "--pkg",
            pkg,
            "--desc",
            "Local birth acceptance fixture",
            "--work-dir",
            str(tmp_path / "work"),
            "--org-profile-src",
            str(ORG_SRC),
            "--no-remote",
            *extra,
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.fixture(scope="module")
def born(tmp_path_factory: pytest.TempPathFactory) -> tuple[subprocess.CompletedProcess[str], Path]:
    tmp_path = tmp_path_factory.mktemp("birth")
    proc = _birth(tmp_path)
    return proc, tmp_path / "work" / "l9-birth-acceptance"


def test_birth_passes(born: tuple[subprocess.CompletedProcess[str], Path]) -> None:
    proc, _ = born
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BIRTH: PASS" in proc.stdout


def test_every_stage_reports(born: tuple[subprocess.CompletedProcess[str], Path]) -> None:
    proc, _ = born
    for label in ("uv.lock generated", "org defaults", "forbid clean", "inventory", "lock"):
        assert label in proc.stdout, f"receipt omits {label!r}"
    assert "FAIL" not in proc.stdout


def test_identity_is_stamped_everywhere(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    _, dest = born
    assert (dest / "src" / "l9_birth_acceptance" / "app.py").is_file()
    assert not (dest / "src" / "l9_example_pkg").exists()

    pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "l9-birth-acceptance"' in pyproject
    assert 'description = "Local birth acceptance fixture"' in pyproject

    for rel in (".l9/ownership.yaml", ".l9/sdk-compatibility.yaml", ".l9/architecture.yaml"):
        assert "Quantum-L9/l9-birth-acceptance" in (dest / rel).read_text(encoding="utf-8")


def test_lock_is_resolved_for_the_newborn(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    # The birth invariant that motivated the whole command: a product author is
    # never asked to remember `uv lock`.
    _, dest = born
    lock = (dest / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "l9-birth-acceptance"' in lock
    assert 'name = "l9-example-pkg"' not in lock


def test_org_birth_profile_is_applied(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    _, dest = born
    marker = (dest / ".l9" / "org-birth-profile.yaml").read_text(encoding="utf-8")
    assert new_repo.parse_marker_profile(marker) == "non_constellation_python"
    assert "Quantum-L9/l9-birth-acceptance" in marker
    # The class declaration is the organization's contract and stays flat; the
    # provenance it used to sit beside now lives in the immutable `birth:` block.
    birth = prov.birth_block(marker)
    assert new_repo.SHA_RE.match(str(birth["template_sha"]))
    assert new_repo.SHA_RE.match(str(birth["org_policy_sha"]))
    assert birth["born_at"]


def test_birth_stamps_an_immutable_record(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    """The four provenance surfaces, stamped after everything that could move."""
    _, dest = born
    receipt = json.loads((dest / prov.BIRTH_RECEIPT_PATH).read_text(encoding="utf-8"))
    assert receipt["schema"] == prov.RECEIPT_SCHEMA
    assert receipt["repository"] == "Quantum-L9/l9-birth-acceptance"
    assert receipt["repo_class"] == "non_constellation_python"
    assert receipt["digest"] == prov.receipt_digest(receipt)

    version = (dest / prov.TEMPLATE_VERSION_PATH).read_text(encoding="utf-8").strip()
    assert version == receipt["template"]["version"]

    birth = prov.birth_block((dest / prov.MARKER_PATH).read_text(encoding="utf-8"))
    assert birth["template_sha"] == receipt["template"]["sha"]
    assert birth["template_version"] == version
    assert birth["org_policy_sha"] == receipt["org_policy"]["sha"]


def test_the_recorded_version_is_the_version_at_the_recorded_sha(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    """The invariant that would have caught a 2.0.0 / 2.1.0 disagreement.

    The record pins a template commit, so the version it records has to be the
    version that commit carries — read out of git here, not out of the template
    working tree the birth ran from.
    """
    _, dest = born
    receipt = json.loads((dest / prov.BIRTH_RECEIPT_PATH).read_text(encoding="utf-8"))
    at_sha = prov.template_version_at(REPO, receipt["template"]["sha"])
    assert receipt["template"]["version"] == at_sha


def test_the_conformance_record_is_born_equal_and_separate(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    """Born equal to the birth record, and a different file so it can move."""
    _, dest = born
    state = prov.parse_flat_yaml((dest / prov.TEMPLATE_STATE_PATH).read_text(encoding="utf-8"))
    receipt = json.loads((dest / prov.BIRTH_RECEIPT_PATH).read_text(encoding="utf-8"))
    assert state["schema"] == prov.TEMPLATE_STATE_SCHEMA
    assert state["template"]["current_sha"] == receipt["template"]["sha"]
    assert state["template"]["current_version"] == receipt["template"]["version"]
    assert state["policy"]["current_sha"] == receipt["org_policy"]["sha"]
    assert state["reconciled_by"] == "birth"
    assert prov.TEMPLATE_STATE_PATH not in prov.BIRTH_OWNED_PATHS


def test_the_newborn_can_prove_its_own_birth(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    """The repository carries the checker, so the proof outlives the birth run."""
    _, dest = born
    proc = subprocess.run(
        [sys.executable, "scripts/birth-runner/verify_birth_integrity.py", "--require-receipt"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BIRTH INTEGRITY: PASS" in proc.stdout


def test_a_payload_carrying_birth_provenance_stops_the_birth(tmp_path: Path) -> None:
    """A product owns its product. It never owns the record of its own birth.

    A payload copied out of an older repository carries that repository's
    `.l9-template-version`, and the overlay wins on collision — so without this
    the newborn is born claiming provenance that belongs to somebody else.
    """
    payload = tmp_path / "payload"
    payload.mkdir(parents=True)
    (payload / prov.TEMPLATE_VERSION_PATH).write_text("0.0.1\n", encoding="utf-8")

    proc = _birth(tmp_path, "--payload", str(payload))
    assert proc.returncode != 0
    assert "protected birth paths" in proc.stderr
    assert "repository created" not in proc.stdout


def test_no_forbidden_org_ci_distribution(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    _, dest = born
    profile = {
        "forbid": [
            ".github/workflows/l9-analysis.yml",
            ".github/workflows/l9-lint-test.yml",
            ".github/workflows/on-org-update.yml",
            ".github/workflows/governance.yml",
            ".github/governance/**",
        ]
    }
    assert new_repo.forbidden_present(dest, profile) == []


def test_no_agent_session_scaffolding_is_inherited(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    """A birth run from a governed workspace must not carry that workspace in.

    `.claude/` holds symlinks into the governance clone at an absolute machine
    path and a copy of the governance command/skill library; `.mcp.json` is 0600
    environment configuration. Both were landing in the newborn's root commit.
    """
    _, dest = born
    assert not (dest / ".claude").exists()
    assert not (dest / ".mcp.json").exists()
    ignored = (dest / ".gitignore").read_text(encoding="utf-8")
    assert "/.claude/" in ignored
    assert "/.mcp.json" in ignored


def test_no_template_git_history_is_inherited(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    _, dest = born
    log = subprocess.run(
        ["git", "-C", str(dest), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert log.returncode != 0 or not log.stdout.strip(), (
        "a newborn must not carry the template's commit history"
    )


def test_receipt_records_both_provenance_shas(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    proc, dest = born
    receipt_path = dest.parent / "l9-birth-acceptance-birth-receipt.json"
    assert receipt_path.is_file(), proc.stdout
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["result"] == "PASS"
    assert receipt["organization"]["birth_profile"] == "non_constellation_python"
    assert receipt["product"]["repository"] == "Quantum-L9/l9-birth-acceptance"
    assert receipt["template"]["template_version"]
    assert receipt["birth_receipt"]["digest"]
    assert receipt["manifest_sha256"]
    assert receipt["product"]["payload_mode"] == "none"


def test_org_contract_still_has_the_shape_birth_depends_on() -> None:
    """Cross-repo contract check, against the real policy file.

    Birth reads this from Quantum-L9/.github. If the class stops forbidding a
    path that `scripts/inventory_check.py` denies, every repository born from
    this template gets a pull request it cannot merge — which is exactly what
    this whole contract was built to stop.
    """
    assert ORG_SRC is not None
    doc = new_repo.parse_json_in_yaml(
        (ORG_SRC / "policies" / "repo-classes.yml").read_text(encoding="utf-8")
    )
    profile = new_repo.resolve_profile(doc, new_repo.BIRTH_PROFILE_CLASS)
    for denied in (
        ".github/workflows/l9-analysis.yml",
        ".github/workflows/l9-lint-test.yml",
        ".github/workflows/on-org-update.yml",
        ".github/workflows/governance.yml",
    ):
        assert new_repo.match_pattern(profile["forbid"], denied), (
            f"org class {profile['name']} must forbid {denied}; inventory_check.py denies it"
        )
    assert new_repo.match_pattern(profile["forbid"], ".github/governance/waivers.yaml")
    assert profile["seed_categories"], "the class must materialize something"


def test_materialized_org_files_are_in_the_initial_commit(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    """MATERIALIZE lands before the commit, not in a later seeder PR."""
    proc, dest = born
    receipt = json.loads(
        (dest.parent / "l9-birth-acceptance-birth-receipt.json").read_text(encoding="utf-8")
    )
    assert "materialized" in receipt
    for rel in receipt["materialized"]:
        assert (dest / rel).is_file(), f"{rel} was reported materialized but is not on disk"
    assert "org files materialized" in proc.stdout


def test_license_governs_the_newborn_not_the_org_github_repo(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    """The one defect a factory would reproduce perfectly, forever."""
    _, dest = born
    text = (dest / "LICENSE").read_text(encoding="utf-8")
    assert new_repo.POISONED_LICENSE_NOTICE not in text
    assert "QUANTUM AI PARTNERS" in text


def test_no_origin_is_pre_created(
    born: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    """`gh repo create --source --remote origin --push` owns remote creation.

    Pre-creating `origin` in stage 2 gave two owners for one remote.
    """
    _, dest = born
    remotes = subprocess.run(
        ["git", "-C", str(dest), "remote"], capture_output=True, text=True, check=False
    )
    assert remotes.stdout.strip() == ""


def test_a_payload_that_smuggles_org_ci_stops_the_birth(tmp_path: Path) -> None:
    # FORBID is an assertion about the assembled repository, not only a filter
    # on a seed payload: a product payload can introduce one just as easily.
    payload = tmp_path / "payload" / ".github" / "workflows"
    payload.mkdir(parents=True)
    (payload / "governance.yml").write_text("name: governance\n", encoding="utf-8")

    proc = _birth(tmp_path, "--payload", str(tmp_path / "payload"))
    assert proc.returncode == 1
    assert "BIRTH: FAIL" in proc.stdout
    assert "violates repo class non_constellation_python" in proc.stderr
    # Stage 4 stops before stage 6: nothing was created.
    assert "repository created" not in proc.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Repository-shaped PAYLOAD: authoritative over the product tree
# ─────────────────────────────────────────────────────────────────────────────

# A standalone product repository, in the shape the birth engine recognizes:
# pyproject.toml, .l9/architecture.yaml, src/, tests/, scripts/inventory_check.py.
# It owns backend-neutral contracts and NOTHING else — no service, no Docker, no
# local observability stack — and its own inventory check says so. That last part
# matters: if the template leaked its example product into this repository, the
# newborn's OWN gate would fail in stage 5, which is the regression this fixture
# exists to hold.
PAYLOAD_PKG = "l9_domain_contracts"
PAYLOAD_REPO = "l9-birth-repo-payload"

PAYLOAD_FILES: dict[str, str] = {
    "pyproject.toml": '[build-system]\nrequires = ["setuptools>=75.0.0", "wheel"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "PKG_KEBAB"\nversion = "0.1.0"\ndescription = "Backend-neutral domain contracts"\nreadme = "README.md"\nrequires-python = ">=3.12"\nlicense = { text = "Proprietary" }\ndependencies = []\n\n[project.optional-dependencies]\ndev = [\n  "mypy==2.3.1",\n  "pytest==9.1.1",\n  "ruff==0.16.4",\n  "pyyaml>=6.0.2",\n]\n\n[tool.setuptools]\npackage-dir = {"" = "src"}\n\n[tool.setuptools.packages.find]\nwhere = ["src"]\n\n[tool.ruff]\nline-length = 100\ntarget-version = "py312"\nexclude = ["tools/l9_repo"]\n\n[tool.ruff.lint]\nselect = ["E", "F", "B", "I", "UP"]\nignore = ["E501"]\n\n[tool.mypy]\npython_version = "3.12"\nstrict = true\nmypy_path = "src"\npackages = ["PKG"]\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
    ".l9/architecture.yaml": "schema: l9.architecture-spec/v1\nmetadata:\n  repository: Quantum-L9/REPO_NAME\n  status: authoritative\nboundaries:\n  owns:\n    - backend-neutral domain contracts under src/\n  does_not_own:\n    - HTTP services, exporters, collectors, dashboards, or any runtime backend\n",
    "src/PKG/__init__.py": '"""Backend-neutral domain contracts."""\n\nfrom .canonical import CANONICAL_VERSION, canonical_name\n\n__all__ = ["CANONICAL_VERSION", "canonical_name"]\n',
    "src/PKG/canonical.py": '"""The one contract this product owns."""\n\nfrom __future__ import annotations\n\nCANONICAL_VERSION = "v1"\n\n\ndef canonical_name(raw: str) -> str:\n    """Normalize a contract name. No transport, no backend, no I/O."""\n    return raw.strip().lower().replace(" ", "_")\n',
    "src/PKG/py.typed": "",
    "schemas/v1/contract.schema.json": '{\n  "$schema": "https://json-schema.org/draft/2020-12/schema",\n  "title": "contract",\n  "type": "object",\n  "required": ["name"],\n  "properties": {"name": {"type": "string"}}\n}\n',
    "tests/test_canonical.py": 'from __future__ import annotations\n\nfrom PKG import CANONICAL_VERSION, canonical_name\n\n\ndef test_version_is_v1() -> None:\n    assert CANONICAL_VERSION == "v1"\n\n\ndef test_names_are_normalized() -> None:\n    assert canonical_name("  Request Latency ") == "request_latency"\n',
    "tests/test_schemas_are_present.py": 'from __future__ import annotations\n\nimport json\nfrom pathlib import Path\n\nSCHEMAS = Path(__file__).resolve().parents[1] / "schemas" / "v1"\n\n\ndef test_every_schema_parses() -> None:\n    files = sorted(SCHEMAS.glob("*.json"))\n    assert files\n    for path in files:\n        json.loads(path.read_text(encoding="utf-8"))\n',
    "scripts/inventory_check.py": '#!/usr/bin/env python3\n"""Fail closed on surfaces this product does not own.\n\nThis product is backend-neutral domain contracts. A Docker runtime, a compose\nfile, or a local observability stack is not a missing feature here — it is a\nboundary violation, whatever put it in the tree.\n"""\n\nfrom __future__ import annotations\n\nimport os\nimport sys\nfrom pathlib import Path\n\nROOT = Path(os.environ.get("L9_INVENTORY_ROOT") or Path(__file__).resolve().parents[1])\n\nDENY = (\n    "observability",\n    "Dockerfile",\n    "docker-compose.yml",\n    "engine",\n    "chassis",\n    "domains",\n    "deploy",\n)\n\nREQUIRED = (\n    "pyproject.toml",\n    "uv.lock",\n    "LICENSE",\n    ".l9/architecture.yaml",\n    ".l9/org-birth-profile.yaml",\n    "src/PKG/__init__.py",\n    "src/PKG/canonical.py",\n    "schemas/v1/contract.schema.json",\n)\n\nDENY_PACKAGE_MODULES = ("app.py", "health.py", "protocols.py", "retry.py", "settings.py")\n\n\ndef main() -> int:\n    errors: list[str] = []\n    for name in DENY:\n        if (ROOT / name).exists():\n            errors.append(f"surface this product does not own is present: {name}")\n    for rel in REQUIRED:\n        if not (ROOT / rel).is_file():\n            errors.append(f"missing required file: {rel}")\n    package = ROOT / "src" / "PKG"\n    for name in DENY_PACKAGE_MODULES:\n        if (package / name).exists():\n            errors.append(\n                f"package module this product does not own: src/PKG/{name}"\n            )\n    if errors:\n        for err in errors:\n            sys.stderr.write(f"inventory-check FAIL: {err}\\n")\n        return 1\n    sys.stdout.write("inventory-check OK\\n")\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n',
}


def _write_repository_payload(root: Path) -> Path:
    """Materialize the payload, substituting the fixture's package identity."""
    for rel, body in PAYLOAD_FILES.items():
        target = root / rel.replace("PKG", PAYLOAD_PKG)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            body.replace("PKG_KEBAB", PAYLOAD_PKG.replace("_", "-"))
            .replace("REPO_NAME", PAYLOAD_REPO)
            .replace("PKG", PAYLOAD_PKG),
            encoding="utf-8",
        )
    return root


@pytest.fixture(scope="module")
def born_from_repository_payload(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    tmp_path = tmp_path_factory.mktemp("birth-repo-payload")
    payload = _write_repository_payload(tmp_path / "payload")
    proc = _birth(
        tmp_path,
        "--payload",
        str(payload),
        repo=PAYLOAD_REPO,
        pkg=PAYLOAD_PKG,
    )
    return proc, tmp_path / "work" / PAYLOAD_REPO


def test_repository_payload_births(
    born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    proc, _ = born_from_repository_payload
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BIRTH: PASS" in proc.stdout
    assert "payload ownership" in proc.stdout


def test_the_payload_owns_its_package(
    born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    """Replace, not union-merge.

    The template's example package is renamed to the product's name in stage 2.
    Without ownership reconciliation its optional helpers would then appear to be
    the product's own modules, because the payload has no same-named file with
    which to overwrite them.
    """
    _, dest = born_from_repository_payload
    package = dest / "src" / PAYLOAD_PKG
    assert sorted(p.name for p in package.iterdir()) == [
        "__init__.py",
        "canonical.py",
        "py.typed",
    ]
    for leaked in ("app.py", "health.py", "protocols.py", "retry.py", "settings.py"):
        assert not (package / leaked).exists(), f"template module {leaked} leaked into the product"


def test_unowned_template_product_surfaces_do_not_survive(
    born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    _, dest = born_from_repository_payload
    for leaked in (
        "Dockerfile",
        "docker-compose.yml",
        ".dockerignore",
        ".env.example",
        "observability",
        "docs/examples",
        "tests/integration/test_app_http.py",
        "tests/conftest.py",
    ):
        assert not (dest / leaked).exists(), f"template surface {leaked} leaked into the product"


def test_the_birth_chassis_survives_an_authoritative_payload(
    born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    """A product owns its product, not the factory that made it."""
    _, dest = born_from_repository_payload
    for kept in (
        "Makefile",
        "Repo.mk",
        "LICENSE",
        "MANIFEST.sha256",
        "uv.lock",
        "tools/l9_repo/__main__.py",
        "scripts/birth-runner/new_repo.py",
        "scripts/birth-runner/payload-ownership.yaml",
        "scripts/render_cursor_rules.py",
        ".l9/org-birth-profile.yaml",
        ".cursor/rules/templates/l9-python-repo.mdc.template",
    ):
        assert (dest / kept).exists(), f"authoritative payload removed chassis surface {kept}"
    assert (dest / "schemas" / "v1" / "contract.schema.json").is_file()
    marker = (dest / ".l9" / "org-birth-profile.yaml").read_text(encoding="utf-8")
    assert new_repo.parse_marker_profile(marker) == "non_constellation_python"


def test_the_newborns_own_gate_ran_green(
    born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    """The payload's inventory rules are what stage 5 enforced, not the template's.

    The payload's `scripts/inventory_check.py` denies exactly the surfaces the
    template ships. Stage 5 running it green is the proof that no template
    product surface survived — asserted by the product's own contract rather
    than by this test's opinion.
    """
    proc, dest = born_from_repository_payload
    assert "inventory" in proc.stdout
    assert "FAIL" not in proc.stdout
    checked = (dest / "scripts" / "inventory_check.py").read_text(encoding="utf-8")
    assert "surface this product does not own" in checked, "the payload's rules were overwritten"


def test_receipt_records_the_ownership_decision(
    born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    _, dest = born_from_repository_payload
    receipt = json.loads(
        (dest.parent / f"{PAYLOAD_REPO}-birth-receipt.json").read_text(encoding="utf-8")
    )
    stages = {s["key"]: s for s in receipt["stages"]}
    assert stages["assemble.ownership"]["status"] == "PASS"
    assert "authoritative" in stages["assemble.ownership"]["detail"]


def test_pkg_must_name_the_package_the_payload_ships(tmp_path: Path) -> None:
    """A mismatch is caught in stage 2, not as an import error in stage 5."""
    payload = _write_repository_payload(tmp_path / "payload")
    proc = _birth(
        tmp_path,
        "--payload",
        str(payload),
        repo=PAYLOAD_REPO,
        pkg="l9_wrong_name",
    )
    assert proc.returncode == 1
    assert "is not the package this repository payload ships" in proc.stderr
    assert "repository created" not in proc.stdout


def test_a_partial_overlay_is_still_purely_additive(tmp_path: Path) -> None:
    """The pre-existing contract, unchanged.

    A fragment adds and overrides. It never speaks for what it omits — this
    payload has no Dockerfile and the newborn keeps the template's.
    """
    payload = tmp_path / "payload" / "src" / "l9_birth_acceptance"
    payload.mkdir(parents=True)
    (payload / "extra.py").write_text("VALUE = 1\n", encoding="utf-8")

    proc = _birth(tmp_path, "--payload", str(tmp_path / "payload"))
    assert proc.returncode == 0, proc.stdout + proc.stderr

    dest = tmp_path / "work" / "l9-birth-acceptance"
    receipt = json.loads(
        (dest.parent / "l9-birth-acceptance-birth-receipt.json").read_text(encoding="utf-8")
    )
    ownership = {s["key"]: s for s in receipt["stages"]}["assemble.ownership"]
    assert "additive overlay" in ownership["detail"]

    assert (dest / "src" / "l9_birth_acceptance" / "extra.py").is_file()
    for kept in ("Dockerfile", "docker-compose.yml", "observability", ".env.example"):
        assert (dest / kept).exists(), f"a partial overlay removed {kept}"
    assert (dest / "src" / "l9_birth_acceptance" / "app.py").is_file()


# ─────────────────────────────────────────────────────────────────────────────
# Semantic identity: what the newborn's generated metadata is allowed to claim
# ─────────────────────────────────────────────────────────────────────────────

# The template's own product vocabulary. None of it may appear as an ACTIVE
# claim in a repository that never asked for the example product. Provenance —
# `template_repo`, the birth marker's `template_sha` — is a different thing and
# is deliberately preserved.
TEMPLATE_PRODUCT_CLAIMS = (
    "l9-repo-template",
    "l9-python-museum",
    "l9_example_pkg",
    "obs-optional",
)


def _generated_metadata(dest: Path) -> dict[str, str]:
    """Every active generated agent-facing surface, by repository-relative path."""
    found = {"plugin-config.yaml": (dest / "plugin-config.yaml").read_text(encoding="utf-8")}
    for path in sorted((dest / ".cursor" / "rules").glob("*.mdc")):
        found[path.relative_to(dest).as_posix()] = path.read_text(encoding="utf-8")
    return found


class TestGeneratedMetadataDescribesTheNewborn:
    """A plain birth: the example product IS this repository's product."""

    def test_repo_identity_is_the_newborns_own(
        self, born: tuple[subprocess.CompletedProcess[str], Path]
    ) -> None:
        _, dest = born
        config = (dest / "plugin-config.yaml").read_text(encoding="utf-8")
        assert 'repo_name: "l9-birth-acceptance"' in config
        assert "l9-repo-template" not in config

    def test_a_kept_claim_is_one_the_tree_proves(
        self, born: tuple[subprocess.CompletedProcess[str], Path]
    ) -> None:
        """Reconciliation removes false claims; it never removes true ones."""
        _, dest = born
        config = (dest / "plugin-config.yaml").read_text(encoding="utf-8")
        assert 'app_entrypoint: "l9_birth_acceptance.app:app"' in config
        assert (dest / "src" / "l9_birth_acceptance" / "app.py").is_file()
        assert '- "obs-optional"' in config
        assert (dest / "observability").is_dir()
        assert (dest / ".cursor" / "rules" / "fastapi.mdc").is_file()

    def test_the_birth_receipt_records_the_reconciliation(
        self, born: tuple[subprocess.CompletedProcess[str], Path]
    ) -> None:
        proc, dest = born
        receipt = json.loads(
            (dest.parent / "l9-birth-acceptance-birth-receipt.json").read_text(encoding="utf-8")
        )
        stages = {s["key"]: s for s in receipt["stages"]}
        assert stages["finalize.config"]["status"] == "PASS"
        assert "repo_name -> l9-birth-acceptance" in stages["finalize.config"]["detail"]
        assert "config reconciled" in proc.stdout

    def test_the_newborn_passes_its_own_semantic_gate(
        self, born: tuple[subprocess.CompletedProcess[str], Path]
    ) -> None:
        _, dest = born
        for check in ("scripts/reconcile_plugin_config.py", "scripts/render_cursor_rules.py"):
            proc = subprocess.run(
                [str(dest / ".venv" / "bin" / "python"), check, "--check"],
                cwd=dest,
                capture_output=True,
                text=True,
                check=False,
            )
            assert proc.returncode == 0, f"{check}: {proc.stderr or proc.stdout}"


class TestAnAuthoritativePayloadInheritsNoProductClaims:
    """The defect the first real offspring found.

    Birth returned PASS and the product tree was correct, while the agent-facing
    chassis metadata still described the template's FastAPI demo. Every
    assertion below failed before the reconciler existed.
    """

    def test_no_template_product_claim_survives_anywhere(
        self, born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path]
    ) -> None:
        _, dest = born_from_repository_payload
        offences = [
            f"{rel}: {claim}"
            for rel, text in _generated_metadata(dest).items()
            for claim in TEMPLATE_PRODUCT_CLAIMS
            if claim in text
        ]
        assert offences == [], (
            f"the template's example product leaked as an active claim: {offences}"
        )

    def test_identity_is_the_products_own(
        self, born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path]
    ) -> None:
        _, dest = born_from_repository_payload
        config = (dest / "plugin-config.yaml").read_text(encoding="utf-8")
        assert f'repo_name: "{PAYLOAD_REPO}"' in config
        assert f'package_name: "{PAYLOAD_PKG}"' in config
        for text in _generated_metadata(dest).values():
            assert PAYLOAD_REPO in text or "Repo:" not in text

    def test_no_entrypoint_is_claimed_for_a_module_that_does_not_exist(
        self, born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path]
    ) -> None:
        _, dest = born_from_repository_payload
        assert not (dest / "src" / PAYLOAD_PKG / "app.py").exists()
        config = (dest / "plugin-config.yaml").read_text(encoding="utf-8")
        assert "app_entrypoint:" not in config
        for rel, text in _generated_metadata(dest).items():
            assert f"{PAYLOAD_PKG}.app:app" not in text, f"{rel} claims a module nothing ships"

    def test_the_fastapi_rule_is_not_rendered_for_a_library(
        self, born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path]
    ) -> None:
        """A rule is an instruction. This repository hosts nothing."""
        _, dest = born_from_repository_payload
        assert not (dest / ".cursor" / "rules" / "fastapi.mdc").exists()
        manifest = json.loads(
            (dest / ".cursor" / "rules" / ".render-manifest.json").read_text(encoding="utf-8")
        )
        skipped = {Path(entry["template"]).name for entry in manifest["skipped"]}
        assert "fastapi.mdc.template" in skipped
        assert manifest["rules"], "reconciliation removed every rule, not only the false one"

    def test_an_optional_stack_that_was_never_born_is_not_a_capability(
        self, born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path]
    ) -> None:
        _, dest = born_from_repository_payload
        assert not (dest / "observability").exists()
        config = (dest / "plugin-config.yaml").read_text(encoding="utf-8")
        assert "obs-optional" not in config
        assert '- "verify"' in config, "a chassis capability was collateral damage"

    def test_provenance_is_not_mistaken_for_a_claim(
        self, born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path]
    ) -> None:
        """Where the repository came from stays recorded; what it IS is corrected."""
        _, dest = born_from_repository_payload
        marker = (dest / ".l9" / "org-birth-profile.yaml").read_text(encoding="utf-8")
        assert "template_sha:" in marker
        assert f"Quantum-L9/{PAYLOAD_REPO}" in marker

    def test_the_newborn_passes_its_own_semantic_gate(
        self, born_from_repository_payload: tuple[subprocess.CompletedProcess[str], Path]
    ) -> None:
        """Not just correct at birth — provably correct by the newborn's own gate."""
        _, dest = born_from_repository_payload
        for check in ("scripts/reconcile_plugin_config.py", "scripts/render_cursor_rules.py"):
            proc = subprocess.run(
                [str(dest / ".venv" / "bin" / "python"), check, "--check"],
                cwd=dest,
                capture_output=True,
                text=True,
                check=False,
            )
            assert proc.returncode == 0, f"{check}: {proc.stderr or proc.stdout}"
