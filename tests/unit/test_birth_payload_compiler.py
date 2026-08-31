"""The source-repository -> BirthPayload compilation boundary.

The property under test is one equality, stated three ways:

    CompiledBirthPayload.files  ==  actual source snapshot  ==  bytes birth copies

Everything here runs without gh, uv, or a network — git only, because git is the
substrate the immutable snapshot is defined over and faking it would test the
fake.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BIRTH_RUNNER = REPO / "scripts" / "birth-runner"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BIRTH_RUNNER / filename)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


compiler = _load("l9_birth_compile_payload", "compile_birth_payload.py")
verifier = _load("l9_birth_verify_payload", "verify_birth_payload.py")
new_repo = _load("l9_birth_engine_payload", "new_repo.py")
prov = compiler.prov

SCHEMA_FILE = BIRTH_RUNNER / "schemas" / "birth-payload.schema.json"

# A minimal standalone repository in the shape `payload-ownership.yaml` declares.
SOURCE_FILES: dict[str, str] = {
    "pyproject.toml": '[project]\nname = "ideaos"\nversion = "0.1.0"\n',
    ".l9/architecture.yaml": "schema: l9.architecture-spec/v1\n",
    "src/ideaos/__init__.py": '"""IdeaOS."""\n',
    "src/ideaos/core.py": "VALUE = 1\n",
    "tests/test_core.py": "def test_value() -> None:\n    assert True\n",
    "scripts/inventory_check.py": "print('ok')\n",
}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )


def _commit(root: Path, *paths: str, message: str = "snapshot") -> None:
    _git(root, "add", "--", *paths)
    _git(
        root,
        "-c",
        "user.email=birth@l9.invalid",
        "-c",
        "user.name=birth",
        "commit",
        "-q",
        "-m",
        message,
    )


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")


def make_source(
    root: Path,
    files: dict[str, str] | None = None,
    *,
    remote: str | None = "git@github.com:Quantum-L9/IdeaOS.git",
    commit: bool = True,
) -> Path:
    """A source repository: files, a git history, and an origin to be named by."""
    root.mkdir(parents=True, exist_ok=True)
    _write(root, SOURCE_FILES if files is None else files)
    _git(root, "init", "-q", "-b", "main")
    if remote:
        _git(root, "remote", "add", "origin", remote)
    if commit:
        _commit(root, *sorted(SOURCE_FILES if files is None else files))
    return root


def compile_from(source: Path, **kwargs: object) -> dict:
    return compiler.compile_payload(source, template_src=REPO, **kwargs)  # type: ignore[arg-type]


@pytest.fixture
def source(tmp_path: Path) -> Path:
    return make_source(tmp_path / "IdeaOS")


@pytest.fixture
def payload(source: Path) -> dict:
    return compile_from(source)


# ─────────────────────────────────────────────────────────────────────────────


class TestTheSnapshotIsImmutable:
    """BP-004. A payload is compiled from a committed, clean tree or not at all."""

    def test_a_clean_checkout_compiles(self, payload: dict) -> None:
        assert payload["schema"] == compiler.SCHEMA
        assert payload["source"]["repository"] == "Quantum-L9/IdeaOS"
        assert len(payload["source"]["revision"]) == 40

    def test_a_plain_directory_is_not_a_snapshot(self, tmp_path: Path) -> None:
        plain = tmp_path / "loose"
        _write(plain, SOURCE_FILES)
        with pytest.raises(compiler.PayloadCompileError, match="not a git checkout"):
            compile_from(plain)

    def test_a_repository_with_no_commits_has_no_revision(self, tmp_path: Path) -> None:
        empty = make_source(tmp_path / "empty", commit=False)
        with pytest.raises(compiler.PayloadCompileError, match="no commits"):
            compile_from(empty)

    def test_uncommitted_edits_stop_the_compilation(self, source: Path) -> None:
        (source / "src" / "ideaos" / "core.py").write_text("VALUE = 2\n", encoding="utf-8")
        with pytest.raises(compiler.PayloadCompileError, match="dirty"):
            compile_from(source)

    def test_an_untracked_file_is_dirt_too(self, source: Path) -> None:
        """Not "close enough". It would be staged by the birth's own commit."""
        (source / "src" / "ideaos" / "extra.py").write_text("X = 1\n", encoding="utf-8")
        with pytest.raises(compiler.PayloadCompileError, match="dirty"):
            compile_from(source)


