"""Pure synthetic orchestration checks for real public GitHub integration smoke."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager, redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import live_github_readonly_probe as probe
from reqea.core.github_source import GitHubRateLimitError


class LiveProbeSynthetic(unittest.TestCase):
    def test_full_live_probe_orchestration_with_ephemeral_owned_source(self):
        sha = "a" * 40
        expected = b"def main("
        roots = []

        class FakeReader:
            def __init__(self, url, ref):
                self.url, self.ref = url, ref

            def head_commit_sha(self):
                return sha

            def pinned_tree(self):
                return sha, "b" * 40, [
                    {"path": "src/reqea/cli.py", "type": "blob",
                     "sha": "c" * 40, "size": len(expected)}
                ]

            def read_blob(self, sha_arg, *, max_bytes):
                self_test.assertEqual(sha_arg, "c" * 40)
                return expected

        self_test = self

        @contextmanager
        def fake_snapshot(url, ref):
            self.assertEqual(url, probe._PUBLIC_B_REPO)
            self.assertEqual(ref, probe._PUBLIC_B_SHA)
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder) / "source"
                walk = root / "src" / "reqea_codegraph" / "walk.py"
                walk.parent.mkdir(parents=True)
                walk.write_bytes(b"def scan_tree(root): return root\n")
                roots.append(root)
                yield {"root": str(root), "file_count": 14,
                       "commit_sha": probe._PUBLIC_B_SHA,
                       "source_sha": "UNVERIFIED"}

        out = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"REQEA_PUBLIC_SELF_SHA": sha}))
            stack.enter_context(patch.object(probe, "PublicGitHubReader", FakeReader))
            stack.enter_context(patch.object(probe, "public_github_snapshot", fake_snapshot))
            stack.enter_context(redirect_stdout(out))
            self.assertEqual(probe.main(), 0)
        self.assertIn("LIVE_PUBLIC_GITHUB_P2_PASS", out.getvalue())
        self.assertIn("LIVE_PUBLIC_B_SNAPSHOT_P2_PASS", out.getvalue())
        self.assertEqual(len(roots), 1)
        self.assertFalse(roots[0].exists())

    def test_quota_failure_is_explicit_skip_never_live_pass(self):
        class Throttled:
            def __init__(self, url, ref):
                pass

            def head_commit_sha(self):
                raise GitHubRateLimitError(7200)

        out = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"REQEA_PUBLIC_SELF_SHA": "a" * 40}))
            stack.enter_context(patch.object(probe, "PublicGitHubReader", Throttled))
            stack.enter_context(redirect_stdout(out))
            self.assertEqual(probe.main(), 0)
        self.assertIn("LIVE_PUBLIC_GITHUB_P2_SKIP", out.getvalue())
        self.assertNotIn("LIVE_PUBLIC_GITHUB_P2_PASS", out.getvalue())

    def test_access_denied_remains_failure_not_skip(self):
        class Denied:
            def __init__(self, url, ref):
                pass

            def head_commit_sha(self):
                raise ValueError("GitHub access denied")

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"REQEA_PUBLIC_SELF_SHA": "a" * 40}))
            stack.enter_context(patch.object(probe, "PublicGitHubReader", Denied))
            with self.assertRaisesRegex(ValueError, "access denied"):
                probe.main()


if __name__ == "__main__":
    unittest.main()
