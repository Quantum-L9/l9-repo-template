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
RUNNER = REPO / "scripts" / "birth-runner" / "new_repo.py"
_SPEC = importlib.util.spec_from_file_location("l9_birth_new_repo_it", RUNNER)
assert _SPEC and _SPEC.loader
new_repo = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = new_repo
_SPEC.loader.exec_module(new_repo)

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

ORG_POLICY = json.dumps(
    {
        "schema": "l9.org-birth-profile/v1",
        "default_class": "default",
        "marker_path": ".l9/org-birth-profile.yaml",
        "classes": {
            "default": {"seed_categories": ["codeowners"]},
            "non_constellation_python": {
                "description": "test fixture mirroring the org contract",
                "seed_categories": ["codeowners", "dependabot", "labels"],
                "inherit": ["CODE_OF_CONDUCT.md"],
                # Mirrors scripts/inventory_check.py DENY_CI_DISTRIBUTION.
                "forbid": [
                    ".github/workflows/l9-analysis.yml",
                    ".github/workflows/l9-lint-test.yml",
                    ".github/workflows/on-org-update.yml",
                    ".github/workflows/governance.yml",
                    ".github/governance/**",
                ],
                "remote_apply": {"labels": True, "repo_settings": True},
                "mandatory_files_waive": [".github/workflows/governance.yml"],
            },
        },
    },
    indent=2,
)


def _org_profile_src(tmp_path: Path) -> Path:
    """A stand-in Quantum-L9/.github holding only the class policy.

    Reading the real organization repository over the network would make this
    test depend on gh auth and on whatever is on that repo's default branch
    today. The contract under test is the *shape*, which is pinned here.
    """
    root = tmp_path / "org-github"
    (root / "policies").mkdir(parents=True)
    (root / "policies" / "repo-classes.yml").write_text(ORG_POLICY, encoding="utf-8")
    return root


def _birth(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["L9_SKIP_BIRTH_ACCEPTANCE"] = "1"
    return subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--repo",
            "l9-birth-acceptance",
            "--pkg",
            "l9_birth_acceptance",
            "--desc",
            "Local birth acceptance fixture",
            "--work-dir",
            str(tmp_path / "work"),
            "--org-profile-src",
            str(_org_profile_src(tmp_path)),
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
    assert "template_sha:" in marker and "org_profile_sha:" in marker


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
