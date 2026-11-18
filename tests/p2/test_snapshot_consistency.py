"""P2: a changing worktree cannot keep an exact source SHA on mixed-time evidence."""
from __future__ import annotations

import importlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from reqea.core.orchestrator import build_audit
from reqea_codegraph import build_code_index


@unittest.skipUnless(shutil.which("git"), "Git CLI required for exact provenance tests")
class SnapshotConsistency(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        src = self.root / "src"
        src.mkdir(parents=True)
        self.code = src / "app.py"
        self.code.write_text("def answer(): return 42\n", encoding="utf-8")
        self.requirements = self.root / "requirements.md"
        self.requirements.write_text(
            "# REQ-001 static evidence\n"
            "Reference src/app.py\n"
            "Acceptance criteria:\n"
            "- local file exists\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "requirements.md", "src/app.py"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=P2 Fixture",
                        "-c", "user.email=p2-fixture@example.invalid",
                        "commit", "-qm", "synthetic fixed baseline"], check=True)
        self.sha = subprocess.check_output(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True
        ).strip().lower()

    def _commit_fixture(self, *files):
        subprocess.run(["git", "-C", str(self.root), "add", *files], check=True)
        subprocess.run(["git", "-C", str(self.root),
                        "-c", "user.name=P2 Fixture",
                        "-c", "user.email=p2-fixture@example.invalid",
                        "commit", "-qm", "synthetic fixture revision"], check=True)
        return subprocess.check_output(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            text=True).strip().lower()

    def test_ignored_untracked_code_never_claims_exact_head(self):
        (self.root / ".gitignore").write_text("src/ignored.py\n", encoding="utf-8")
        frozen = self._commit_fixture(".gitignore")
        ignored = self.root / "src" / "ignored.py"
        ignored.write_text("def ignored_reference(): return 3\n", encoding="utf-8")
        self.requirements.write_text(
            "# REQ-001 local evidence\nReference src/ignored.py\n"
            "Acceptance criteria:\n- source src/ignored.py exists\n", encoding="utf-8")
        # Persist changed requirements as a separate clean baseline.
        frozen = self._commit_fixture("requirements.md")
        status = subprocess.check_output(
            ["git", "-C", str(self.root), "status", "--porcelain"],
            text=True).strip()
        self.assertEqual(status, "")
        outcome = build_audit(str(self.root), str(self.requirements))
        self.assertEqual(outcome["source_sha"], "UNVERIFIED")
        self.assertEqual(outcome["status"], "UNASSESSED")
        self.assertEqual(outcome["findings"], [])
        self.assertIn("indexed_files_not_tracked_at_head", outcome["warnings"])

    def test_ignored_requirements_never_claim_exact_head(self):
        (self.root / ".gitignore").write_text("src/private_req.md\n", encoding="utf-8")
        self._commit_fixture(".gitignore")
        ignored_req = self.root / "src" / "private_req.md"
        ignored_req.write_text(
            "# REQ-001 private ignored\nReference src/app.py\n"
            "Acceptance criteria:\n- read local app\n", encoding="utf-8")
        outcome = build_audit(str(self.root), str(ignored_req))
        self.assertEqual(outcome["source_sha"], "UNVERIFIED")
        self.assertEqual(outcome["status"], "UNASSESSED")
        self.assertIn("indexed_files_not_tracked_at_head", outcome["warnings"])

    def test_assume_unchanged_modified_source_cannot_inherit_head(self):
        # git status deliberately omits this change, even with untracked-file checks.
        subprocess.run(["git", "-C", str(self.root), "update-index",
                        "--assume-unchanged", "src/app.py"], check=True)
        self.code.write_text("def answer(): return 999\\n".replace("\\n", "\n"), encoding="utf-8")
        status = subprocess.check_output(
            ["git", "-C", str(self.root), "status", "--porcelain"],
            text=True).strip()
        self.assertEqual(status, "")
        result = build_audit(str(self.root), str(self.requirements))
        self.assertEqual(result["source_sha"], "UNVERIFIED")
        self.assertEqual(result["status"], "UNASSESSED")
        self.assertEqual(result["findings"], [])
        self.assertIn("indexed_files_not_tracked_at_head", result["warnings"])

    def test_skip_worktree_requirements_cannot_inherit_head(self):
        subprocess.run(["git", "-C", str(self.root), "update-index",
                        "--skip-worktree", "requirements.md"], check=True)
        status = subprocess.check_output(
            ["git", "-C", str(self.root), "status", "--porcelain"],
            text=True).strip()
        self.assertEqual(status, "")
        result = build_audit(str(self.root), str(self.requirements))
        self.assertEqual(result["source_sha"], "UNVERIFIED")
        self.assertEqual(result["status"], "UNASSESSED")
        self.assertEqual(result["findings"], [])
        self.assertIn("indexed_files_not_tracked_at_head", result["warnings"])

    def test_tracked_unicode_source_keeps_head(self):
        korean = self.root / "src" / "한글.py"
        korean.write_text("def available(): return 1\n", encoding="utf-8")
        self.requirements.write_text(
            "# REQ-001 Korean reference\nReference src/한글.py\n"
            "Acceptance criteria:\n- indexed source src/한글.py\n", encoding="utf-8")
        expected = self._commit_fixture("requirements.md", "src/한글.py")
        result = build_audit(str(self.root), str(self.requirements))
        self.assertEqual(result["source_sha"], expected, result["warnings"])
        self.assertNotIn("indexed_files_not_tracked_at_head", result["warnings"])

    def test_stable_checkout_keeps_exact_source_sha(self):
        outcome = build_audit(str(self.root), str(self.requirements))
        self.assertEqual(outcome["source_sha"], self.sha)
        self.assertEqual(outcome["schema_version"], "reqea.v1")
        self.assertNotIn("source_snapshot_changed_during_analysis", outcome["warnings"])

    def test_file_modified_after_index_cannot_keep_original_sha(self):
        def index_then_change(root, options):
            evidence = build_code_index(root, options)
            self.code.write_text("def answer(): return 999\n", encoding="utf-8")
            return evidence

        def module_loader(name):
            if name == "reqea_codegraph":
                return SimpleNamespace(build_code_index=index_then_change)
            return importlib.import_module(name)

        with patch("reqea.core.orchestrator.import_module", side_effect=module_loader):
            outcome = build_audit(str(self.root), str(self.requirements))
        self.assertEqual(outcome["schema_version"], "reqea.v1")
        self.assertEqual(outcome["source_sha"], "UNVERIFIED")
        self.assertEqual(outcome["status"], "UNASSESSED")
        self.assertEqual(outcome["findings"], [])
        self.assertIn("source_snapshot_changed_during_analysis", outcome["warnings"])
        self.assertEqual(outcome["verification_status"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
