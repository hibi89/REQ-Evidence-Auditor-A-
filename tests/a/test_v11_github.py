"""Public-GitHub-only P1 bounded source snapshot, URL and blob security contracts."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import format_datetime
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import patch
import unittest

from reqea.core.github_source import (PublicGitHubReader, parse_public_github_url,
                                      validate_ref)
from reqea.core import github_source
from reqea.core.snapshot import public_github_snapshot


def _blob(data: bytes) -> tuple[str, dict]:
    sha = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
    return sha, {"sha": sha, "size": len(data), "encoding": "base64",
                 "content": base64.b64encode(data).decode("ascii")}


class PublicGitHubSnapshot(unittest.TestCase):
    def test_validates_URL_and_branch_without_network(self):
        self.assertEqual(parse_public_github_url("https://github.com/Owner/My_Repo"), ("Owner", "My_Repo"))
        self.assertEqual(validate_ref("feature/reqea-v11"), "feature/reqea-v11")
        self.assertIsNone(validate_ref(""))
        for url in ("http://github.com/o/r", "https://github.com@localhost/o/r",
                    "https://github.com/o/r/tree/main", "https://github.com/o/r?token=ABC",
                    "https://github.com/o/r#secret", "https://github.com:443/o/r",
                    "https://api.github.com/o/r", "https://github.com/o/r.git"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_public_github_url(url)
        for ref in ("../evil", "main//other", "feature/../attack", "-bad", ".hidden",
                    "heads/%2Fsecret", "main?token=x", "refs/a.lock", "foo\\bar"):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                validate_ref(ref)

    def test_http_403_distinguishes_denial_from_quota_without_network(self):
        # GitHub 403 alone must not requeue an inaccessible repo forever.
        cases = [
            (403, {}, "GitHub access denied"),
            (403, {"X-RateLimit-Remaining": "0"}, "GitHub rate limited"),
            (403, {"Retry-After": "120"}, "GitHub rate limited"),
            (429, {}, "GitHub rate limited"),
        ]
        for code, values, expected in cases:
            with self.subTest(status=code, headers=values):
                headers = Message()
                for key, value in values.items():
                    headers[key] = value

                class ForbiddenOpener:
                    def open(self, request, timeout):
                        raise HTTPError(request.full_url, code, "synthetic", headers, None)

                with patch.object(github_source, "build_opener",
                                  return_value=ForbiddenOpener()):
                    with self.assertRaisesRegex(ValueError, expected):
                        github_source._json_get("/repos/o/r")

    def test_transient_http_server_failures_are_retryable_not_denied(self):
        for code in (408, 500, 502, 503, 504):
            with self.subTest(code=code):
                headers = Message()
                headers["Retry-After"] = "3600"
                class FailingOpener:
                    def open(self, request, timeout):
                        raise HTTPError(request.full_url, code, "untrusted", headers, None)
                with patch.object(github_source, "build_opener",
                                  return_value=FailingOpener()):
                    with self.assertRaises(github_source.GitHubTransientError) as caught:
                        github_source._json_get("/repos/o/r")
                self.assertEqual(caught.exception.retry_seconds, 3600)
                self.assertNotIn("untrusted", str(caught.exception))

    def test_offline_transport_and_timeout_are_retryable_but_tls_stays_fatal(self):
        import ssl
        from urllib.error import URLError

        class FailingOpener:
            def __init__(self, error):
                self.error = error

            def open(self, request, timeout):
                raise self.error

        for error in (URLError(ConnectionResetError("private host name")),
                      TimeoutError("private host name"), OSError("private host name")):
            with self.subTest(error=type(error).__name__):
                with patch.object(github_source, "build_opener",
                                  return_value=FailingOpener(error)):
                    with self.assertRaises(github_source.GitHubTransientError) as caught:
                        github_source._json_get("/repos/o/r")
                self.assertIsNone(caught.exception.retry_seconds)
                self.assertNotIn("private host name", str(caught.exception))

        for error in (URLError(ssl.SSLError("untrusted certificate")),
                      ssl.SSLError("untrusted certificate")):
            with self.subTest(error=type(error).__name__):
                with patch.object(github_source, "build_opener",
                                  return_value=FailingOpener(error)):
                    with self.assertRaisesRegex(ValueError, "TLS/transport") as caught:
                        github_source._json_get("/repos/o/r")
                self.assertNotIsInstance(caught.exception, github_source.GitHubRetryableError)
                self.assertNotIn("untrusted certificate", str(caught.exception))

    def test_offline_watch_keeps_last_audit_backs_off_and_recovers(self):
        from urllib.error import URLError
        from reqea.core.watch import PublicGitHubChangeWatch

        watcher = PublicGitHubChangeWatch("https://github.com/o/r", ref="main")
        previous = {"schema_version": "reqea.v1", "marker": "prior-readonly-audit"}
        watcher.active = True
        watcher._head = "a" * 40
        watcher._audit = previous
        watcher._checked_at = 0.0

        class OfflineOpener:
            def open(self, request, timeout):
                raise URLError(ConnectionResetError("private network detail"))

        with patch.object(github_source, "build_opener", return_value=OfflineOpener()):
            result = watcher.tick(now=900.0)
        self.assertEqual(result["status"], "BACKOFF")
        self.assertEqual(result["retry_seconds"], 1800.0)
        self.assertTrue(watcher.active)
        self.assertIs(watcher._audit, previous)
        self.assertEqual(watcher._head, "a" * 40)

        # The backoff must suppress HTTP while offline.
        with patch.object(github_source, "_json_get", side_effect=AssertionError("early GET")):
            self.assertEqual(watcher.tick(now=2699.0)["status"], "WAIT")

        calls = []
        def healthy_get(path, *, cap=2_000_000):
            calls.append(path)
            if path.endswith("/o/r"):
                return {"private": False, "full_name": "o/r", "default_branch": "main"}
            if path.endswith("/commits/main"):
                return {"sha": "a" * 40}
            raise AssertionError("unexpected GitHub read-only route")

        with patch.object(github_source, "_json_get", side_effect=healthy_get):
            self.assertEqual(watcher.tick(now=2700.0)["status"], "UNCHANGED")
        self.assertEqual(len(calls), 2)
        self.assertTrue(watcher.active)
        self.assertIs(watcher._audit, previous)
        self.assertEqual(watcher._head, "a" * 40)
        self.assertEqual(watcher._backoff, 900.0)

    def test_permanent_401_404_501_do_not_retry(self):
        for code in (401, 404, 501):
            with self.subTest(code=code):
                class FailingOpener:
                    def open(self, request, timeout):
                        raise HTTPError(request.full_url, code, "untrusted", Message(), None)
                with patch.object(github_source, "build_opener",
                                  return_value=FailingOpener()):
                    with self.assertRaises(ValueError) as caught:
                        github_source._json_get("/repos/o/r")
                self.assertNotIsInstance(caught.exception, github_source.GitHubRetryableError)

    def test_transient_retry_header_invalid_fails_closed(self):
        headers = Message()
        headers["Retry-After"] = "not a date"
        class FailingOpener:
            def open(self, request, timeout):
                raise HTTPError(request.full_url, 503, "untrusted", headers, None)
        with patch.object(github_source, "build_opener",
                          return_value=FailingOpener()):
            with self.assertRaisesRegex(ValueError, "invalid GitHub retry hint") as caught:
                github_source._json_get("/repos/o/r")
        self.assertNotIsInstance(caught.exception, github_source.GitHubRetryableError)

    def test_rate_limit_retry_after_and_reset_deadlines_without_network(self):
        # A server-required 2h delay must not be reduced to normal 30m backoff.
        numeric = Message()
        numeric["Retry-After"] = "7200"
        self.assertEqual(github_source._retry_delay(numeric), 7200)
        date_hint = Message()
        date_hint["Retry-After"] = format_datetime(
            datetime.now(timezone.utc) + timedelta(hours=1), usegmt=True
        )
        self.assertTrue(3580 <= github_source._retry_delay(date_hint) <= 3601)
        reset = Message()
        reset["X-RateLimit-Remaining"] = "0"
        reset["X-RateLimit-Reset"] = "1800003600"
        with patch.object(github_source.time, "time", return_value=1800000000):
            self.assertEqual(github_source._retry_delay(reset), 3600)

    def test_rate_limit_malformed_or_overlong_hint_fails_closed(self):
        for hint in ("garbage-date", "9999999999", "123456789012345"):
            with self.subTest(hint=hint):
                headers = Message()
                headers["Retry-After"] = hint
                with self.assertRaises(ValueError):
                    github_source._retry_delay(headers)
        headers = Message()
        headers["X-RateLimit-Remaining"] = "0"
        headers["X-RateLimit-Reset"] = "not-a-timestamp"
        with self.assertRaises(ValueError):
            github_source._retry_delay(headers)

    def test_http_429_carries_safe_retry_metadata(self):
        headers = Message()
        headers["Retry-After"] = "7200"

        class LimitedOpener:
            def open(self, request, timeout):
                raise HTTPError(request.full_url, 429, "synthetic", headers, None)

        with patch.object(github_source, "build_opener",
                          return_value=LimitedOpener()):
            with self.assertRaises(github_source.GitHubRateLimitError) as caught:
                github_source._json_get("/repos/o/r")
        self.assertEqual(caught.exception.retry_seconds, 7200)

    def test_pinned_public_snapshot_verifies_blobs_and_cleans_up(self):
        source = b"# REQ-001 sampled\\nAcceptance criteria:\\n- file exists\\n".replace(b"\\n", b"\n")
        source_sha, blob = _blob(source)
        code_sha, code = _blob(b"def run(): return True\n")
        commit = "a" * 40
        tree_sha = "b" * 40
        calls: list[str] = []

        def fake_api(path, *, cap=2_000_000):
            calls.append(path)
            if path.endswith("/o/r"):
                return {"private": False, "full_name": "o/r", "default_branch": "main"}
            if "/commits/" in path:
                return {"sha": commit, "commit": {"tree": {"sha": tree_sha}}}
            if "/git/trees/" in path:
                return {"sha": tree_sha, "truncated": False, "tree": [
                    {"path": "docs/FINAL_BLUEPRINT.md", "type": "blob",
                     "mode": "100644", "sha": source_sha, "size": len(source)},
                    {"path": "src/app.py", "type": "blob",
                     "mode": "100644", "sha": code_sha, "size": 23},
                    {"path": ".env", "type": "blob", "mode": "100644",
                     "sha": "c" * 40, "size": 100},
                ]}
            if path.endswith(source_sha):
                return blob
            if path.endswith(code_sha):
                return code
            raise AssertionError("unexpected request " + path)

        with patch("reqea.core.github_source._json_get", side_effect=fake_api):
            with public_github_snapshot("https://github.com/o/r", ref="feature/topic") as snap:
                root = Path(snap["root"])
                self.assertEqual(snap["commit_sha"], commit)
                self.assertEqual(snap["source_sha"], "UNVERIFIED")
                self.assertEqual(snap["file_count"], 2)
                self.assertEqual((root / "docs/FINAL_BLUEPRINT.md").read_bytes(), source)
                self.assertEqual((root / "src/app.py").read_bytes(), b"def run(): return True\n")
                self.assertFalse((root / ".env").exists())
                saved_root = root
        self.assertFalse(saved_root.exists(), "ephemeral source must be disposed")
        self.assertFalse(any(x.endswith("c" * 40) for x in calls),
                         "hidden secrets must never be requested")

    def test_private_missing_and_unsafe_tree_fail_closed(self):
        with patch("reqea.core.github_source._json_get", return_value={
            "private": True, "full_name": "o/r", "default_branch": "main"}):
            with self.assertRaisesRegex(ValueError, "not confirmed public"):
                with public_github_snapshot("https://github.com/o/r"):
                    pass
        reader = PublicGitHubReader("https://github.com/o/r")
        with patch("reqea.core.snapshot.PublicGitHubReader.pinned_tree", return_value=("a"*40, "b"*40, [
                {"path": "secret.py", "type": "blob", "mode": "100644",
                 "size": 2, "sha": "c"*40}])):
            with self.assertRaisesRegex(ValueError, "no eligible"):
                with public_github_snapshot("https://github.com/o/r"):
                    pass

    def test_hash_mismatch_is_rejected_before_writing(self):
        reader = PublicGitHubReader("https://github.com/o/r")
        good_sha, record = _blob(b"good")
        record["content"] = base64.b64encode(b"evil").decode("ascii")
        with patch("reqea.core.github_source._json_get", return_value=record):
            with self.assertRaisesRegex(ValueError, "SHA check"):
                reader.read_blob(good_sha, max_bytes=100)

    def test_snapshot_tree_symlink_is_not_restored(self):
        with patch("reqea.core.snapshot.PublicGitHubReader.pinned_tree", return_value=(
                "a"*40, "b"*40, [{"path": "docs/FINAL_BLUEPRINT.md",
                                  "type": "blob", "mode": "120000",
                                  "sha": "c"*40, "size": 4}])):
            with self.assertRaisesRegex(ValueError, "unsafe GitHub tree entry"):
                with public_github_snapshot("https://github.com/o/r"):
                    pass


if __name__ == "__main__":
    unittest.main()
