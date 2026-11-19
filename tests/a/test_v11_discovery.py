"""V1.1 P1 vertical local discovery and explicit canonical-selection smoke."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from reqea.core.discovery import discover_local_requirements
from reqea.core.selector import select_requirements


def _req(n: int) -> str:
    return f"# REQ-{n:03d} candidate\nAcceptance criteria:\n- inspect src/app.py\n"


class LocalSourceDiscovery(unittest.TestCase):
    def test_only_document_autoselected_then_existing_audit_runs(self):
        from reqea.core.orchestrator import build_audit
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "한글 source"
            (root / "docs").mkdir(parents=True)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("def ok(): return True\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("See docs/FINAL_BLUEPRINT.md\n", encoding="utf-8")
            doc = root / "docs" / "FINAL_BLUEPRINT.md"
            doc.write_text(_req(1), encoding="utf-8")
            found = discover_local_requirements(str(root))
            self.assertEqual(found["status"], "SINGLE_CANDIDATE", found)
            self.assertEqual(found["candidates"][0]["path"], "docs/FINAL_BLUEPRINT.md")
            selected = select_requirements(found)
            self.assertEqual(Path(selected["requirements_path"]), doc)
            report = build_audit(str(root), selected["requirements_path"])
            self.assertEqual([f["req_id"] for f in report["findings"]], ["REQ-001"])
            self.assertEqual(report["verification_status"], "NOT_RUN")

    def test_multiple_valid_designs_require_explicit_choice(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            (root / "docs" / "FINAL_BLUEPRINT.md").write_text(_req(1), encoding="utf-8")
            (root / "docs" / "FINAL_BLUEPRINT_V11.md").write_text(_req(31), encoding="utf-8")
            found = discover_local_requirements(str(root))
            self.assertEqual(found["status"], "AMBIGUOUS")
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                select_requirements(found)
            selected = select_requirements(found, "docs/FINAL_BLUEPRINT_V11.md")
            self.assertEqual(selected["relative_path"], "docs/FINAL_BLUEPRINT_V11.md")
            with self.assertRaises(ValueError):
                select_requirements(found, "../outside.md")

    def test_mutated_or_replaced_document_cannot_inherit_discovery(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            doc = root / "requirements.md"
            doc.write_text(_req(2), encoding="utf-8")
            found = discover_local_requirements(str(root))
            doc.write_text(_req(3), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed"):
                select_requirements(found)

    def test_symlinked_candidate_and_sensitive_files_not_read(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "project"
            root.mkdir()
            out = base / "outside.md"
            out.write_text(_req(55), encoding="utf-8")
            try:
                (root / "requirements.md").symlink_to(out)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(type(exc).__name__)
            (root / ".env").write_text("TOP_SECRET", encoding="utf-8")
            found = discover_local_requirements(str(root))
            self.assertEqual(found["status"], "NO_CANDIDATE", found)
            self.assertFalse(found["candidates"])
            self.assertNotIn("TOP_SECRET", json.dumps(found))

    def test_hardlink_never_selected(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "project"
            root.mkdir()
            original = base / "sensitive.md"
            original.write_text(_req(7), encoding="utf-8")
            try:
                os.link(original, root / "requirements.md")
            except OSError as exc:
                self.skipTest(type(exc).__name__)
            found = discover_local_requirements(str(root))
            self.assertEqual(found["status"], "NO_CANDIDATE")

    def test_bounded_scan_refuses_incomplete_scope(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "requirements.md").write_text(_req(1), encoding="utf-8")
            for i in range(755):
                (root / f"a{i:04d}.py").write_text("x=1\n", encoding="utf-8")
            found = discover_local_requirements(str(root))
            self.assertEqual(found["status"], "BLOCKED")
            self.assertIn("INCOMPLETE_DISCOVERY_SCOPE", found["warnings"])
            with self.assertRaises(ValueError):
                select_requirements(found)


if __name__ == "__main__":
    unittest.main()