class TestSourceIdentity:
    """The compiled payload describes the SOURCE, never the repository being born."""

    @pytest.mark.parametrize(
        "url",
        [
            "git@github.com:Quantum-L9/IdeaOS.git",
            "https://github.com/Quantum-L9/IdeaOS.git",
            "https://github.com/Quantum-L9/IdeaOS",
            "ssh://git@github.com/Quantum-L9/IdeaOS.git",
        ],
    )
    def test_owner_and_name_come_from_origin(self, tmp_path: Path, url: str) -> None:
        source = make_source(tmp_path / "src", remote=url)
        assert compile_from(source)["source"]["repository"] == "Quantum-L9/IdeaOS"

    def test_no_remote_and_no_override_stops_the_compilation(self, tmp_path: Path) -> None:
        source = make_source(tmp_path / "src", remote=None)
        with pytest.raises(compiler.PayloadCompileError, match="origin"):
            compile_from(source)

    def test_an_override_names_the_source(self, tmp_path: Path) -> None:
        source = make_source(tmp_path / "src", remote=None)
        document = compile_from(source, source_repository_override="Quantum-L9/IdeaOS")
        assert document["source"]["repository"] == "Quantum-L9/IdeaOS"

    def test_an_unusable_override_is_refused(self, source: Path) -> None:
        with pytest.raises(compiler.PayloadCompileError, match="owner/name"):
            compile_from(source, source_repository_override="not a slug")


class TestTheManifestIsEvidence:
    def test_every_file_is_hashed(self, source: Path, payload: dict) -> None:
        for entry in payload["files"]:
            body = (source / entry["path"]).read_bytes()
            assert entry["sha256"] == hashlib.sha256(body).hexdigest()

    def test_the_digest_is_the_shared_provenance_primitive(
        self, source: Path, payload: dict
    ) -> None:
        """BP: one algorithm, not a second hashing protocol invented here."""
        files = {rel: (source / rel).read_bytes() for rel in SOURCE_FILES}
        assert payload["manifest_sha256"] == prov.manifest_digest(files)

    def test_files_are_path_sorted(self, payload: dict) -> None:
        paths = [entry["path"] for entry in payload["files"]]
        assert paths == sorted(paths)

    def test_a_gitignored_artifact_is_not_authorized(self, tmp_path: Path) -> None:
        files = dict(SOURCE_FILES, **{".gitignore": "build/\n"})
        source = make_source(tmp_path / "src", files)
        (source / "build").mkdir()
        (source / "build" / "out.bin").write_bytes(b"\x00")
        paths = {entry["path"] for entry in compile_from(source)["files"]}
        assert "build/out.bin" not in paths

    def test_tracked_machine_state_is_excluded_exactly_as_the_overlay_excludes_it(
        self, tmp_path: Path
    ) -> None:
        """The manifest must equal the bytes birth copies, not a superset.

        The overlay never copies `__pycache__`; a manifest that authorized it
        would describe a newborn that can never exist.
        """
        files = dict(SOURCE_FILES, **{"src/ideaos/__pycache__/core.pyc": "junk\n"})
        source = make_source(tmp_path / "src", files)
        paths = {entry["path"] for entry in compile_from(source)["files"]}
        assert "src/ideaos/__pycache__/core.pyc" not in paths
        assert "src/ideaos/core.py" in paths

    def test_a_source_claiming_birth_provenance_is_refused(self, tmp_path: Path) -> None:
        """BP-009. A product never supplies the record of its own birth."""
        files = dict(SOURCE_FILES, **{prov.TEMPLATE_VERSION_PATH: "0.0.1\n"})
        source = make_source(tmp_path / "src", files)
        with pytest.raises(compiler.PayloadCompileError, match="engine-owned"):
            compile_from(source)

    def test_an_empty_snapshot_is_refused(self, tmp_path: Path) -> None:
        source = make_source(tmp_path / "src", {"README.md": "x\n"})
        _git(source, "rm", "-q", "--", "README.md")
        _commit(source, ".", message="empty")
        with pytest.raises(compiler.PayloadCompileError, match="no files"):
            compile_from(source)


