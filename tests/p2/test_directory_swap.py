"""P2 local adversarial path-swap: no redirect via replaced directory."""
from __future__ import annotations

import os
import stat
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reqea_codegraph.files import read_file
from reqea_codegraph.walk import scan_tree


class ReadDirectorySwapSafety(unittest.TestCase):
    @unittest.skipUnless(
        os.open in getattr(os, "supports_dir_fd", set())
        and hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW"),
        "POSIX no-follow directory handles required for race injection",
    )
    def test_parent_symlink_swap_during_leaf_open_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "selected-project"
            directory = root / "src"
            directory.mkdir(parents=True)
            source = directory / "app.py"
            original = b"def local_only(): return 42\\n"
            source.write_bytes(original)
            entry = next(e for e in scan_tree(str(root), {}).files if e.path == "src/app.py")
            relocated = base / "moved-source-original"
            real_open = os.open
            switched = False

            def swap_before_leaf(path, flags, *args, **kwargs):
                nonlocal switched
                if not switched and str(path) == "app.py" and kwargs.get("dir_fd") is not None:
                    switched = True
                    directory.rename(relocated)
                    directory.symlink_to(relocated, target_is_directory=True)
                return real_open(path, flags, *args, **kwargs)

            with patch("reqea_codegraph.files.os.open", side_effect=swap_before_leaf):
                with self.assertRaisesRegex(ValueError, "symlink_or_reparse_disallowed"):
                    read_file(root, entry, 2_000_000)
            self.assertTrue(switched, "synthetic swap was not triggered")
            self.assertEqual((relocated / "app.py").read_bytes(), original)
            self.assertTrue(directory.is_symlink())

    @unittest.skipUnless(os.name == "nt", "Windows-only junction and Win32 handle test")
    def test_windows_junction_swap_cannot_read_file_moved_outside_root(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "selected"
            directory = root / "src"
            directory.mkdir(parents=True)
            source = directory / "app.py"
            original = b"def original(): return 42\\n"
            source.write_bytes(original)
            entry = next(e for e in scan_tree(str(root), {}).files if e.path == "src/app.py")
            moved = base / "original-moved-outside"
            real_open = os.open
            switched = False

            def switch_during_open(path, flags, *args, **kwargs):
                nonlocal switched
                if not switched and str(path).endswith("app.py"):
                    switched = True
                    directory.rename(moved)
                    mk = subprocess.run(["cmd", "/c", "mklink", "/J",
                                         str(directory), str(moved)],
                                        capture_output=True, text=True, timeout=15)
                    if mk.returncode:
                        raise RuntimeError("synthetic junction creation failed: " + mk.stderr)
                return real_open(path, flags, *args, **kwargs)

            with patch("reqea_codegraph.files.os.open", side_effect=switch_during_open):
                with patch("reqea_codegraph.files.os.fdopen", side_effect=AssertionError(
                    "out-of-tree file contents were read before Win32 validation")) as read_probe:
                    with self.assertRaisesRegex(ValueError, "file_changed_or_unsafe"):
                        read_file(root, entry, 2000000)
                    read_probe.assert_not_called()
            self.assertTrue(switched)
            self.assertEqual((moved / "app.py").read_bytes(), original)
            self.assertTrue(directory.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
            # Dispose only synthetic junction, never source contents.
            directory.rmdir()
            self.assertEqual((moved / "app.py").read_bytes(), original)

    def test_unchanged_path_still_indexable(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "sample.py").write_text("def present(): return True\\n", encoding="utf-8")
            entry = next(e for e in scan_tree(str(root), {}).files if e.path == "sample.py")
            item = read_file(root, entry, 2_000_000)
            self.assertEqual(item.record["path"], "sample.py")
            self.assertIn("present", item.text)


if __name__ == "__main__":
    unittest.main()
