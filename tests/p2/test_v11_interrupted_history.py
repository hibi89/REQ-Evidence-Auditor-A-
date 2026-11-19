"""P2 actual subprocess crash between fsync of staging and committed hardlink.

Ensures still-valid local records remain readable, without deleting or
trusting the abandoned staging file. Synthetic project only, no customer data.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from reqea.core.history import compare_audits, load_deltas, load_projects, register_project, save_delta


def _audit(state: str) -> dict:
    return {
        "schema_version": "reqea.v1", "source_sha": "UNVERIFIED",
        "verification_status": "NOT_RUN",
        "warnings": [],
        "findings": [{"req_id": "REQ-001", "status": state, "evidence": []}],
    }


# The real writer enters _append_json and is killed after fsync, before link.
# A machine power interruption leaves the same staging-file shape; this test
# does NOT claim to verify actual sudden hardware power loss.
_CHILD = r"""
import json, os, sys
from unittest.mock import patch
from reqea.core.history import register_project, save_delta
payload = json.loads(sys.argv[1])
with patch("reqea.core.history.os.link", side_effect=lambda *a, **k: os._exit(79)):
    if payload["operation"] == "history":
        save_delta(payload["delta"], out_dir=payload["out"], source_root=payload["root"])
    else:
        register_project(payload["profile"], out_dir=payload["out"])
raise AssertionError("forced death did not occur")
"""


def _crash(arguments: dict) -> None:
    process = subprocess.run(
        [sys.executable, "-c", _CHILD, json.dumps(arguments)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
        check=False,
    )
    if process.returncode != 79:
        raise AssertionError(
            "crash injection did not hit the staging-to-commit boundary: "
            + process.stderr[:500]
        )


class InterruptedHistoryRecovery(unittest.TestCase):
    def test_crashed_delta_writer_does_not_block_prior_or_future_history(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "source"
            root.mkdir()
            unchanged = root / "original.py"
            unchanged.write_bytes(b"OWNER_ORIGINAL_PRESERVE")
            out = base / "approved-out"
            earlier = compare_audits(_audit("UNASSESSED"), _audit("GAP_CANDIDATE"))
            newer = compare_audits(_audit("UNASSESSED"), _audit("CODE_CANDIDATE"))
            saved = save_delta(earlier, out_dir=str(out), source_root=str(root))
            original_record = Path(saved["file"]).read_bytes()
            _crash({"operation": "history", "delta": newer,
                    "out": str(out), "root": str(root)})
            folder = out / "reqea-history"
            staging = list(folder.glob(".reqea-pending-*"))
            self.assertEqual(len(staging), 1, "true abrupt-exit residue expected")
            self.assertEqual(len(load_deltas(out_dir=str(out))), 1)
            later = save_delta(newer, out_dir=str(out), source_root=str(root))
            self.assertEqual(later["status"], "SAVED")
            self.assertEqual(len(load_deltas(out_dir=str(out))), 2)
            self.assertEqual(Path(saved["file"]).read_bytes(), original_record)
            self.assertTrue(staging[0].exists(), "preserve crash evidence, no auto-delete")
            self.assertEqual(unchanged.read_bytes(), b"OWNER_ORIGINAL_PRESERVE")

    def test_crashed_project_writer_keeps_earlier_bookmarks_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "source"
            root.mkdir()
            out = base / "approved-out"
            prior = {"kind": "local", "source": str(root),
                     "requirements": "requirements.md"}
            new = {"kind": "github", "source": "https://github.com/openai/demo",
                   "ref": "main", "requirements": "docs/FINAL_BLUEPRINT.md"}
            earlier = register_project(prior, out_dir=str(out))
            earlier_bytes = Path(earlier["file"]).read_bytes()
            _crash({"operation": "project", "profile": new, "out": str(out)})
            folder = out / "reqea-projects"
            staging = list(folder.glob(".reqea-pending-*"))
            self.assertEqual(len(staging), 1)
            self.assertEqual(len(load_projects(out_dir=str(out))), 1)
            self.assertEqual(register_project(new, out_dir=str(out))["status"], "SAVED")
            self.assertEqual(len(load_projects(out_dir=str(out))), 2)
            self.assertEqual(Path(earlier["file"]).read_bytes(), earlier_bytes)
            self.assertTrue(staging[0].exists())

    def test_four_competing_processes_preserve_distinct_commits_and_deduplicate(self):
        """Real concurrent processes race on hardlink creation, not a mock lock."""
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "source"
            root.mkdir()
            sentinel = root / "immutable.py"
            sentinel.write_bytes(b"ORIGINAL")
            out = base / "approved"
            gate = base / "start"
            one = compare_audits(_audit("UNASSESSED"), _audit("CODE_CANDIDATE"))
            two = compare_audits(_audit("UNASSESSED"), _audit("GAP_CANDIDATE"))
            worker = r"""
import json, sys, time
from pathlib import Path
from reqea.core.history import save_delta
args=json.loads(sys.argv[1])
deadline=time.monotonic()+12
while not Path(args["gate"]).exists():
    if time.monotonic()>deadline:
        sys.exit(10)
    time.sleep(0.01)
r=save_delta(args["delta"],out_dir=args["out"],source_root=args["root"])
print(r["status"])
"""
            children = []
            for delta in (one, one, two, two):
                command = [sys.executable, "-c", worker, json.dumps({
                    "delta": delta, "out": str(out), "root": str(root), "gate": str(gate),
                })]
                children.append(subprocess.Popen(command, stdout=subprocess.PIPE,
                                                  stderr=subprocess.PIPE, text=True))
            gate.write_text("GO", encoding="ascii")
            for child in children:
                stdout, stderr = child.communicate(timeout=20)
                self.assertEqual(child.returncode, 0, stderr[:500])
                self.assertIn(stdout.strip(), ("SAVED", "EXISTS"))
            records = load_deltas(out_dir=str(out))
            self.assertEqual(len(records), 2, "both distinct reports must commit only once")
            self.assertEqual(sorted(r["changes"][0]["after"] for r in records),
                             ["CODE_CANDIDATE", "GAP_CANDIDATE"])
            self.assertEqual(sentinel.read_bytes(), b"ORIGINAL")
            self.assertFalse(list((out / "reqea-history").glob(".reqea-pending-*")))

    def test_unknown_and_malicious_staging_names_still_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            folder = out / "reqea-history"
            folder.mkdir()
            (folder / ".reqea-pending-invalid.extra").write_bytes(b"fake")
            with self.assertRaisesRegex(ValueError, "unexpected"):
                load_deltas(out_dir=str(out))
            (folder / ".reqea-pending-invalid.extra").unlink()
            outside = out / "external"
            outside.write_bytes(b"SAFE_EXTERNAL")
            try:
                (folder / ".reqea-pending-abcdefgh").symlink_to(outside)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(type(exc).__name__)
            with self.assertRaisesRegex(ValueError, "unsafe"):
                load_deltas(out_dir=str(out))
            self.assertEqual(outside.read_bytes(), b"SAFE_EXTERNAL")


if __name__ == "__main__":
    unittest.main()