class TestClassificationIsProposedFromEvidence:
    def test_a_repository_shaped_source_compiles_as_authoritative(self, payload: dict) -> None:
        assert payload["mode"] == "authoritative"
        assert payload["repository_shape"]["matched"] == [
            "pyproject.toml",
            ".l9/architecture.yaml",
            "src",
            "tests",
            "scripts/inventory_check.py",
        ]

    def test_a_fragment_compiles_as_additive(self, tmp_path: Path) -> None:
        source = make_source(tmp_path / "src", {"src/ideaos/extra.py": "X = 1\n"})
        document = compile_from(source)
        assert document["mode"] == "additive"
        assert document["repository_shape"]["matched"] == ["src"]

    def test_packages_are_the_ones_the_source_ships(self, payload: dict) -> None:
        assert payload["packages"]["python"] == ["ideaos"]

    def test_require_mode_refuses_a_source_that_does_not_qualify(self, tmp_path: Path) -> None:
        source = make_source(tmp_path / "src", {"src/ideaos/extra.py": "X = 1\n"})
        with pytest.raises(compiler.PayloadCompileError, match="compiles as additive"):
            compile_from(source, require_mode="authoritative")

    def test_require_mode_passes_when_the_evidence_agrees(self, source: Path) -> None:
        assert compile_from(source, require_mode="authoritative")["mode"] == "authoritative"


class TestPathsTheManifestCannotDescribe:
    def test_a_symlink_inside_the_source_is_hashed_as_its_target_text(self, tmp_path: Path) -> None:
        source = make_source(tmp_path / "src")
        (source / "link.py").symlink_to("src/ideaos/core.py")
        _commit(source, "link.py", message="link")
        entry = next(e for e in compile_from(source)["files"] if e["path"] == "link.py")
        assert entry["sha256"] == hashlib.sha256(b"src/ideaos/core.py").hexdigest()

    def test_a_symlink_escaping_the_source_root_is_refused(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("secret\n", encoding="utf-8")
        source = make_source(tmp_path / "src")
        (source / "escape.txt").symlink_to("../outside.txt")
        _commit(source, "escape.txt", message="escape")
        with pytest.raises(compiler.PayloadCompileError, match="escapes the source root"):
            compile_from(source)

    def test_case_colliding_paths_are_refused(self, tmp_path: Path) -> None:
        """One of the two would be lost on macOS, and not the one the digest names.

        Skipped where the filesystem under the test cannot hold both at once —
        there the collision is unreachable rather than unhandled.
        """
        source = make_source(tmp_path / "src")
        (source / "README.md").write_text("upper\n", encoding="utf-8")
        if (source / "readme.md").exists():
            pytest.skip("case-insensitive filesystem: both paths cannot coexist to collide")
        (source / "readme.md").write_text("lower\n", encoding="utf-8")
        _commit(source, "README.md", "readme.md", message="collide")
        with pytest.raises(compiler.PayloadCompileError, match="collide case-insensitively"):
            compile_from(source)


class TestTheContractCarriesEvidenceNotIntent:
    """BP-005/BP-006. The power of this document is that it is boring."""

    def test_the_document_has_exactly_the_locked_keys(self, payload: dict) -> None:
        assert set(payload) == {
            "schema",
            "source",
            "mode",
            "repository_shape",
            "packages",
            "files",
            "manifest_sha256",
        }

    @pytest.mark.parametrize(
        "inferred",
        [
            "capabilities",
            "absent_product_surfaces",
            "ci",
            "repo_class",
            "template_version",
            "organization",
            "repository",
            "born_at",
            "generated",
            "ownership",
        ],
    )
    def test_inferred_intent_is_absent(self, payload: dict, inferred: str) -> None:
        assert inferred not in payload

    def test_file_contents_stay_in_the_source_repository(self, payload: dict) -> None:
        """A manifest, not a second repository."""
        for entry in payload["files"]:
            assert set(entry) == {"path", "sha256"}


class TestDocumentValidator:
    def test_a_compiled_payload_validates(self, payload: dict) -> None:
        assert compiler.validate_payload_document(payload) == []

    def test_an_unrecognized_schema_reports_only_that(self, payload: dict) -> None:
        """Every other rule below belongs to v1. Reporting them would describe a
        contract the document never claimed to satisfy."""
        errors = compiler.validate_payload_document(dict(payload, schema="l9.birth-payload/v2"))
        assert len(errors) == 1
        assert "unrecognized payload schema" in errors[0]

    @pytest.mark.parametrize(
        ("mutation", "expected"),
        [
            ({"mode": "authoritative-ish"}, "mode is not one of"),
            ({"manifest_sha256": "nope"}, "manifest_sha256"),
            ({"capabilities": ["http"]}, "unknown key"),
            ({"files": []}, "files is not a non-empty array"),
        ],
    )
    def test_malformed_documents_are_named(
        self, payload: dict, mutation: dict, expected: str
    ) -> None:
        errors = compiler.validate_payload_document(dict(payload, **mutation))
        assert any(expected in err for err in errors), errors

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/etc/passwd", "repository-relative"),
            ("../outside.py", "repository-relative"),
            ("dir\\file.py", "repository-relative"),
        ],
    )
    def test_unusable_manifest_paths_are_named(
        self, payload: dict, path: str, expected: str
    ) -> None:
        broken = dict(payload)
        broken["files"] = [dict(payload["files"][0], path=path)]
        assert any(expected in err for err in compiler.validate_payload_document(broken))

    def test_duplicate_paths_are_named(self, payload: dict) -> None:
        broken = dict(payload)
        broken["files"] = [payload["files"][0], payload["files"][0]]
        assert any("duplicate" in err for err in compiler.validate_payload_document(broken))

    def test_every_error_is_reported_not_just_the_first(self, payload: dict) -> None:
        errors = compiler.validate_payload_document(
            dict(payload, mode="wrong", manifest_sha256="wrong")
        )
        assert len(errors) >= 2


