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

    def test_stop_during_initial_local_start_cannot_rearm_watch(self):
        from reqea.core import watch as module
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            req = _project(root)
            watcher = LocalChangeWatch(str(root), str(req))
            original = module.build_audit

            def cancelled(*args, **kwargs):
                result = original(*args, **kwargs)
                watcher.stop()  # User closed the view during initial analysis.
                return result

            with patch.object(module, "build_audit", side_effect=cancelled):
                outcome = watcher.start(now=0)
            self.assertEqual(outcome["status"], "STOPPED")
            self.assertFalse(watcher.active)
            self.assertIsNone(watcher._audit)
            self.assertIsNone(watcher._fingerprint)
            self.assertEqual(watcher.tick(now=900)["status"], "STOPPED")

    def test_stop_during_initial_remote_start_cannot_rearm_watch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "public"
            _project(root)
            watcher = PublicGitHubChangeWatch(
                "https://github.com/o/r", "main", "requirements.md"
            )

            @contextmanager
            def interrupted_snapshot(url, ref):
                watcher.stop()  # STOP while a pinned HTTPS snapshot is loading.
                yield {"root": str(root), "owner": "o", "repository": "r",
                       "commit_sha": "a" * 40, "source_sha": "UNVERIFIED"}

            with patch("reqea.core.watch.public_github_snapshot",
                       side_effect=interrupted_snapshot):
                outcome = watcher.start(now=0)
            self.assertEqual(outcome["status"], "STOPPED")
            self.assertFalse(watcher.active)
            self.assertIsNone(watcher._head)
            self.assertIsNone(watcher._audit)
            self.assertEqual(watcher.tick(now=900)["status"], "STOPPED")

    def test_initial_source_mutation_during_audit_fails_closed(self):
        from reqea.core import watch as module
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"root"
            req=_project(root)
            watcher=LocalChangeWatch(str(root),str(req))
            original=module.build_audit
            def raced(*args,**kwargs):
                result=original(*args,**kwargs)
                (root/"src"/"app.py").write_text("def f(): return 99\n",encoding="utf-8")
                return result
            with patch.object(module,"build_audit",side_effect=raced):
                with self.assertRaisesRegex(ValueError,"source changed during initial audit"):
                    watcher.start(now=0)
            self.assertFalse(watcher.active)
            self.assertIsNone(watcher._audit)

    def test_changed_source_mid_rescan_pauses_without_replacing_audit(self):
        from reqea.core import watch as module
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"root"
            req=_project(root)
            watcher=LocalChangeWatch(str(root),str(req))
            watcher.start(now=0)
            baseline=watcher._audit
            file=root/"src"/"app.py"
            file.write_text("def f(): return 2\n",encoding="utf-8")
            self.assertEqual(watcher.tick(now=30)["status"],"DEBOUNCING")
            original=module.build_audit
            def raced(*args,**kwargs):
                result=original(*args,**kwargs)
                file.write_text("def f(): return 3\n",encoding="utf-8")
                return result
            with patch.object(module,"build_audit",side_effect=raced):
                state=watcher.tick(now=60)
            self.assertEqual(state["status"],"PAUSED")
            self.assertFalse(watcher.active)
            self.assertIs(watcher._audit,baseline)

    def test_explicit_stop_during_local_rescan_cancels_state_promotion(self):
        from reqea.core import watch as module
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"root"
            req=_project(root)
            watcher=LocalChangeWatch(str(root),str(req))
            watcher.start(now=0)
            original_audit=watcher._audit
            (root/"src"/"app.py").write_text("def f(): return 2\n",encoding="utf-8")
            self.assertEqual(watcher.tick(now=30)["status"],"DEBOUNCING")
            original=module.build_audit
            def stop_during_audit(*args,**kwargs):
                result=original(*args,**kwargs)
                watcher.stop()
                return result
            with patch.object(module,"build_audit",side_effect=stop_during_audit):
                state=watcher.tick(now=60)
            self.assertEqual(state["status"],"STOPPED")
            self.assertFalse(watcher.active)
            self.assertIs(watcher._audit,original_audit)

    def test_explicit_stop_during_remote_snapshot_cancels_state_promotion(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"remote"
            _project(root)
            old,new="a"*40,"b"*40
            watcher=PublicGitHubChangeWatch("https://github.com/o/r","main","requirements.md")
            @contextmanager
            def synthetic(url,ref):
                if ref==new:
                    watcher.stop()
                yield {"root":str(root),"commit_sha":new if ref==new else old,
                       "owner":"o","repository":"r","source_sha":"UNVERIFIED"}
            with patch("reqea.core.watch.public_github_snapshot",side_effect=synthetic):
                watcher.start(now=0)
                original_audit=watcher._audit
                with patch.object(watcher.reader,"head_commit_sha",return_value=new):
                    state=watcher.tick(now=900)
            self.assertEqual(state["status"],"STOPPED")
            self.assertEqual(watcher._head,old)
            self.assertIs(watcher._audit,original_audit)

    def test_48_hour_virtual_public_poll_does_not_exhaust_lifetime_request_budget(self):
        """192 real code-path polls at 15min intervals, with mocked HTTP only."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "public"
            _project(root)
            head = "a" * 40
            calls: list[str] = []
            @contextmanager
            def fake_snapshot(url, ref):
                self.assertEqual(url, "https://github.com/o/r")
                yield {"root": str(root), "owner": "o", "repository": "r",
                       "commit_sha": head, "source_sha": "UNVERIFIED"}
            def fake_api(path, *, cap=2_000_000):
                calls.append(path)
                if path.endswith("/o/r"):
                    return {"private": False, "full_name": "o/r", "default_branch": "main"}
                if path.endswith("/commits/main"):
                    return {"sha": head}
                raise AssertionError("unexpected GitHub poll URL")
            watcher = PublicGitHubChangeWatch(
                "https://github.com/o/r", "main", "requirements.md",
                interval_seconds=900,
            )
            with patch("reqea.core.watch.public_github_snapshot", side_effect=fake_snapshot):
                baseline = watcher.start(now=0)["audit"]
            with patch("reqea.core.github_source._json_get", side_effect=fake_api):
                for i in range(1, 193):  # 48h of simulated time, no wall-clock wait
                    self.assertEqual(
                        watcher.tick(now=900 * i)["status"], "UNCHANGED",
                        f"public watch unexpectedly stopped at virtual poll {i}",
                    )
            self.assertEqual(len(calls), 384, "two bounded GETs per poll, no blob downloads")
            self.assertTrue(watcher.active)
            self.assertIs(watcher._audit, baseline)
            self.assertEqual(watcher._head, head)
            self.assertEqual(watcher.stop()["status"], "STOPPED")

    def test_remote_access_denial_pauses_without_retrying(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "public"
            _project(root)

            @contextmanager
            def fake_snapshot(url, ref):
                yield {"root": str(root), "owner": "o", "repository": "r",
                       "commit_sha": "a" * 40, "source_sha": "UNVERIFIED"}

            watcher = PublicGitHubChangeWatch(
                "https://github.com/o/r", "main", "requirements.md"
            )
            with patch("reqea.core.watch.public_github_snapshot",
                       side_effect=fake_snapshot):
                self.assertEqual(watcher.start(now=0)["status"], "STARTED")
            with patch.object(watcher.reader, "head_commit_sha",
                              side_effect=ValueError("GitHub access denied")):
                result = watcher.tick(now=900)
            self.assertEqual(result["status"], "PAUSED")
            self.assertFalse(watcher.active)
            self.assertEqual(watcher.tick(now=100000)["status"], "STOPPED")

    def test_local_stop_during_unchanged_fingerprint_is_final(self):
        from reqea.core import watch as module
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            req = _project(root)
            watcher = LocalChangeWatch(str(root), str(req))
            watcher.start(now=0)
            old_audit = watcher._audit
            original = module._local_fingerprint

            def stop_after_read(*args, **kwargs):
                value = original(*args, **kwargs)
                watcher.stop()
                return value

            with patch.object(module, "_local_fingerprint", side_effect=stop_after_read):
                result = watcher.tick(now=30)
            self.assertEqual(result["status"], "STOPPED")
            self.assertFalse(watcher.active)
            self.assertIs(watcher._audit, old_audit)

    def test_local_stop_during_debounce_does_not_recreate_pending(self):
        from reqea.core import watch as module
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            req = _project(root)
            watcher = LocalChangeWatch(str(root), str(req))
            watcher.start(now=0)
            (root / "src" / "app.py").write_text("def f(): return 2\\n", encoding="utf-8")
            original = module._local_fingerprint

            def stop_after_read(*args, **kwargs):
                value = original(*args, **kwargs)
                watcher.stop()
                return value

            with patch.object(module, "_local_fingerprint", side_effect=stop_after_read):
                result = watcher.tick(now=30)
            self.assertEqual(result["status"], "STOPPED")
            self.assertFalse(watcher.active)
            self.assertIsNone(watcher._pending)

    def test_remote_stop_during_unchanged_ref_is_final(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "public"
            _project(root)
            head = "a" * 40

            @contextmanager
            def fake_snapshot(url, ref):
                yield {"root": str(root), "owner": "o", "repository": "r",
                       "commit_sha": head, "source_sha": "UNVERIFIED"}

            watcher = PublicGitHubChangeWatch("https://github.com/o/r",
                                               "main", "requirements.md")
            with patch("reqea.core.watch.public_github_snapshot",
                       side_effect=fake_snapshot):
                watcher.start(now=0)
            previous = watcher._audit

            def stop_during_ref():
                watcher.stop()
                return head

            with patch.object(watcher.reader, "head_commit_sha",
                              side_effect=stop_during_ref):
                result = watcher.tick(now=900)
            self.assertEqual(result["status"], "STOPPED")
            self.assertFalse(watcher.active)
            self.assertIs(watcher._audit, previous)

    def test_overlapping_local_tick_is_single_flight(self):
        from reqea.core import watch as module
        from threading import Event, Thread
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            req = _project(root)
            watcher = LocalChangeWatch(str(root), str(req))
            watcher.start(now=0)
            entered, release = Event(), Event()
            results = []
            original = module._local_fingerprint

            def delayed(root_arg):
                entered.set()
                if not release.wait(timeout=10):
                    raise AssertionError("timed out waiting for concurrent probe")
                return original(root_arg)

            def poll():
                results.append(watcher.tick(now=30))

            with patch.object(module, "_local_fingerprint", side_effect=delayed):
                thread = Thread(target=poll)
                thread.start()
                try:
                    self.assertTrue(entered.wait(timeout=10))
                    self.assertEqual(watcher.tick(now=30)["status"], "WAIT")
                finally:
                    release.set()
                    thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
            self.assertEqual([x["status"] for x in results], ["UNCHANGED"])
            self.assertTrue(watcher.active)

    def test_overlapping_remote_tick_is_single_flight(self):
        from threading import Event, Thread
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "remote"
            _project(root)
            head = "a" * 40
            entered, release = Event(), Event()

            @contextmanager
            def fake_snapshot(url, ref):
                yield {"root": str(root), "owner": "o", "repository": "r",
                       "commit_sha": head, "source_sha": "UNVERIFIED"}

            watcher = PublicGitHubChangeWatch("https://github.com/o/r",
                                               "main", "requirements.md")
            with patch("reqea.core.watch.public_github_snapshot",
                       side_effect=fake_snapshot):
                watcher.start(now=0)

            def delayed():
                entered.set()
                if not release.wait(timeout=10):
                    raise AssertionError("timed out waiting for concurrent ref probe")
                return head

            results = []
            with patch.object(watcher.reader, "head_commit_sha", side_effect=delayed):
                thread = Thread(target=lambda: results.append(watcher.tick(now=900)))
                thread.start()
                try:
                    self.assertTrue(entered.wait(timeout=10))
                    self.assertEqual(watcher.tick(now=900)["status"], "WAIT")
                finally:
                    release.set()
                    thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
            self.assertEqual([x["status"] for x in results], ["UNCHANGED"])
            self.assertTrue(watcher.active)

    def test_remote_retry_hint_prevents_premature_poll(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "public"
            _project(root)

            @contextmanager
            def fake_snapshot(url, ref):
                yield {"root": str(root), "owner": "o", "repository": "r",
                       "commit_sha": "a" * 40, "source_sha": "UNVERIFIED"}

            watcher = PublicGitHubChangeWatch("https://github.com/o/r", "main",
                                               "requirements.md")
            with patch("reqea.core.watch.public_github_snapshot",
                       side_effect=fake_snapshot):
                watcher.start(now=0)
            from reqea.core.github_source import GitHubRateLimitError
            with patch.object(watcher.reader, "head_commit_sha",
                              side_effect=GitHubRateLimitError(7200)):
                result = watcher.tick(now=900)
            self.assertEqual(result["status"], "BACKOFF")
            self.assertGreaterEqual(result["retry_seconds"], 7200)
            with patch.object(watcher.reader, "head_commit_sha",
                              return_value="a" * 40) as query:
                self.assertEqual(watcher.tick(now=8099)["status"], "WAIT")
                query.assert_not_called()
                self.assertEqual(watcher.tick(now=8100)["status"], "UNCHANGED")

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
                              side_effect=__import__("reqea.core.github_source", fromlist=["GitHubRateLimitError"]).GitHubRateLimitError()):
                result = watcher.tick(now=900)
            self.assertEqual(result["status"], "BACKOFF")
            self.assertGreaterEqual(result["retry_seconds"], 1800)
            self.assertEqual(watcher.tick(now=1800)["status"], "WAIT")
            watcher.stop()
            self.assertEqual(watcher.tick(now=20000)["status"], "STOPPED")


if __name__ == "__main__":
    unittest.main()
