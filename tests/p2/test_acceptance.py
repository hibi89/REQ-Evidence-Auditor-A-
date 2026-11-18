"""P2 acceptance on synthetic-only local fixtures; no external/customer source."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from reqea.core.orchestrator import build_audit, render_audit_html
from reqea.core.output import save_artifacts
from reqea.core.requirements_md import parse_markdown_requirements
from reqea.core.requirements_json import parse_json_requirements
from reqea_codegraph import build_code_index
from reqea_evidence import evaluate, render_html


class P2SyntheticAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name)
        self.root = self.parent / "sample 한글 project"
        self.root.mkdir()
        (self.root / "src").mkdir()
        self.req = self.root / "requirements.md"
        self.out = self.parent / "out"

    def fixture(self, present=20, total=30):
        rows = ["| ID | 요구사항 / 핵심 수용 조건 | Owner |", "|---|---|---|"]
        for n in range(1, total + 1):
            name = "a%03d.py" % n
            rows.append("| REQ-%03d | static file exists src/%s | A |" % (n, name))
            if n <= present:
                (self.root / "src" / name).write_text("def marker():\n    return 1\n", encoding="utf-8")
        self.req.write_text("\n".join(rows) + "\n", encoding="utf-8")

    def test_canonical_blueprint_30_acceptance_criteria(self):
        doc = Path(__file__).resolve().parents[2] / "docs" / "FINAL_BLUEPRINT.md"
        manifest = parse_markdown_requirements(doc.read_text(encoding="utf-8"), source_document="docs/FINAL_BLUEPRINT.md")
        self.assertEqual([r["req_id"] for r in manifest["requirements"]], ["REQ-%03d" % i for i in range(1, 31)])
        self.assertTrue(all(r["acceptance_criteria"] for r in manifest["requirements"]))

    def test_30_true_false_candidate_cases(self):
        self.fixture()
        audit = build_audit(str(self.root), str(self.req))
        self.assertEqual([f["req_id"] for f in audit["findings"]], ["REQ-%03d" % i for i in range(1, 31)])
        self.assertEqual(audit["summary"]["code_candidates"], 20)
        self.assertEqual(audit["summary"]["gap_candidates"], 10)
        self.assertTrue(all(f["status"] != "VERIFIED" for f in audit["findings"]))
        self.assertEqual(audit["verification_status"], "NOT_RUN")

    def test_no_refs_never_certifies(self):
        self.req.write_text("# REQ-001 A\nAcceptance criteria:\n- human review\n", encoding="utf-8")
        result = build_audit(str(self.root), str(self.req))
        self.assertEqual(result["findings"][0]["status"], "UNASSESSED")

    def test_secret_not_emitted_and_source_unchanged(self):
        path = self.root / "src" / "a.py"
        path.write_text("def run():\n    return 'NEVER_PUBLISH_SECRET_12345'\n", encoding="utf-8")
        self.req.write_text("# REQ-001 A\nReference src/a.py\nAcceptance criteria:\n- file present\n", encoding="utf-8")
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        audit = build_audit(str(self.root), str(self.req))
        html = render_audit_html(audit)
        save_artifacts(audit, html, source_root=str(self.root), out_dir=str(self.out))
        self.assertNotIn("NEVER_PUBLISH_SECRET_12345", json.dumps(audit) + html)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_output_inside_root_denied_and_exclusive(self):
        self.fixture(1, 1)
        audit = build_audit(str(self.root), str(self.req))
        html = render_audit_html(audit)
        with self.assertRaises(ValueError):
            save_artifacts(audit, html, source_root=str(self.root), out_dir=str(self.root / "bad"))
        save_artifacts(audit, html, source_root=str(self.root), out_dir=str(self.out))
        with self.assertRaises(FileExistsError):
            save_artifacts(audit, html, source_root=str(self.root), out_dir=str(self.out))

    def test_html_escaping_and_no_executable_script(self):
        audit = {"schema_version": "reqea.v1", "source_sha": "UNVERIFIED", "status": "UNASSESSED",
                 "findings": [{"req_id": "REQ-001", "status": "UNASSESSED",
                               "rationale": "<script>alert(1)</script>",
                               "evidence": [{"path": "../<script>.py", "symbol": "<img>", "line": 1}],
                               "acceptance_criteria": [{"criterion": "<script>", "status": "UNASSESSED"}],
                               "warnings": []}], "warnings": [], "summary": {}}
        html = render_html(audit)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img>", html)
        self.assertIn("Content-Security-Policy", html)

    def test_symlink_input_rejected(self):
        self.fixture(1, 1)
        link = self.parent / "linked"
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("OS disallows creating symlinks")
        with self.assertRaises(ValueError):
            build_audit(str(link), str(self.req))

    def test_duplicate_requirement_rejected(self):
        with self.assertRaises(ValueError):
            parse_markdown_requirements("# REQ-001 A\n# REQ-001 B", source_document="requirements.md")
        with self.assertRaises(ValueError):
            parse_json_requirements('{"requirements":[{"req_id":"REQ-001","title":"A","title":"B"}]}',
                                    source_document="requirements.json")

    def test_b_determinism_and_truncation_blocks_gap(self):
        self.fixture(3, 3)
        a = build_code_index(str(self.root), {"max_files": 100})
        b = build_code_index(str(self.root), {"max_files": 100})
        self.assertEqual(a, b)
        limited = build_code_index(str(self.root), {"max_files": 1})
        self.assertTrue(limited["limits"]["truncated"])
        manifest = parse_markdown_requirements(self.req.read_text(encoding="utf-8"),
                                               source_document="requirements.md")
        manifest.pop("policy_sha", None)  # reqea.v1 C accepts only 40-hex when present
        out = evaluate(manifest, limited, {})
        self.assertNotIn("GAP_CANDIDATE", [f["status"] for f in out["findings"]])

    def test_cli_return_codes_and_unicode_path(self):
        self.fixture(1, 1)
        cmd = [sys.executable, "-m", "reqea.cli", "audit", "--repo", str(self.root),
               "--requirements", str(self.req), "--out", str(self.out)]
        first = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["verification_status"], "NOT_RUN")
        second = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        self.assertEqual(second.returncode, 2)
        denied = subprocess.run(cmd[:-1] + [str(self.root / "nested")],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(denied.returncode, 2)
        self.assertFalse((self.root / "nested").exists())

    def test_gui_import_smoke_not_live_desktop(self):
        import reqea.gui.app
        self.assertTrue(callable(reqea.gui.app.main))


if __name__ == "__main__":
    unittest.main()
