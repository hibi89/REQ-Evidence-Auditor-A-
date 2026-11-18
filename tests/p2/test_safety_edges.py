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

    def test_requirement_inode_or_bytes_swap_before_read_fails_closed(self):
        """Same-sized replacement after inspection cannot be parsed as the old REQ."""
        from reqea.core.source_ref import read_checked_requirements
        original_bytes = self.req.read_bytes()
        inspected = inspect_local_source(str(self.root), str(self.req))
        replacement = self.root / "replacement.md"
        replacement.write_bytes(b"Z" * len(original_bytes))
        os.replace(replacement, self.req)
        with self.assertRaises(ValueError):
            read_checked_requirements(inspected)

    @unittest.skipUnless(
        os.name == "posix"
        and os.open in getattr(os, "supports_dir_fd", set())
        and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
        "POSIX no-follow ancestor handles required",
    )
    def test_posix_requirement_parent_swap_never_reads_outside_root(self):
        """A renamed parent replaced by a symlink must be blocked before fdopen."""
        from reqea.core.source_ref import inspect_local_source, read_checked_requirements
        folder = self.root / "nested"
        folder.mkdir()
        req = folder / "actual.md"
        payload = b"# REQ-001 synthetic\\nAcceptance criteria:\\n- local only\\n".replace(b"\\n", b"\n")
        req.write_bytes(payload)
        inspected = inspect_local_source(str(self.root), str(req))
        relocated = self.base / "moved-req-outside-root"
        original_open = os.open
        switched = False

        def swap_before_parent_or_leaf(path, flags, *args, **kwargs):
            nonlocal switched
            if (not switched and (
                (str(path) == "nested" and kwargs.get("dir_fd") is not None)
                or str(path) == str(req)
            )):
                switched = True
                folder.rename(relocated)
                folder.symlink_to(relocated, target_is_directory=True)
            return original_open(path, flags, *args, **kwargs)

        with patch("reqea.core.source_ref.os.open", side_effect=swap_before_parent_or_leaf):
            with patch("reqea.core.source_ref.os.fdopen",
                       side_effect=AssertionError("out-of-root requirement read")) as reader:
                with self.assertRaisesRegex(ValueError, "requirements could not be safely opened"):
                    read_checked_requirements(inspected)
                reader.assert_not_called()
        self.assertTrue(switched, "race injection must exercise the leaf open boundary")
        self.assertEqual((relocated / "actual.md").read_bytes(), payload)
        self.assertTrue(folder.is_symlink())

    @unittest.skipUnless(sys.platform == "win32", "Win32 junction handle check")
    def test_windows_requirement_swap_blocks_before_reading_external_inode(self):
        from reqea.core.source_ref import read_checked_requirements
        folder = self.root / "nested"
        folder.mkdir()
        req = folder / "actual.md"
        payload = b"# REQ-001 synthetic\nAcceptance criteria:\n- local only\n"
        req.write_bytes(payload)
        inspected = inspect_local_source(str(self.root), str(req))
        relocated = self.base / "outside-moved-source"
        original_open = os.open
        switched = False

        def switch_while_opening(path, flags, *args, **kwargs):
            nonlocal switched
            if not switched and str(path).endswith("actual.md"):
                switched = True
                folder.rename(relocated)
                mk = subprocess.run(["cmd", "/c", "mklink", "/J", str(folder), str(relocated)],
                                    capture_output=True, text=True, timeout=15)
                if mk.returncode:
                    raise RuntimeError("synthetic junction creation failed: " + mk.stderr)
            return original_open(path, flags, *args, **kwargs)

        with patch("reqea.core.source_ref.os.open", side_effect=switch_while_opening):
            with patch("reqea.core.source_ref.os.fdopen",
                       side_effect=AssertionError("external source read before handle check")) as opened:
                with self.assertRaisesRegex(ValueError, "requirements changed during open"):
                    read_checked_requirements(inspected)
                opened.assert_not_called()
        self.assertTrue(switched)
        self.assertEqual((relocated / "actual.md").read_bytes(), payload)
        self.assertTrue(folder.lstat().st_file_attributes & __import__("stat").FILE_ATTRIBUTE_REPARSE_POINT)
        folder.rmdir()

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
