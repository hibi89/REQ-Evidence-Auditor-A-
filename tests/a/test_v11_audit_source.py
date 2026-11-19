"""V1.1 A-11 CLI caller -> canonical -> A/B/C -> local-only artifacts."""
from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reqea.cli import main


def _make(root: Path, *, second: bool = False) -> None:
    (root / "docs").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "unit.py").write_text("def unit(): return 1\n", encoding="utf-8")
    (root / "docs" / "FINAL_BLUEPRINT.md").write_text(
        "# REQ-001 scan\nReference src/unit.py\nAcceptance criteria:\n- exists\n",
        encoding="utf-8",
    )
    if second:
        (root / "docs" / "FINAL_BLUEPRINT_V11.md").write_text(
            "# REQ-031 scan extension\nAcceptance criteria:\n- source appears\n",
            encoding="utf-8",
        )


def _call(*args: str) -> tuple[int, dict]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        result = main(list(args))
    payload = json.loads(stdout.getvalue() if stdout.getvalue() else stderr.getvalue())
    return result, payload


class CallerToCalleeSourceAudit(unittest.TestCase):
    def test_approved_local_auto_candidate_to_v1_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root, out = base / "repo", base / "out"
            root.mkdir()
            _make(root)
            rc, data = _call("audit-source", "--repo", str(root), "--out", str(out))
            self.assertEqual(rc, 0)
            self.assertEqual(data["canonical_document"], "docs/FINAL_BLUEPRINT.md")
            self.assertEqual(data["verification_status"], "NOT_RUN")
            saved = json.loads((out / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["schema_version"], "reqea.v1")
            self.assertEqual([x["req_id"] for x in saved["findings"]], ["REQ-001"])
            self.assertNotEqual(saved["status"], "VERIFIED")
            rc2, denied = _call("audit-source", "--repo", str(root), "--out", str(out))
            self.assertEqual(rc2, 2, denied)
            self.assertTrue((out / "manifest.json").exists())

    def test_ambiguous_requires_explicit_document_and_stale_path_denied(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root, out = base / "repo", base / "out"
            root.mkdir()
            _make(root, second=True)
            rc, result = _call("audit-source", "--repo", str(root), "--out", str(out))
            self.assertEqual(rc, 2, result)
            self.assertFalse(out.exists(), "ambiguous choice must not save files")
            selected = "docs/FINAL_BLUEPRINT_V11.md"
            rc, data = _call("audit-source", "--repo", str(root),
                             "--requirements", selected, "--out", str(out))
            self.assertEqual(rc, 0, data)
            self.assertEqual(data["canonical_document"], selected)
            self.assertEqual(json.loads((out / "audit.json").read_text())["findings"][0]["req_id"],
                             "REQ-031")

    def test_github_snapshot_pinned_sha_distinguished_from_verified_source(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root, out = base / "synthetic-gh", base / "report"
            root.mkdir()
            _make(root)

            @contextmanager
            def fake_public(url: str, ref: str | None = None):
                self.assertEqual(url, "https://github.com/example/example")
                self.assertEqual(ref, "feature/branch")
                yield {"root": str(root), "owner": "example", "repository": "example",
                       "commit_sha": "a" * 40, "tree_sha": "b" * 40,
                       "source_sha": "UNVERIFIED"}

            with patch("reqea.cli.public_github_snapshot", side_effect=fake_public):
                rc, result = _call("audit-source", "--github-url",
                                   "https://github.com/example/example",
                                   "--ref", "feature/branch", "--out", str(out))
            self.assertEqual(rc, 0, result)
            self.assertEqual(result["pinned_commit_sha"], "a" * 40)
            self.assertEqual(result["source_sha"], "UNVERIFIED")
            self.assertEqual(result["verification_status"], "NOT_RUN")
            self.assertEqual(json.loads((out / "manifest.json").read_text())["source_sha"],
                             "UNVERIFIED")

    def test_ref_on_local_root_and_output_inside_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            _make(root)
            rc, err = _call("audit-source", "--repo", str(root), "--ref", "main",
                            "--out", str(Path(d) / "out"))
            self.assertEqual(rc, 2, err)
            rc2, err2 = _call("audit-source", "--repo", str(root),
                             "--out", str(root / "unsafe-output"))
            self.assertEqual(rc2, 2, err2)
            self.assertFalse((root / "unsafe-output").exists())


if __name__ == "__main__":
    unittest.main()
