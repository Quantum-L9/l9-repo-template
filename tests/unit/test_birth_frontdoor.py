from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "scripts" / "birth-runner" / "birth_frontdoor.py"
_SPEC = importlib.util.spec_from_file_location("l9_birth_frontdoor", MODULE)
assert _SPEC is not None
assert _SPEC.loader is not None
front = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = front
_SPEC.loader.exec_module(front)


def _intent(**overrides: str):
    values = {
        "repo": "IdeaOS",
        "pkg": "ideaos",
        "desc": "Idea lifecycle runtime",
        "visibility": "private",
        "repo_class": "non_constellation_python",
        "ci_unverified_reason": "",
        "governance_ref": "main",
        "payload_repo": "Quantum-L9/IdeaOS-seed",
        "payload_ref": "abc123",
        "payload_subpath": "",
        "payload_contract_path": "birth.payload.json",
        "factory_ref": "main",
    }
    values.update(overrides)
    return front.BirthIntent(**values)


def test_dispatch_targets_canonical_factory_workflow() -> None:
    command = front.build_dispatch_command(_intent())
    assert command[:7] == [
        "gh",
        "workflow",
        "run",
        "repo-birth-dispatch.yml",
        "--repo",
        "Quantum-L9/l9-repo-template",
        "--ref",
    ]
    assert command[7] == "main"
    joined = " ".join(command)
    assert "repo_name=IdeaOS" in joined
    assert "package_name=ideaos" in joined
    assert "payload_repo=Quantum-L9/IdeaOS-seed" in joined
    assert "payload_ref=abc123" in joined


def test_optional_blank_fields_are_not_dispatched() -> None:
    intent = _intent(
        repo_class="",
        governance_ref="",
        payload_repo="",
        payload_ref="",
        payload_contract_path="",
    )
    fields = dict(front.dispatch_fields(intent))
    assert fields == {
        "repo_name": "IdeaOS",
        "package_name": "ideaos",
        "description": "Idea lifecycle runtime",
        "visibility": "private",
    }


def test_payload_ref_is_required_with_payload_repo() -> None:
    with pytest.raises(front.BirthFrontDoorError, match="PAYLOAD_REF"):
        front.validate_intent(_intent(payload_ref=""))


def test_payload_repo_is_required_with_payload_ref() -> None:
    with pytest.raises(front.BirthFrontDoorError, match="PAYLOAD_REPO"):
        front.validate_intent(_intent(payload_repo=""))


def test_payload_must_stay_inside_quantum_l9() -> None:
    with pytest.raises(front.BirthFrontDoorError, match="inside Quantum-L9"):
        front.validate_intent(_intent(payload_repo="someone/foreign"))


def test_description_must_be_one_line() -> None:
    with pytest.raises(front.BirthFrontDoorError, match="one line"):
        front.validate_intent(_intent(desc="line one\nline two"))


def test_front_door_never_passes_publication_credentials() -> None:
    command = front.build_dispatch_command(_intent())
    text = " ".join(command)
    assert "GH_TOKEN" not in text
    assert "GITHUB_TOKEN" not in text
    assert "L9_BIRTH_PRIVILEGED_TOKEN" not in text


ADAPTER_PATHS = {
    "product_birth_binding_path": "birth/product-birth-binding.json",
    "product_manifest_path": "birth/product-manifest.json",
    "repo_birth_contract_path": "birth/repo-birth-contract.json",
}


def test_an_adapter_bundle_is_dispatched_as_three_relative_paths() -> None:
    fields = dict(front.dispatch_fields(_intent(**ADAPTER_PATHS)))
    for key, value in ADAPTER_PATHS.items():
        assert fields[key] == value


@pytest.mark.parametrize("dropped", sorted(ADAPTER_PATHS))
def test_a_partial_adapter_bundle_is_refused(dropped: str) -> None:
    with pytest.raises(front.BirthFrontDoorError, match="all three artifacts"):
        front.validate_intent(_intent(**{**ADAPTER_PATHS, dropped: ""}))


def test_an_adapter_bundle_requires_the_compiled_payload() -> None:
    with pytest.raises(front.BirthFrontDoorError, match="PAYLOAD_CONTRACT_PATH"):
        front.validate_intent(_intent(**ADAPTER_PATHS, payload_contract_path=""))


def test_an_adapter_bundle_requires_the_payload_checkout() -> None:
    with pytest.raises(front.BirthFrontDoorError, match="PAYLOAD_REPO"):
        front.validate_intent(_intent(**ADAPTER_PATHS, payload_repo="", payload_ref=""))


@pytest.mark.parametrize("key", sorted(ADAPTER_PATHS))
def test_adapter_paths_must_be_relative(key: str) -> None:
    with pytest.raises(front.BirthFrontDoorError, match="must be relative"):
        front.validate_intent(_intent(**{**ADAPTER_PATHS, key: "/etc/passwd"}))


@pytest.mark.parametrize("key", sorted(ADAPTER_PATHS))
def test_adapter_paths_must_not_traverse(key: str) -> None:
    with pytest.raises(front.BirthFrontDoorError, match=r"'\.\.'"):
        front.validate_intent(_intent(**{**ADAPTER_PATHS, key: "birth/../../secret.json"}))


def test_the_front_door_does_not_interpret_adapter_artifacts() -> None:
    """Transport only: no ProductKind, archetype, or topology reasoning here."""
    import ast

    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in (
            node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")]
        )
    }
    assert imported <= {
        "__future__",
        "argparse",
        "dataclasses",
        "re",
        "shutil",
        "subprocess",
        "sys",
    }
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not called & {"open", "read_text", "read_bytes", "load", "loads"}
