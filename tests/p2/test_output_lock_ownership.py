"""P2 output lock ownership cannot be stolen or cleaned up by a peer."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reqea.core.orchestrator import build_audit, render_audit_html
from reqea.core.output import save_artifacts


class OutputLockOwnership(unittest.TestCase):
    def _fixture(self, base: Path):
        root = base / "source"
        root.mkdir()
        (root / "app.py").write_bytes(b"def run(): return 1\n")
        req = root / "REQ.md"
        req.write_text("# REQ-001 synthetic\nReference app.py\nAcceptance criteria:\n- present\n", encoding="utf-8")
        audit = build_audit(str(root), str(req))
        return root, base / "out", audit, render_audit_html(audit)

    def test_no_clobber_does_not_delete_replacement_lock_after_theft(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root, out, audit, html = self._fixture(base)
            out.mkdir()
            unrelated = out / "keep.txt"
            unrelated.write_bytes(b"UNCHANGED")
            original_lock = base / "original-lock"
            real_link = os.link
            stolen = False

            def steal_after_first(src, dst, *args, **kwargs):
                nonlocal stolen
                result = real_link(src, dst, *args, **kwargs)
                if Path(dst).name == "audit.json" and not stolen:
                    stolen = True
                    (out / ".reqea-transaction.lock").rename(original_lock)
                    (out / ".reqea-transaction.lock").mkdir()
                return result

            with patch("reqea.core.output.os.link", side_effect=steal_after_first):
                with self.assertRaisesRegex(ValueError, "lock ownership lost"):
                    save_artifacts(audit, html, source_root=str(root), out_dir=str(out))
            self.assertTrue(stolen)
            self.assertTrue(original_lock.is_dir())
            self.assertTrue((out / ".reqea-transaction.lock").is_dir())
            self.assertEqual(unrelated.read_bytes(), b"UNCHANGED")
            self.assertTrue((out / "audit.json").is_file())
            with self.assertRaises(FileExistsError):
                save_artifacts(audit, html, source_root=str(root), out_dir=str(out), overwrite=True)

    def test_overwrite_preserves_prior_backup_after_lock_theft(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root, out, audit, html = self._fixture(base)
            save_artifacts(audit, html, source_root=str(root), out_dir=str(out))
            original = (out / "audit.json").read_bytes()
            other = (out / "report.html").read_bytes()
            altered = dict(audit, tool_version="SYNTHETIC_CHANGED")
            saved_lock = base / "original-lock"
            real_replace = os.replace
            stolen = False

            def steal_after_first(src, dst, *args, **kwargs):
                nonlocal stolen
                result = real_replace(src, dst, *args, **kwargs)
                if Path(dst).name == "audit.json" and not stolen:
                    stolen = True
                    (out / ".reqea-transaction.lock").rename(saved_lock)
                    (out / ".reqea-transaction.lock").mkdir()
                return result

            with patch("reqea.core.output.os.replace", side_effect=steal_after_first):
                with self.assertRaisesRegex(ValueError, "lock ownership lost"):
                    save_artifacts(altered, html, source_root=str(root), out_dir=str(out), overwrite=True)
            self.assertTrue(stolen)
            self.assertTrue(saved_lock.is_dir())
            self.assertTrue((out / ".reqea-transaction.lock").is_dir())
            self.assertEqual((out / "report.html").read_bytes(), other)
            backups = [p.read_bytes() for p in out.iterdir() if p.name.startswith(".reqea-prev-")]
            self.assertIn(original, backups)
            with self.assertRaises(FileExistsError):
                save_artifacts(altered, html, source_root=str(root), out_dir=str(out), overwrite=True)


if __name__ == "__main__":
    unittest.main()
