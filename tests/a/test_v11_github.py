"""Public-GitHub-only P1 bounded source snapshot, URL and blob security contracts."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import unittest

from reqea.core.github_source import (PublicGitHubReader, parse_public_github_url,
                                      validate_ref)
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
        with patch.object(reader, "pinned_tree", return_value=("a"*40, "b"*40, [
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
