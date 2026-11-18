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


if __name__ == "__main__":
    unittest.main()
