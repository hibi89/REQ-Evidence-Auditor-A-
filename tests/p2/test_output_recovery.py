"""Deterministic output recovery on a partially failed local no-clobber write."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reqea.core.orchestrator import build_audit, render_audit_html
from reqea.core.output import save_artifacts


class OutputRecovery(unittest.TestCase):
    def test_injected_second_link_failure_rolls_back_only_owned_files(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "source"
            (root / "src").mkdir(parents=True)
            (root / "src" / "unit.py").write_bytes(b"def unit(): return 1\n")
            req = root / "REQ.md"
            req.write_text("# REQ-001 local\nReference src/unit.py\nAcceptance criteria:\n- exists\n",
                           encoding="utf-8")
            audit = build_audit(str(root), str(req))
            html = render_audit_html(audit)
            out = base / "out"
            out.mkdir()
            marker = out / "other-user-document.txt"
            marker.write_bytes(b"PRESERVE_ME")
            real_link = os.link
            def fail_second(src, dst, *args, **kwargs):
                if Path(dst).name == "report.html":
                    raise PermissionError("simulated second-link filesystem failure")
                return real_link(src, dst, *args, **kwargs)
            with patch("reqea.core.output.os.link", side_effect=fail_second):
                with self.assertRaises(PermissionError):
                    save_artifacts(audit, html, source_root=str(root), out_dir=str(out))
            self.assertEqual(marker.read_bytes(), b"PRESERVE_ME")
            self.assertEqual(sorted(p.name for p in out.iterdir()), [marker.name])
            result = save_artifacts(audit, html, source_root=str(root), out_dir=str(out))
            self.assertEqual(result["artifacts"], ["audit.json", "manifest.json", "report.html"])
            self.assertTrue((out / "manifest.json").is_file())
            self.assertEqual(marker.read_bytes(), b"PRESERVE_ME")


    def test_overwrite_failure_restores_all_existing_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "source"
            (root / "src").mkdir(parents=True)
            (root / "src" / "unit.py").write_bytes(b"def unit(): return 1\n")
            req = root / "REQ.md"
            req.write_text("# REQ-001 local\nReference src/unit.py\nAcceptance criteria:\n- exists\n",
                           encoding="utf-8")
            audit = build_audit(str(root), str(req))
            html = render_audit_html(audit)
            out = base / "out"
            save_artifacts(audit, html, source_root=str(root), out_dir=str(out))
            originals = {p.name: p.read_bytes() for p in out.iterdir()}
            altered = dict(audit)
            altered["tool_version"] = "P2_SYNTHETIC_REPLACEMENT"
            real_replace = os.replace
            called = 0
            def fail_second(src, dst, *args, **kwargs):
                nonlocal called
                if Path(dst).name in originals:
                    called += 1
                    if called == 2:
                        raise PermissionError("synthetic second replace error")
                return real_replace(src, dst, *args, **kwargs)
            with patch("reqea.core.output.os.replace", side_effect=fail_second):
                with self.assertRaises(PermissionError):
                    save_artifacts(altered, html, source_root=str(root), out_dir=str(out),
                                   overwrite=True)
            self.assertEqual({p.name: p.read_bytes() for p in out.iterdir()}, originals)
            save_artifacts(altered, html, source_root=str(root), out_dir=str(out),
                           overwrite=True)
            self.assertNotEqual((out / "audit.json").read_bytes(), originals["audit.json"])

    def test_failed_rollback_retains_original_backup_for_manual_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "source"
            root.mkdir()
            req = root / "REQ.md"
            req.write_text("# REQ-001 synthetic\n", encoding="utf-8")
            audit = build_audit(str(root), str(req))
            html = render_audit_html(audit)
            out = base / "out"
            save_artifacts(audit, html, source_root=str(root), out_dir=str(out))
            original = (out / "audit.json").read_bytes()
            changed = dict(audit)
            changed["tool_version"] = "SYNTHETIC_OVERWRITE"
            real_replace = os.replace
            installed_count = 0
            def fail_update_and_rollback(src, dst, *args, **kwargs):
                nonlocal installed_count
                if Path(dst).name in {"audit.json", "report.html", "manifest.json"}:
                    if Path(src).name.startswith(".reqea-prev-"):
                        raise PermissionError("synthetic failed restore")
                    installed_count += 1
                    if installed_count == 2:
                        raise PermissionError("synthetic update failure")
                return real_replace(src, dst, *args, **kwargs)
            with patch("reqea.core.output.os.replace", side_effect=fail_update_and_rollback):
                with self.assertRaises(PermissionError):
                    save_artifacts(changed, html, source_root=str(root),
                                   out_dir=str(out), overwrite=True)
            backups = [p for p in out.iterdir() if p.name.startswith(".reqea-prev-")]
            self.assertTrue(backups, "original backup must survive failed rollback")
            self.assertIn(original, [p.read_bytes() for p in backups])
            self.assertFalse(any(p.name.startswith(".reqea-new-") for p in out.iterdir()))

    def test_overwrite_refuses_existing_symlink_output(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "source"
            root.mkdir()
            req = root / "REQ.md"
            req.write_text("# REQ-001 synthetic\n", encoding="utf-8")
            audit = build_audit(str(root), str(req))
            html = render_audit_html(audit)
            out = base / "out"
            out.mkdir()
            outside = base / "unrelated-user-data.json"
            outside.write_bytes(b"PROTECTED")
            try:
                (out / "audit.json").symlink_to(outside)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(type(exc).__name__)
            with self.assertRaises(ValueError):
                save_artifacts(audit, html, source_root=str(root), out_dir=str(out),
                               overwrite=True)
            self.assertEqual(outside.read_bytes(), b"PROTECTED")


    def test_interrupted_transaction_sentinel_blocks_any_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "source"
            root.mkdir()
            req = root / "REQ.md"
            req.write_text("# REQ-001 synthetic\\n", encoding="utf-8")
            audit = build_audit(str(root), str(req))
            html = render_audit_html(audit)
            out = base / "out"
            save_artifacts(audit, html, source_root=str(root), out_dir=str(out))
            self.assertFalse((out / ".reqea-transaction.lock").exists())
            original = {p.name: p.read_bytes() for p in out.iterdir()}
            lock = out / ".reqea-transaction.lock"
            lock.mkdir()  # Represents a still-active or killed process.
            changed = dict(audit, tool_version="ANOTHER_WRITER")
            with self.assertRaisesRegex(FileExistsError, "transaction"):
                save_artifacts(changed, html, source_root=str(root),
                               out_dir=str(out), overwrite=True)
            self.assertEqual({p.name: p.read_bytes() for p in out.iterdir()
                              if p.is_file()}, original)
            self.assertTrue(lock.is_dir(), "never remove an unowned lock")

    def test_unrecovered_backup_blocks_retry_and_keeps_original_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "source"
            root.mkdir()
            req = root / "REQ.md"
            req.write_text("# REQ-001 synthetic\\n", encoding="utf-8")
            audit = build_audit(str(root), str(req))
            html = render_audit_html(audit)
            out = base / "out"
            save_artifacts(audit, html, source_root=str(root), out_dir=str(out))
            backup = out / ".reqea-prev-recovery-evidence"
            backup.write_bytes(b"KEEP_UNVERIFIED_RECOVERY_BYTES")
            originals = {p.name: p.read_bytes() for p in out.iterdir()}
            with self.assertRaisesRegex(FileExistsError, "unrecovered"):
                save_artifacts(dict(audit, tool_version="MUST_NOT_REPLACE"),
                               html, source_root=str(root), out_dir=str(out),
                               overwrite=True)
            self.assertEqual({p.name: p.read_bytes() for p in out.iterdir()}, originals)
            self.assertFalse((out / ".reqea-transaction.lock").exists())

    def test_injected_failure_does_not_leave_transaction_lock(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "source"
            root.mkdir()
            req = root / "REQ.md"
            req.write_text("# REQ-001 synthetic\\n", encoding="utf-8")
            audit = build_audit(str(root), str(req))
            html = render_audit_html(audit)
            out = base / "out"
            real_link = os.link
            def fail_second(src, dst, *args, **kwargs):
                if Path(dst).name == "report.html":
                    raise PermissionError("synthetic second-artifact failure")
                return real_link(src, dst, *args, **kwargs)
            with patch("reqea.core.output.os.link", side_effect=fail_second):
                with self.assertRaises(PermissionError):
                    save_artifacts(audit, html, source_root=str(root), out_dir=str(out))
            self.assertFalse((out / ".reqea-transaction.lock").exists())
            self.assertEqual(list(out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
