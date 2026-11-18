"""Minimal P1 integration smoke: only synthetic source, no customer content."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from reqea.core.orchestrator import build_audit, render_audit_html
from reqea.core.output import save_artifacts
from reqea.core.requirements_json import parse_json_requirements
from reqea.core.requirements_md import parse_markdown_requirements

FAIL_CLOSED = {
    "required_B_or_C_module_unavailable",
    "B_contract_or_SHA_mismatch",
    "C_contract_or_SHA_mismatch",
    "C_invalid_or_untrusted_status",
    "C_invalid_finding_status",
    "C_invalid_warning_contract",
    "analysis_failed_without_verified_evidence",
}
CANDIDATES = {"CODE_CANDIDATE", "GAP_CANDIDATE", "REVIEW_REQUIRED", "UNASSESSED"}


class P1IntegrationSmoke(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        parent = Path(self.temp.name)
        self.root = parent / "source"
        self.root.mkdir()
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text(
            "def run():\n    return 'REQ-001 static-only candidate'\n",
            encoding="utf-8",
        )
        self.req = self.root / "requirements.md"
        self.req.write_text(
            "# REQ-001 - Basic local audit\n"
            "Explicit reference: src/app.py\n"
            "Acceptance criteria:\n"
            "- Static method candidate appears\n",
            encoding="utf-8",
        )
        self.out = parent / "results"

    def test_a_b_c_live_contract_to_html_and_manifest(self):
        result = build_audit(str(self.root), str(self.req))
        self.assertEqual(result["schema_version"], "reqea.v1")
        self.assertEqual(result["source_sha"], "UNVERIFIED")
        self.assertEqual(result["verification_status"], "NOT_RUN")
        self.assertIn(result["status"], CANDIDATES)
        self.assertFalse(FAIL_CLOSED.intersection(result.get("warnings", [])), result.get("warnings"))
        self.assertIsInstance(result["findings"], list)
        self.assertEqual([x["req_id"] for x in result["findings"]], ["REQ-001"])
        html = render_audit_html(result)
        self.assertIn("<html", html.lower())
        self.assertIn("not VERIFIED", html)
        manifest = save_artifacts(
            result, html, source_root=str(self.root), out_dir=str(self.out)
        )
        self.assertEqual(manifest["verification_status"], "NOT_RUN")
        for name in ("audit.json", "report.html", "manifest.json"):
            self.assertTrue((self.out / name).is_file(), name)
        saved = json.loads((self.out / "audit.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["source_sha"], "UNVERIFIED")
        self.assertEqual(saved["findings"][0]["req_id"], "REQ-001")

    def test_cli_success_duplicate_results_and_internal_write_rejected(self):
        command = [sys.executable, "-m", "reqea.cli", "audit",
                   "--repo", str(self.root), "--requirements", str(self.req),
                   "--out", str(self.out)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["verification_status"], "NOT_RUN")
        duplicate = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(duplicate.returncode, 2, duplicate.stderr)
        inside = command[:-1] + [str(self.root / "output")]
        denied = subprocess.run(inside, capture_output=True, text=True, timeout=20)
        self.assertEqual(denied.returncode, 2, denied.stderr)
        self.assertFalse((self.root / "output").exists())

    def test_invalid_req_ids_and_json_duplicates_rejected(self):
        manifest = parse_markdown_requirements(
            self.req.read_text(encoding="utf-8"),
            source_document="requirements.md"
        )
        self.assertEqual(manifest["requirements"][0]["req_id"], "REQ-001")
        self.assertIn("src/app.py", manifest["requirements"][0]["explicit_refs"])
        with self.assertRaises(ValueError):
            parse_markdown_requirements(
                "# REQ-001 - One\n# REQ-001 - Duplicate",
                source_document="requirements.md"
            )
        with self.assertRaises(ValueError):
            parse_json_requirements(
                '{"requirements":[{"req_id":"REQ-001","title":"A","title":"B"}]}',
                source_document="requirements.json"
            )
        valid = parse_json_requirements(
            '{"requirements":[{"req_id":"REQ-001","title":"A","acceptance_criteria":["X"],'
            '"explicit_refs":["src/app.py"]}]}',
            source_document="requirements.json"
        )
        self.assertEqual(valid["schema_version"], "reqea.v1")


if __name__ == "__main__":
    unittest.main()
