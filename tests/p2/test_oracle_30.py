"""P2-01 fixed 30-REQ gold oracle, with partial and decoy false-positive controls.

The expected results live in a separate static fixture, never derived from the
auditor's observed output. Only synthetic local files are read.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from reqea.core.orchestrator import build_audit


ORACLE = Path(__file__).parent / "fixtures" / "oracle_30.json"


class GoldOracleAcceptance(unittest.TestCase):
    def _root(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "selected"
        (root / "src").mkdir(parents=True)
        return root

    def test_30_fixed_expectations_and_not_one_verified(self):
        gold = json.loads(ORACLE.read_text(encoding="utf-8"))
        self.assertEqual(gold["schema"], "reqea.p2.oracle.v1")
        cases = gold["cases"]
        self.assertEqual(len(cases), 30)
        root = self._root()
        lines = []
        for case in cases:
            lines.extend([
                "# " + case["req_id"] + " fixture",
                "Reference " + case["path"],
                "Acceptance criteria:",
                "- local source " + case["path"] + " present",
            ])
            if case["present"]:
                (root / case["path"]).write_text(
                    "def harmless(): return 42\\n", encoding="utf-8")
        (root / "src" / "req_0120.py").write_text("def decoy(): return 1\\n", encoding="utf-8")
        (root / "src" / "req_0290.py").write_text("def decoy(): return 1\\n", encoding="utf-8")
        req = root / "REQUIREMENTS.md"
        req.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
        report = build_audit(str(root), str(req))
        observed = {item["req_id"]: item["status"] for item in report["findings"]}
        fixed = {item["req_id"]: item["expected_status"] for item in cases}
        self.assertEqual(observed, fixed)
        self.assertEqual(sum(x["present"] for x in cases), 20)
        self.assertEqual(sum(not x["present"] for x in cases), 10)
        self.assertEqual(report["summary"]["code_candidates"], 20)
        self.assertEqual(report["summary"]["gap_candidates"], 10)
        self.assertTrue(all(x["status"] != "VERIFIED" for x in report["findings"]))
        self.assertEqual(report["verification_status"], "NOT_RUN")

    def test_partial_and_id_prefix_decoys_require_human_review(self):
        root = self._root()
        (root / "src" / "live.py").write_text("def live(): return True\\n", encoding="utf-8")
        (root / "src" / "req_0320.py").write_text("def decoy(): return True\\n", encoding="utf-8")
        req = root / "REQUIREMENTS.md"
        req.write_text(
            "# REQ-031 partial evidence\\n"
            "Reference src/live.py and src/missing.py\\n"
            "Acceptance criteria:\\n- both src/live.py and src/missing.py exist\\n"
            "# REQ-032 prefix collision\\n"
            "Acceptance criteria:\\n- inspect manually\\n"
            "# REQ-033 no reference\\n"
            "Acceptance criteria:\\n- human review\\n", encoding="utf-8")
        report = build_audit(str(root), str(req))
        observed = {x["req_id"]: x["status"] for x in report["findings"]}
        self.assertEqual(observed, {
            "REQ-031": "REVIEW_REQUIRED",
            "REQ-032": "UNASSESSED",
            "REQ-033": "UNASSESSED",
        })
        self.assertNotIn("VERIFIED", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
