"""P2 adversarial file-system safety cases using disposable synthetic fixtures."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reqea.core.orchestrator import build_audit
from reqea.core.output import save_artifacts
from reqea.core.source_ref import inspect_local_source
from reqea.core.requirements_md import parse_markdown_requirements
from reqea_codegraph import build_code_index
from reqea_evidence import evaluate


class P2SafetyEdges(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / "source"
        (self.root / "src").mkdir(parents=True)
        self.req = self.root / "REQ.md"
        self.req.write_text(
            "# REQ-001 - synthetic evidence\nSource src/app.py\n"
            "Acceptance criteria:\n- source available\n", encoding="utf-8")
        self.source = self.root / "src" / "app.py"
        self.source.write_bytes(b"def run():\n    return 1\n")

    def test_hardlinked_source_is_not_a_trustworthy_missing_code_gap(self):
        alias = self.base / "hardlink-target.py"
        try:
            os.link(self.source, alias)
        except OSError as exc:
            self.skipTest("hardlink unavailable: " + type(exc).__name__)
        index = build_code_index(str(self.root), {})
        self.assertFalse(any(f["path"] == "src/app.py" for f in index["files"]))
        self.assertGreater(index["limits"]["skipped_files"], 0)
        manifest = parse_markdown_requirements(self.req.read_text(encoding="utf-8"),
                                               source_document="REQ.md")
        manifest.pop("policy_sha", None)
        audit = evaluate(manifest, index, {})
        self.assertEqual(audit["findings"][0]["status"], "UNASSESSED")

    def test_hardlinked_requirement_outside_source_root_refused(self):
        outside = self.base / "external-policy.json"
        outside.write_text('{"requirements":[]}', encoding="utf-8")
        try:
            os.link(outside, self.root / "hardlinked.json")
        except OSError as exc:
            self.skipTest("hardlink unavailable: " + type(exc).__name__)
        with self.assertRaises(ValueError):
            inspect_local_source(str(self.root), str(self.root / "hardlinked.json"))

    def test_source_file_permission_error_isolated_and_report_incomplete(self):
        original = self.source.read_bytes()
        original_open = os.open
        def deny_python_only(path, flags, *args, **kwargs):
            if str(path).endswith("app.py"):
                raise PermissionError("synthetic")
            return original_open(path, flags, *args, **kwargs)
        with patch("reqea_codegraph.files.os.open", side_effect=deny_python_only):
            index = build_code_index(str(self.root), {})
        self.assertTrue(index["limits"]["truncated"])
        self.assertEqual(index["limits"]["scanned_files"], 1)  # the REQ file remains readable
        self.assertTrue(any("file_unreadable" in w for w in index["warnings"]))
        self.assertEqual(original, self.source.read_bytes())

    def test_symlinked_source_file_never_indexed(self):
        outside = self.base / "secret.py"
        outside.write_text("secret='SECRET_CANARY_123'\n", encoding="utf-8")
        link = self.root / "src" / "link.py"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlinks unavailable: " + type(exc).__name__)
        index = build_code_index(str(self.root), {})
        self.assertNotIn("src/link.py", [x["path"] for x in index["files"]])
        self.assertNotIn("SECRET_CANARY_123", json.dumps(index))
        self.assertTrue(any("link_skipped" in w for w in index["warnings"]))

    def test_requirement_inode_swap_before_open_fails_closed(self):
        """Swap same-sized input to a different inode after initial validation."""
        from reqea.core import source_ref
        original_open = os.open
        swapped = False
        replacement = self.root / "replacement.md"
        content = self.req.read_bytes()
        replacement.write_bytes(b"Z" * len(content))
        def swap_before_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if not swapped and Path(path) == self.req:
                swapped = True
                os.replace(replacement, self.req)
            return original_open(path, flags, *args, **kwargs)
        with patch.object(source_ref.os, "open", side_effect=swap_before_open):
            with self.assertRaises(ValueError):
                build_audit(str(self.root), str(self.req))
        self.assertTrue(swapped)

    def test_requirement_read_only_same_inode_is_stable(self):
        from reqea.core.source_ref import read_checked_requirements
        info = inspect_local_source(str(self.root), str(self.req))
        self.assertEqual(read_checked_requirements(info), self.req.read_bytes())

    def test_requirements_path_outside_root_is_rejected(self):
        outside = self.base / "outside.md"
        outside.write_text("# REQ-002 - external\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            inspect_local_source(str(self.root), str(outside))

    def test_existing_output_symlink_is_rejected_without_modification(self):
        from reqea.core.orchestrator import render_audit_html
        audit = build_audit(str(self.root), str(self.req))
        dest = self.base / "untouched"
        dest.mkdir()
        link = self.base / "linked-output"
        try:
            link.symlink_to(dest, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlinks unavailable: " + type(exc).__name__)
        with self.assertRaises(ValueError):
            save_artifacts(audit, render_audit_html(audit), source_root=str(self.root),
                           out_dir=str(link))
        self.assertEqual(list(dest.iterdir()), [])

    def test_unc_source_explicitly_denied(self):
        if sys.platform != "win32":
            self.skipTest("Windows-only UNC path")
        with self.assertRaises(ValueError):
            inspect_local_source(r"\\untrusted-host\private\repo", str(self.req))
        with self.assertRaises(ValueError):
            build_code_index(r"\\untrusted-host\private\repo", {})

    def test_windows_junction_requirements_path_is_denied(self):
        if sys.platform != "win32":
            self.skipTest("Windows-only junction")
        outside = self.base / "outside-folder"
        outside.mkdir()
        (outside / "copied.md").write_text("# REQ-001 fake\n", encoding="utf-8")
        junction = self.root / "junction"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            self.skipTest("Junction creation unavailable")
        with self.assertRaises(ValueError):
            inspect_local_source(str(self.root), str(junction / "copied.md"))

    def test_long_unicode_relative_source_paths(self):
        deep = self.root / "src"
        try:
            for n in range(9):
                deep = deep / ("한글_선택경로_" + str(n) + "_" + "a" * 20)
                deep.mkdir()
            file = deep / "long.py"
            file.write_bytes(b"def ok(): return 1\n")
        except OSError as exc:
            self.skipTest("Runner long paths unavailable: " + type(exc).__name__)
        index = build_code_index(str(self.root), {"max_depth": 32})
        relative = file.relative_to(self.root).as_posix()
        self.assertGreater(len(str(file)), 260)
        self.assertIn(relative, [f["path"] for f in index["files"]])


if __name__ == "__main__":
    unittest.main()
