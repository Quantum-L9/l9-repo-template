from __future__ import annotations

from pathlib import Path
from typing import Any


class AuthorityError(RuntimeError):
    """Raised when repository-runtime authority or derivation drifts."""


def _read_identity_document(
    root: Path, relative: str, artifact_id: str, version: str
) -> list[str]:
    path = root / relative
    if path.is_symlink() or not path.is_file():
        return [f"missing derived document: {relative}"]
    content = path.read_text(encoding="utf-8", errors="replace")
    errors: list[str] = []
    for token in (artifact_id, version):
        if token not in content:
            errors.append(f"{relative} does not declare authoritative token {token!r}")
    return errors


def validate_authority(root: Path, config: dict[str, Any]) -> None:
    metadata = config["metadata"]
    authority = config["authority"]
    version = metadata["artifact_version"]
    artifact_id = metadata["artifact_id"]
    errors: list[str] = []

    for relative in authority["target_authorities"]:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"missing target authority: {relative}")

    for relative in authority["generated_artifacts"]:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"missing generated artifact: {relative}")

    for relative in authority["derived_documents"]:
        errors.extend(_read_identity_document(root, relative, artifact_id, version))

    dependencies = authority["dependency_manifests"]
    for relative in dependencies["component_bundled"]:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"missing component dependency manifest: {relative}")
    for relative in dependencies["target_required"]:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"missing target dependency manifest: {relative}")

    component_authority = authority["component_authority"]
    component_schema = authority["component_schema"]
    if component_authority != ".l9/repo-workflow.json":
        errors.append("component authority path drift")
    if component_schema != ".l9/repo-workflow.schema.json":
        errors.append("component schema path drift")

    if errors:
        raise AuthorityError("; ".join(errors))