class TestThePublishedSchemaAgreesWithTheGate:
    """The JSON Schema is the contract for external readers; the Python validator
    is the mechanical gate. Two statements of one contract have to agree, so they
    are held to the same verdicts here rather than trusted to stay in step."""

    @staticmethod
    def _validator():
        jsonschema = pytest.importorskip("jsonschema")
        return jsonschema.Draft202012Validator(json.loads(SCHEMA_FILE.read_text(encoding="utf-8")))

    def test_the_schema_file_is_a_valid_schema(self) -> None:
        jsonschema = pytest.importorskip("jsonschema")
        jsonschema.Draft202012Validator.check_schema(
            json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
        )

    def test_a_compiled_payload_satisfies_the_published_schema(self, payload: dict) -> None:
        assert list(self._validator().iter_errors(payload)) == []

    @pytest.mark.parametrize(
        "mutation",
        [
            {"schema": "l9.birth-payload/v2"},
            {"mode": "authoritative-ish"},
            {"manifest_sha256": "nope"},
            {"capabilities": ["http"]},
            {"files": []},
        ],
    )
    def test_both_readers_reject_the_same_documents(self, payload: dict, mutation: dict) -> None:
        broken = dict(payload, **mutation)
        assert compiler.validate_payload_document(broken)
        assert list(self._validator().iter_errors(broken))


