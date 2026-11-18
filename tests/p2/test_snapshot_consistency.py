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
