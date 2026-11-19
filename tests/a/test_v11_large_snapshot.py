"""P2 GitHub snapshot request-budget and bounded-file integration checks.

Only a mocked HTTPS JSON transport is used; no customer files or network.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from unittest.mock import patch
import unittest

from reqea.core.snapshot import public_github_snapshot


class PublicSnapshotBudgetTests(unittest.TestCase):
    @staticmethod
    def _responses(file_count: int):
        blob = b"def example(): return 1\n"
        digest = hashlib.sha1(
            b"blob " + str(len(blob)).encode("ascii") + b"\x00" + blob,
            usedforsecurity=False,
        ).hexdigest()
        entries = [
            {"path": f"src/module_{i:03}.py", "type": "blob",
             "mode": "100644", "sha": digest, "size": len(blob)}
            for i in range(file_count)
        ]
        calls = []

        def fake_json(path, *, cap=2_000_000):
            calls.append(path)
            if path == "/repos/o/r":
                return {"private": False, "full_name": "o/r", "default_branch": "main"}
            if path == "/repos/o/r/commits/main":
                return {"sha": "a" * 40, "commit": {"tree": {"sha": "b" * 40}}}
            if path == "/repos/o/r/git/trees/" + "b" * 40 + "?recursive=1":
                return {"sha": "b" * 40, "truncated": False, "tree": entries}
            if path == "/repos/o/r/git/blobs/" + digest:
                return {"sha": digest, "size": len(blob), "encoding": "base64",
                        "content": base64.b64encode(blob).decode("ascii")}
            raise AssertionError("unexpected GitHub request route")
        return calls, fake_json

    def test_126_and_200_allowlisted_blobs_fit_finite_operation_budget(self):
        # Before fix, a legal 126-file snapshot died on the 129th API call.
        for count in (126, 200):
            with self.subTest(count=count):
                calls, fake_json = self._responses(count)
                with patch("reqea.core.github_source._json_get",
                           side_effect=fake_json):
                    with public_github_snapshot("https://github.com/o/r",
                                                "main") as snapshot:
                        source = Path(snapshot["root"])
                        self.assertEqual(snapshot["commit_sha"], "a" * 40)
                        self.assertEqual(snapshot["source_sha"], "UNVERIFIED")
                        self.assertEqual(snapshot["file_count"], count)
                        self.assertEqual(
                            (source / f"src/module_{count - 1:03}.py").read_bytes(),
                            b"def example(): return 1\n",
                        )
                    self.assertFalse(source.exists())
                self.assertEqual(len(calls), count + 3)

    def test_201_blobs_fail_before_any_network_blob_requests(self):
        calls, fake_json = self._responses(201)
        with patch("reqea.core.github_source._json_get", side_effect=fake_json):
            with self.assertRaisesRegex(ValueError, "exceeds bounded scope"):
                with public_github_snapshot("https://github.com/o/r", "main"):
                    self.fail("out-of-range snapshot should never be yielded")
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