class TestBirthReproducesRatherThanTrusts:
    """BP-007. The consumer re-derives the manifest immediately before assembly."""

    def test_an_untouched_source_reproduces(self, source: Path, payload: dict) -> None:
        report = verifier.verify_payload(payload, source, template_src=REPO, pkg="ideaos")
        assert report.result == "PASS", report.render()

    def test_one_changed_byte_stops_the_birth(self, source: Path, payload: dict) -> None:
        (source / "src" / "ideaos" / "core.py").write_text("VALUE = 2\n", encoding="utf-8")
        _commit(source, "src/ideaos/core.py", message="drift")
        report = verifier.verify_payload(payload, source, template_src=REPO)
        assert report.result == "FAIL"
        assert "source manifest" in report.reason

    def test_a_dirty_source_stops_the_birth(self, source: Path, payload: dict) -> None:
        (source / "src" / "ideaos" / "core.py").write_text("VALUE = 3\n", encoding="utf-8")
        report = verifier.verify_payload(payload, source, template_src=REPO)
        assert report.result == "FAIL"
        assert "dirty" in report.reason

    def test_an_added_file_is_unauthorized(self, source: Path, payload: dict) -> None:
        (source / "src" / "ideaos" / "extra.py").write_text("X = 1\n", encoding="utf-8")
        _commit(source, "src/ideaos/extra.py", message="add")
        report = verifier.verify_payload(payload, source, template_src=REPO)
        assert "unauthorized path(s) present" in report.reason

    def test_a_hand_edited_mode_cannot_promote_a_fragment(self, tmp_path: Path) -> None:
        """The compiler proposes; the ownership contract decides."""
        source = make_source(tmp_path / "src", {"src/ideaos/extra.py": "X = 1\n"})
        promoted = dict(compile_from(source), mode="authoritative")
        report = verifier.verify_payload(promoted, source, template_src=REPO)
        assert report.result == "FAIL"
        assert "does not get to promote itself" in report.reason

    def test_a_tampered_digest_is_caught(self, source: Path, payload: dict) -> None:
        tampered = dict(payload, manifest_sha256="0" * 64)
        report = verifier.verify_payload(tampered, source, template_src=REPO)
        assert "manifest digest" in report.reason

    def test_pkg_must_name_a_package_the_payload_ships(self, source: Path, payload: dict) -> None:
        report = verifier.verify_payload(payload, source, template_src=REPO, pkg="wrong_name")
        assert report.result == "FAIL"
        assert "not a package this payload ships" in report.reason

    def test_the_report_names_every_failure(self, source: Path, payload: dict) -> None:
        (source / "src" / "ideaos" / "core.py").write_text("VALUE = 9\n", encoding="utf-8")
        _commit(source, "src/ideaos/core.py", message="drift")
        report = verifier.verify_payload(payload, source, template_src=REPO, pkg="wrong")
        assert len(report.failed) >= 2


