"""Node birth pipeline, end to end, on the real State payload (campaign L9-NODE-PIPELINE-01).

One local NO_REMOTE birth of the compiler-backed State payload, then the
post-PUBLISH activation stage against the assembled root, proving in the
assembled tree:

  item 2  Repository Execution V2 contract, Core facade, Repo.mk, all four
          make-v1 phases passed inside PREPARE;
  item 3  every Core-owned CI-tool file stamped from Core, `.l9/core-stamp.json`
          valid, Core `validate` passes;
  item 4  the compiler-emitted repository contracts are present and AGENTS.md
          names them (no hand-made file);
  item 8  the topology packet compiled from the post-injection SHA is committed
          under `.l9/topology-packet`;

and that no factory-only surface reached the product.

Skip condition — real, narrow, documented, externally unavoidable: every input
is a separate repository this factory does not vendor (the State snapshot, the
pinned compiler, Core, the organization `.github`, the pinned meta-injector and
topology compiler). Point the variables below at clean checkouts; set
`L9_REQUIRE_NODE_PIPELINE=1` to turn any absent input into a failure, which is
what a provisioned runner must do. The pure parts are unit-tested without them
(`tests/unit/test_birth_activation.py`, `tests/unit/test_new_repo_orchestrator.py`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "scripts" / "birth-runner"
INPUTS = {
    "payload": "L9_STATE_PAYLOAD_SRC",
    "engine": "L9_SEMANTIC_COMPILER_SRC",
    "core": "L9_CORE_SRC",
    "org": "L9_ORG_SRC",
    "injector": "L9_META_INJECTOR_SRC",
    "topology": "L9_TOPOLOGY_SRC",
    "topology_cli": "L9_TOPOLOGY_CLI",
}
FACTORY_ONLY = (
    "scripts/birth-runner/new_repo.py",
    "scripts/render_cursor_rules.py",
    "CLAUDE.md",
    "TEMPLATE_INVENTORY.md",
    "bootstrap.sh",
    "plugin-config.yaml",
    "llms.txt",
)


def _inputs() -> dict[str, Path]:
    found = {key: os.environ.get(var, "") for key, var in INPUTS.items()}
    missing = [INPUTS[k] for k, v in found.items() if not v or not Path(v).exists()]
    if missing:
        reason = "node pipeline inputs not provisioned: " + ", ".join(missing)
        if os.environ.get("L9_REQUIRE_NODE_PIPELINE") == "1":
            pytest.fail(reason)
        pytest.skip(reason)
    return {k: Path(v).resolve() for k, v in found.items()}


def _run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)  # type: ignore[call-overload]


@pytest.fixture(scope="module")
def born(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    src = _inputs()
    work = tmp_path_factory.mktemp("node-pipeline")
    bundle = work / "bundle"
    packaged = _run(
        [
            sys.executable,
            str(RUNNER / "package_birth_handoff.py"),
            "--source",
            str(src["payload"]),
            "--semantic-compiler-src",
            str(src["engine"]),
            "--manifest-ref",
            "l9.product-manifest/l9.state@1",
            "--out-dir",
            str(bundle),
            "--source-repository",
            "Quantum-L9/l9-wip",
        ]
    )
    assert packaged.returncode == 0, packaged.stdout + packaged.stderr
    births = work / "births"
    birth = _run(
        [
            sys.executable,
            str(RUNNER / "new_repo.py"),
            "--repo",
            "l9-state",
            "--pkg",
            "l9_state",
            "--desc",
            "L9 State node",
            "--org",
            "Quantum-L9",
            "--repo-class",
            "org_seeded_self_governed",
            "--work-dir",
            str(births),
            "--no-remote",
            "--org-profile-src",
            str(src["org"]),
            "--payload",
            str(src["payload"]),
            "--payload-contract",
            str(bundle / "birth-payload.json"),
            "--product-birth-binding",
            str(bundle / "product-birth-binding.json"),
            "--product-manifest",
            str(bundle / "product-manifest.json"),
            "--semantic-compiler-src",
            str(src["engine"]),
            "--core-src",
            str(src["core"]),
        ],
        cwd=REPO,
    )
    assert birth.returncode == 0, birth.stdout[-4000:] + birth.stderr[-4000:]
    return {"root": births / "l9-state", "work": work, "src": src, "births": births}


def test_item2_v2_contract_and_all_four_phases(born: dict[str, object]) -> None:
    root = Path(str(born["root"]))
    workflow = json.loads((root / ".l9/repo-workflow.json").read_text(encoding="utf-8"))
    assert workflow == {
        "schema": "l9.repo-execution/v2",
        "facade": "make-v1",
        "required_phases": ["setup", "validate", "check", "test"],
    }
    assert (root / "Repo.mk").is_file()
    receipt = json.loads(
        (Path(str(born["births"])) / "l9-state-birth-receipt.json").read_text(encoding="utf-8")
    )
    stages = {s["key"]: s["status"] for s in receipt["stages"]}
    for phase in ("setup", "validate", "check", "test"):
        assert stages[f"validate.phase.{phase}"] == "PASS", phase


def test_item3_core_stamp_is_valid(born: dict[str, object]) -> None:
    root = Path(str(born["root"]))
    src = born["src"]
    assert isinstance(src, dict)
    stamp = json.loads((root / ".l9/core-stamp.json").read_text(encoding="utf-8"))
    assert stamp["schema"] == "l9.core-stamp/v1"
    assert stamp["core"]["repository"] == "Quantum-L9/l9-ci-core"
    for rel in (
        "biome.json",
        "ruff.toml",
        "mypy.ini",
        "pytest.ini",
        "requirements-ci.txt",
        "Makefile",
    ):
        assert rel in stamp["files"], rel
    validated = _run(
        [sys.executable, "-m", "tools.l9_repo", "--workspace", str(root), "validate"],
        cwd=src["core"],
    )
    assert validated.returncode == 0, validated.stdout + validated.stderr


def test_item4_compiler_emitted_contracts(born: dict[str, object]) -> None:
    root = Path(str(born["root"]))
    architecture = yaml.safe_load((root / ".l9/architecture.yaml").read_text(encoding="utf-8"))
    assert architecture["schema"] == "l9.architecture-spec/v1"
    assert (root / ".l9/repo-contracts.json").is_file()
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- l9:repo-contracts:begin -->" in agents
    assert ".l9/architecture.yaml" in agents


def test_no_factory_surface_reached_the_product(born: dict[str, object]) -> None:
    root = Path(str(born["root"]))
    leaked = [rel for rel in FACTORY_ONLY if (root / rel).exists()]
    assert leaked == []
    assert not (root / "scripts" / "birth-runner").exists()
    assert not (root / ".cursor").exists()


def test_item8_activation_commits_a_topology_packet(born: dict[str, object]) -> None:
    root = Path(str(born["root"]))
    src = born["src"]
    assert isinstance(src, dict)
    newborn = Path(str(born["work"])) / "published"
    cloned = _run(["git", "clone", "-q", str(root), str(newborn)])
    assert cloned.returncode == 0, cloned.stderr
    activated = _run(
        [
            sys.executable,
            str(RUNNER / "birth_activation.py"),
            "--newborn",
            str(newborn),
            "--repository",
            "Quantum-L9/l9-state",
            "--org-root",
            str(src["org"]),
            "--injector",
            str(src["injector"]),
            "--topology-cli",
            str(src["topology_cli"]),
            "--topology-root",
            str(src["topology"]),
            "--work",
            str(Path(str(born["work"])) / "activation"),
        ]
    )
    assert activated.returncode == 0, activated.stdout[-3000:] + activated.stderr[-3000:]
    receipt = json.loads(activated.stdout)
    assert [s["step"] for s in receipt["steps"]] == [
        "emit",
        "apply",
        "check",
        "commit",
        "model",
        "topology",
        "commit",
    ]
    assert (newborn / ".l9/meta-authority.yaml").is_file()
    assert (newborn / ".l9/metadata-index.jsonl").is_file()
    assert (newborn / ".l9/topology-packet/packet.json").is_file()
    head = _run(["git", "-C", str(newborn), "log", "--format=%H", "-3"]).stdout.split()
    assert head[0] == receipt["packet_sha"] and head[1] == receipt["injected_sha"]
