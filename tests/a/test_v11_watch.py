"""A-12/A-13 foreground local/GitHub change-watch synthetic code paths."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reqea.core.watch import LocalChangeWatch, PublicGitHubChangeWatch


def _project(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("def f(): return 1\n", encoding="utf-8")
    requirements = root / "requirements.md"
    requirements.write_text("# REQ-001 audit\nReference src/app.py\nAcceptance criteria:\n- exists\n",
                            encoding="utf-8")
    return requirements


class ChangeWatchSynthetic(unittest.TestCase):
    def test_local_explicit_start_change_debounce_and_stop(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            req = _project(root)
            watcher = LocalChangeWatch(str(root), str(req))
            self.assertEqual(watcher.tick(now=0)["status"], "STOPPED")
            self.assertEqual(watcher.start(now=0)["status"], "STARTED")
            self.assertEqual(watcher.tick(now=10)["status"], "WAIT")
            self.assertEqual(watcher.tick(now=30)["status"], "UNCHANGED")
            src = root / "src" / "app.py"
            src.write_text("def f(): return 2\n", encoding="utf-8")
            self.assertEqual(watcher.tick(now=60)["status"], "DEBOUNCING")
            changed = watcher.tick(now=90)
            self.assertEqual(changed["status"], "CHANGED")
            self.assertEqual(changed["verification_status"], "NOT_RUN")
            self.assertNotIn("VERIFIED", [f["status"] for f in changed["current"]["findings"]])
            self.assertEqual(watcher.tick(now=120)["status"], "UNCHANGED")
            self.assertEqual(watcher.stop()["status"], "STOPPED")
            self.assertEqual(watcher.tick(now=999)["status"], "STOPPED")

    def test_local_canonical_mutation_pauses_without_replacing_audit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            req = _project(root)
            watcher = LocalChangeWatch(str(root), str(req))
            watcher.start(now=0)
            req.write_text("# REQ-001 altered\nAcceptance criteria:\n- changed\n", encoding="utf-8")
            self.assertEqual(watcher.tick(now=30)["status"], "PAUSED")
            self.assertFalse(watcher.active)

    def test_remote_pins_exact_new_commit_and_does_not_poll_before_15m(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "public"
            _project(root)
            a, b = "a" * 40, "b" * 40
            calls: list[str | None] = []

            @contextmanager
            def fake_snapshot(url, ref):
                self.assertEqual(url, "https://github.com/o/r")
                calls.append(ref)
                yield {"root": str(root), "owner": "o", "repository": "r",
                       "commit_sha": b if ref == b else a, "source_sha": "UNVERIFIED"}

            watcher = PublicGitHubChangeWatch("https://github.com/o/r", "main",
                                               "requirements.md")
            self.assertEqual(watcher.tick(now=0)["status"], "STOPPED")
            with patch("reqea.core.watch.public_github_snapshot", side_effect=fake_snapshot):
                self.assertEqual(watcher.start(now=0)["status"], "STARTED")
                with patch.object(watcher.reader, "head_commit_sha", return_value=b) as query:
                    self.assertEqual(watcher.tick(now=30)["status"], "WAIT")
                    query.assert_not_called()
                    (root / "src" / "app.py").write_text("def f(): return 2\n", encoding="utf-8")
                    outcome = watcher.tick(now=900)
            self.assertEqual(outcome["status"], "CHANGED")
            self.assertEqual(outcome["pinned_commit_sha"], b)
            self.assertEqual(outcome["source_sha"], "UNVERIFIED")
            self.assertEqual(calls, ["main", b])
            self.assertEqual(watcher.stop()["status"], "STOPPED")

    def test_remote_rate_limit_backs_off_then_stop(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "public"
            _project(root)

            @contextmanager
            def fake_snapshot(url, ref):
                yield {"root": str(root), "owner": "o", "repository": "r",
                       "commit_sha": "a" * 40, "source_sha": "UNVERIFIED"}

            watcher = PublicGitHubChangeWatch("https://github.com/o/r", "main",
                                               "requirements.md")
            with patch("reqea.core.watch.public_github_snapshot", side_effect=fake_snapshot):
                watcher.start(now=0)
            with patch.object(watcher.reader, "head_commit_sha",
                              side_effect=ValueError("GitHub rate limited or access denied")):
                result = watcher.tick(now=900)
            self.assertEqual(result["status"], "BACKOFF")
            self.assertGreaterEqual(result["retry_seconds"], 1800)
            self.assertEqual(watcher.tick(now=1800)["status"], "WAIT")
            watcher.stop()
            self.assertEqual(watcher.tick(now=20000)["status"], "STOPPED")


if __name__ == "__main__":
    unittest.main()