class TestCommandLine:
    def test_compile_writes_a_payload_and_verify_reproduces_it(
        self, source: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "payload.json"
        assert compiler.main(["--source", str(source), "--out", str(out)]) == 0
        assert verifier.main(["--payload", str(out), "--source", str(source)]) == 0
        assert json.loads(out.read_text(encoding="utf-8"))["schema"] == compiler.SCHEMA

    def test_compile_fails_closed_on_a_dirty_source(self, source: Path, tmp_path: Path) -> None:
        (source / "src" / "ideaos" / "core.py").write_text("VALUE = 4\n", encoding="utf-8")
        assert compiler.main(["--source", str(source), "--out", str(tmp_path / "p.json")]) == 2
        assert not (tmp_path / "p.json").exists()

    def test_verify_fails_closed_on_a_malformed_payload(self, source: Path, tmp_path: Path) -> None:
        broken = tmp_path / "payload.json"
        broken.write_text('{"schema": "l9.birth-payload/v9"}\n', encoding="utf-8")
        assert verifier.main(["--payload", str(broken), "--source", str(source)]) == 1

    def test_verify_reports_json_when_asked(
        self, source: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = tmp_path / "payload.json"
        compiler.main(["--source", str(source), "--out", str(out)])
        capsys.readouterr()
        verifier.main(["--payload", str(out), "--source", str(source), "--json"])
        report = json.loads(capsys.readouterr().out)
        assert report["schema"] == verifier.REPORT_SCHEMA
        assert report["result"] == "PASS"


class TestTheBirthEngineConsumesOnlyWhatItReproduced:
    """The engine's half of the boundary: stage 1, before a single file is copied."""

    @staticmethod
    def _config(tmp_path: Path, payload: Path, contract: Path, pkg: str = "ideaos"):
        return new_repo.build_config(
            new_repo.parse_args(
                [
                    "--repo",
                    "ideaos",
                    "--pkg",
                    pkg,
                    "--desc",
                    "A product",
                    "--work-dir",
                    str(tmp_path / "work"),
                    "--payload",
                    str(payload),
                    "--payload-contract",
                    str(contract),
                    "--no-remote",
                ]
            )
        )

    def _contract(self, source: Path, tmp_path: Path) -> Path:
        out = tmp_path / "payload.json"
        assert compiler.main(["--source", str(source), "--out", str(out)]) == 0
        return out

    def test_a_reproduced_contract_sets_the_verified_mode(
        self, source: Path, tmp_path: Path
    ) -> None:
        cfg = self._config(tmp_path, source, self._contract(source, tmp_path))
        receipt = new_repo.BirthReceipt()
        new_repo._preflight_payload_contract(cfg, receipt)
        assert cfg.verified_payload_mode == "authoritative"
        stage = receipt.stages[-1]
        assert stage.status == "PASS"
        assert "authoritative" in stage.detail
        assert receipt.payload_source["repository"] == "Quantum-L9/IdeaOS"

    def test_drift_between_compilation_and_birth_stops_the_birth(
        self, source: Path, tmp_path: Path
    ) -> None:
        contract = self._contract(source, tmp_path)
        (source / "src" / "ideaos" / "core.py").write_text("VALUE = 99\n", encoding="utf-8")
        _commit(source, "src/ideaos/core.py", message="drift")
        cfg = self._config(tmp_path, source, contract)
        with pytest.raises(new_repo.BirthError, match="did not reproduce"):
            new_repo._preflight_payload_contract(cfg, new_repo.BirthReceipt())

    def test_there_is_no_fallback_to_a_naked_directory_overlay(
        self, source: Path, tmp_path: Path
    ) -> None:
        """BP-012. An invalid authoritative payload is a refusal, not a downgrade."""
        contract = tmp_path / "payload.json"
        contract.write_text('{"schema": "l9.birth-payload/v1"}\n', encoding="utf-8")
        cfg = self._config(tmp_path, source, contract)
        with pytest.raises(new_repo.BirthError, match="malformed birth payload"):
            new_repo._preflight_payload_contract(cfg, new_repo.BirthReceipt())
        assert cfg.verified_payload_mode is None

    def test_the_two_digests_stay_separate_proofs(self, source: Path, tmp_path: Path) -> None:
        """BP-010. Source contribution and born-repository content are different
        questions; the payload never claims to answer the second."""
        cfg = self._config(tmp_path, source, self._contract(source, tmp_path))
        receipt = new_repo.BirthReceipt()
        new_repo._preflight_payload_contract(cfg, receipt)
        assert receipt.payload_contract
        assert receipt.manifest_sha256 == ""


class TestTheOverlayWritesTheBytesTheManifestAuthorized:
    """The third term of the invariant, checked directly.

    A manifest that hashes a symlink's target text while the overlay writes the
    target's CONTENT under that name describes a newborn that cannot exist. The
    two copy paths — template and payload — now answer symlinks the same way.
    """

    def test_a_payload_symlink_is_copied_as_a_symlink(self, tmp_path: Path) -> None:
        payload = tmp_path / "payload"
        (payload / "src" / "ideaos").mkdir(parents=True)
        (payload / "src" / "ideaos" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
        (payload / "link.py").symlink_to("src/ideaos/core.py")

        dest = tmp_path / "dest"
        dest.mkdir()
        written = new_repo.overlay_payload(payload, dest)

        assert "link.py" in written
        assert (dest / "link.py").is_symlink()
        assert (dest / "link.py").readlink().as_posix() == "src/ideaos/core.py"

    def test_the_copied_bytes_hash_to_what_the_payload_authorized(self, tmp_path: Path) -> None:
        source = make_source(tmp_path / "src")
        (source / "link.py").symlink_to("src/ideaos/core.py")
        _commit(source, "link.py", message="link")
        document = compile_from(source)

        dest = tmp_path / "dest"
        dest.mkdir()
        new_repo.overlay_payload(source, dest)

        for entry in document["files"]:
            copied = dest / entry["path"]
            body = (
                copied.readlink().as_posix().encode("utf-8")
                if copied.is_symlink()
                else copied.read_bytes()
            )
            assert hashlib.sha256(body).hexdigest() == entry["sha256"], entry["path"]

    def test_an_existing_target_is_replaced_rather_than_written_through(
        self, tmp_path: Path
    ) -> None:
        """The payload wins on collision, symlinks included."""
        payload = tmp_path / "payload"
        payload.mkdir()
        (payload / "target.txt").write_text("payload\n", encoding="utf-8")
        (payload / "link.txt").symlink_to("target.txt")

        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "link.txt").write_text("chassis\n", encoding="utf-8")
        new_repo.overlay_payload(payload, dest)

        assert (dest / "link.txt").is_symlink()
        assert (dest / "link.txt").read_text(encoding="utf-8") == "payload\n"
