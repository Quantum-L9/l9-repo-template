"""Birth provenance: the immutable record, and what it takes to falsify it.

These are the checks that would have caught a repository stamped with one
template version and pinned to a commit carrying another — before the remote
repository existed. Everything here runs with git and nothing else: no network,
no gh, no uv.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BIRTH_RUNNER = REPO / "scripts" / "birth-runner"
_SPEC = importlib.util.spec_from_file_location(
    "l9_verify_birth_integrity", BIRTH_RUNNER / "verify_birth_integrity.py"
)
assert _SPEC is not None
assert _SPEC.loader is not None
verifier = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = verifier
_SPEC.loader.exec_module(verifier)
# The checker locates the provenance module relative to its own file. Reading it
# back off the checker is what keeps this test honest about which module the
# checker actually runs.
prov = verifier.prov

BORN_AT = "2026-08-26T00:00:00+00:00"
TEMPLATE_SHA = "a" * 40
POLICY_SHA = "b" * 40


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@quantum-l9.invalid",
        "commit",
        "-q",
        "-m",
        message,
    )


def born_repo(root: Path, *, version: str = "2.1.0", commit: bool = True) -> Path:
    """A repository stamped exactly the way stage 5 stamps one, then committed.

    Built from the same `birth_provenance` functions the engine calls, so a
    change to the record's shape shows up here as a test that has to be read —
    not as a fixture that quietly describes a shape nothing writes any more.
    """
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# product\n", encoding="utf-8")
    (root / ".l9").mkdir(exist_ok=True)
    (root / prov.TEMPLATE_VERSION_PATH).write_text(version + "\n", encoding="utf-8")
    (root / prov.MARKER_PATH).write_text(
        prov.render_marker(
            profile_name="non_constellation_python",
            repository="Quantum-L9/l9-product",
            template_sha=TEMPLATE_SHA,
            template_version=version,
            org_profile_sha=POLICY_SHA,
            born_at=BORN_AT,
        ),
        encoding="utf-8",
    )
    (root / prov.TEMPLATE_STATE_PATH).write_text(
        prov.render_template_state(
            template_sha=TEMPLATE_SHA,
            template_version=version,
            org_policy_sha=POLICY_SHA,
            reconciled_at=BORN_AT,
        ),
        encoding="utf-8",
    )
    manifest = prov.worktree_manifest(root, exclude={prov.BIRTH_RECEIPT_PATH})
    receipt = prov.build_receipt(
        repository="Quantum-L9/l9-product",
        repo_class="non_constellation_python",
        template_sha=TEMPLATE_SHA,
        template_version=version,
        org_policy_sha=POLICY_SHA,
        payload_mode="authoritative",
        manifest_sha256=prov.manifest_digest(manifest),
        born_at=BORN_AT,
    )
    (root / prov.BIRTH_RECEIPT_PATH).write_text(prov.render_receipt_json(receipt), encoding="utf-8")
    if commit:
        message = "\n".join(
            ["chore: birth Quantum-L9/l9-product", "", *prov.commit_trailers(receipt)]
        )
        _commit(root, message)
    return root


def _verify(root: Path) -> verifier.Report:
    report, _ = verifier.verify(root, require_receipt=True)
    return report


def _status(report: verifier.Report, key: str) -> str:
    return next(check.status for check in report.checks if check.key == key)


def _load_receipt(root: Path) -> dict:
    return json.loads((root / prov.BIRTH_RECEIPT_PATH).read_text(encoding="utf-8"))


def _rewrite_receipt(root: Path, receipt: dict) -> None:
    (root / prov.BIRTH_RECEIPT_PATH).write_text(prov.render_receipt_json(receipt), encoding="utf-8")


class TestFlatReader:
    def test_reads_two_levels(self) -> None:
        doc = prov.parse_flat_yaml("a: 1\nb:\n  c: 2\n  d: 3\ne: 4\n")
        assert doc == {"a": "1", "b": {"c": "2", "d": "3"}, "e": "4"}

    def test_ignores_comments_and_blank_lines(self) -> None:
        assert prov.parse_flat_yaml("# note\n\nprofile: x\n") == {"profile": "x"}

    def test_strips_optional_quotes(self) -> None:
        assert prov.parse_flat_yaml('profile: "x"\n')["profile"] == "x"

    @pytest.mark.parametrize("text", [None, "", "   "])
    def test_empty_input_is_an_empty_document(self, text: str | None) -> None:
        assert prov.parse_flat_yaml(text) == {}


class TestDigests:
    def test_receipt_digest_ignores_key_order(self) -> None:
        a = {"schema": "x", "repository": "r", "digest": "ignored"}
        b = {"repository": "r", "schema": "x"}
        assert prov.receipt_digest(a) == prov.receipt_digest(b)

    def test_receipt_digest_moves_when_a_value_moves(self) -> None:
        base = {"schema": "x", "repository": "r"}
        assert prov.receipt_digest(base) != prov.receipt_digest({**base, "repository": "s"})

    def test_build_receipt_is_self_consistent(self) -> None:
        receipt = prov.build_receipt(
            repository="Quantum-L9/x",
            repo_class="non_constellation_python",
            template_sha=TEMPLATE_SHA,
            template_version="2.1.0",
            org_policy_sha=POLICY_SHA,
            payload_mode="none",
            manifest_sha256="c" * 64,
            born_at=BORN_AT,
        )
        assert receipt["digest"] == prov.receipt_digest(receipt)

    def test_manifest_digest_is_path_ordered_not_insertion_ordered(self) -> None:
        forward = prov.manifest_digest({"a": b"1", "b": b"2"})
        backward = prov.manifest_digest({"b": b"2", "a": b"1"})
        assert forward == backward

    def test_manifest_digest_moves_when_content_moves(self) -> None:
        assert prov.manifest_digest({"a": b"1"}) != prov.manifest_digest({"a": b"2"})

    def test_manifest_digest_moves_when_a_file_appears(self) -> None:
        assert prov.manifest_digest({"a": b"1"}) != prov.manifest_digest({"a": b"1", "b": b""})


class TestPinnedTemplateVersion:
    """The invariant that catches a 2.0.0 / 2.1.0 disagreement before creation."""

    @staticmethod
    def _template(root: Path, committed: str) -> Path:
        root.mkdir(parents=True)
        _git(root, "init", "-q", "-b", "main")
        (root / prov.TEMPLATE_VERSION_PATH).write_text(committed + "\n", encoding="utf-8")
        _commit(root, "chore: template")
        return root

    def test_reads_the_commit_not_the_working_tree(self, tmp_path: Path) -> None:
        template = self._template(tmp_path / "template", "2.0.0")
        sha = _git(template, "rev-parse", "HEAD").strip()
        # Someone bumps the file and does not commit it. The birth record pins a
        # SHA, so the version it may record is the SHA's, never the tree's.
        (template / prov.TEMPLATE_VERSION_PATH).write_text("2.1.0\n", encoding="utf-8")
        assert prov.template_version_at(template, sha) == "2.0.0"

    def test_an_uncommitted_bump_stops_the_birth(self, tmp_path: Path) -> None:
        template = self._template(tmp_path / "template", "2.0.0")
        sha = _git(template, "rev-parse", "HEAD").strip()
        with pytest.raises(prov.ProvenanceError, match="template version disagreement"):
            prov.assert_version_agrees(assembled="2.1.0", pinned="2.0.0", sha=sha)

    def test_agreement_is_silent(self) -> None:
        prov.assert_version_agrees(assembled="2.1.0", pinned="2.1.0", sha=TEMPLATE_SHA)

    def test_an_unknown_template_sha_is_not_pinnable(self, tmp_path: Path) -> None:
        template = self._template(tmp_path / "template", "2.0.0")
        with pytest.raises(prov.ProvenanceError):
            prov.template_version_at(template, "unknown")

    def test_a_commit_without_the_version_file_is_not_pinnable(self, tmp_path: Path) -> None:
        root = tmp_path / "template"
        root.mkdir()
        _git(root, "init", "-q", "-b", "main")
        (root / "README.md").write_text("x\n", encoding="utf-8")
        _commit(root, "chore: no version file")
        sha = _git(root, "rev-parse", "HEAD").strip()
        with pytest.raises(prov.ProvenanceError):
            prov.template_version_at(root, sha)


class TestProtectedBirthPaths:
    """A product owns its product. It never owns the record of its own birth."""

    @pytest.mark.parametrize("rel", sorted(prov.ENGINE_OWNED_PATHS))
    def test_a_payload_supplying_one_is_rejected(self, tmp_path: Path, rel: str) -> None:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("stale\n", encoding="utf-8")
        assert prov.birth_path_collisions(tmp_path) == [rel]
        with pytest.raises(prov.ProvenanceError, match="protected birth paths"):
            prov.assert_payload_owns_no_birth_paths(tmp_path)

    def test_an_ordinary_product_payload_is_untouched(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("", encoding="utf-8")
        assert prov.birth_path_collisions(tmp_path) == []
        prov.assert_payload_owns_no_birth_paths(tmp_path)

    def test_the_conformance_record_is_protected_too(self) -> None:
        # Mutable is not the same as payload-owned: reconciliation moves it, a
        # product tree does not get to arrive carrying one.
        assert prov.TEMPLATE_STATE_PATH in prov.ENGINE_OWNED_PATHS
        assert prov.TEMPLATE_STATE_PATH not in prov.BIRTH_OWNED_PATHS


class TestTrailers:
    def test_round_trip(self) -> None:
        receipt = prov.build_receipt(
            repository="Quantum-L9/x",
            repo_class="non_constellation_python",
            template_sha=TEMPLATE_SHA,
            template_version="2.1.0",
            org_policy_sha=POLICY_SHA,
            payload_mode="none",
            manifest_sha256="c" * 64,
            born_at=BORN_AT,
        )
        message = "chore: birth\n\n" + "\n".join(prov.commit_trailers(receipt))
        parsed = prov.parse_trailers(message)
        assert parsed[prov.TRAILER_RECEIPT] == f"sha256:{receipt['digest']}"
        assert parsed[prov.TRAILER_TEMPLATE] == TEMPLATE_SHA
        assert parsed[prov.TRAILER_POLICY] == POLICY_SHA
        assert parsed[prov.TRAILER_CLASS] == "non_constellation_python"

    def test_a_subject_only_message_has_no_trailers(self) -> None:
        assert prov.parse_trailers("chore: birth") == {}


class TestBirthIntegrity:
    def test_a_freshly_born_repository_passes(self, tmp_path: Path) -> None:
        report = _verify(born_repo(tmp_path / "repo"))
        assert report.result == "PASS", report.render()
        assert _status(report, "root.manifest") == "PASS"
        assert _status(report, "root.trailers") == "PASS"

    def test_an_unborn_repository_is_not_a_failure(self, tmp_path: Path) -> None:
        (tmp_path / "plain").mkdir()
        report, born = verifier.verify(tmp_path / "plain", require_receipt=False)
        assert not born
        assert report.result == "PASS"

    def test_a_required_receipt_that_is_absent_fails(self, tmp_path: Path) -> None:
        (tmp_path / "plain").mkdir()
        report, _ = verifier.verify(tmp_path / "plain", require_receipt=True)
        assert report.result == "FAIL"

    def test_a_tampered_receipt_digest_fails(self, tmp_path: Path) -> None:
        root = born_repo(tmp_path / "repo")
        receipt = _load_receipt(root)
        receipt["repository"] = "Quantum-L9/somebody-elses-repo"
        _rewrite_receipt(root, receipt)
        report = _verify(root)
        assert _status(report, "receipt.digest") == "FAIL"

    def test_a_version_that_no_longer_matches_the_receipt_fails(self, tmp_path: Path) -> None:
        root = born_repo(tmp_path / "repo")
        (root / prov.TEMPLATE_VERSION_PATH).write_text("9.9.9\n", encoding="utf-8")
        report = _verify(root)
        assert _status(report, "birth.version") == "FAIL"
        # And the same edit shows up as provenance mutation, not merely as drift.
        assert _status(report, "root.immutable") == "FAIL"

    def test_a_rewritten_birth_block_fails(self, tmp_path: Path) -> None:
        root = born_repo(tmp_path / "repo")
        (root / prov.MARKER_PATH).write_text(
            prov.render_marker(
                profile_name="non_constellation_python",
                repository="Quantum-L9/l9-product",
                template_sha="f" * 40,
                template_version="2.1.0",
                org_profile_sha=POLICY_SHA,
                born_at=BORN_AT,
            ),
            encoding="utf-8",
        )
        report = _verify(root)
        assert _status(report, "birth.marker") == "FAIL"

    def test_reconciling_the_conformance_record_stays_green(self, tmp_path: Path) -> None:
        """The whole point of the split.

        A repository reconciled onto a newer template baseline disagrees with its
        own birth record about what it conforms to — and is still, provably, the
        repository that birth record describes.
        """
        root = born_repo(tmp_path / "repo")
        (root / prov.TEMPLATE_STATE_PATH).write_text(
            prov.render_template_state(
                template_sha="e" * 40,
                template_version="2.4.0",
                org_policy_sha="d" * 40,
                reconciled_at="2027-01-05T00:00:00+00:00",
                reconciled_by="l9-reconcile",
            ),
            encoding="utf-8",
        )
        (root / "src.py").write_text("VALUE = 1\n", encoding="utf-8")
        _commit(root, "chore(l9): reconcile repository baseline to 2.4.0")
        report = _verify(root)
        assert report.result == "PASS", report.render()

    def test_a_missing_conformance_record_fails(self, tmp_path: Path) -> None:
        root = born_repo(tmp_path / "repo")
        (root / prov.TEMPLATE_STATE_PATH).unlink()
        report = _verify(root)
        assert _status(report, "conformance.state") == "FAIL"

    def test_a_contents_digest_that_does_not_cover_the_repository_fails(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "repo"
        born_repo(root, commit=False)
        receipt = _load_receipt(root)
        receipt["manifest_sha256"] = "0" * 64
        receipt["digest"] = prov.receipt_digest(receipt)
        _rewrite_receipt(root, receipt)
        _commit(root, "chore: birth\n\n" + "\n".join(prov.commit_trailers(receipt)))
        report = _verify(root)
        assert _status(report, "receipt.digest") == "PASS"
        assert _status(report, "root.manifest") == "FAIL"

    def test_a_commit_without_provenance_trailers_fails(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        born_repo(root, commit=False)
        _commit(root, "chore: birth with no record")
        report = _verify(root)
        assert _status(report, "root.trailers") == "FAIL"

    def test_the_git_leg_reports_skip_before_the_first_commit(self, tmp_path: Path) -> None:
        root = born_repo(tmp_path / "repo", commit=False)
        report = _verify(root)
        assert _status(report, "root.commit") == "SKIP"
        assert report.result == "PASS", report.render()

    def test_a_grafted_history_has_no_single_birth_commit(self, tmp_path: Path) -> None:
        root = born_repo(tmp_path / "repo")
        other = tmp_path / "other"
        other.mkdir()
        _git(other, "init", "-q", "-b", "main")
        (other / "unrelated.md").write_text("x\n", encoding="utf-8")
        _commit(other, "chore: unrelated root")
        _git(root, "remote", "add", "other", str(other))
        _git(root, "fetch", "-q", "other")
        _git(
            root,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@quantum-l9.invalid",
            "merge",
            "-q",
            "--allow-unrelated-histories",
            "--no-edit",
            "other/main",
        )
        report = _verify(root)
        assert _status(report, "root.commit") == "FAIL"
