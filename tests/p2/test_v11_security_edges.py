"""P2 negative-path scope checks for V1.1 public-source and local-history boundaries.

Every fixture is synthetic. No network, credentials, customer content or
user-owned files are opened. This is NOT independent security sign-off.
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reqea.cli import main
from reqea.core.github_source import PublicGitHubReader, _RejectRedirect, parse_public_github_url
from reqea.core.history import compare_audits, save_delta, load_deltas, register_project
from reqea.core.snapshot import public_github_snapshot


def _audit(status: str) -> dict:
    return {"schema_version": "reqea.v1",
            "source_sha": "UNVERIFIED", "verification_status": "NOT_RUN",
            "findings": [{"req_id": "REQ-001", "status": status,
                          "evidence": [{"path": "/private/secret.txt"}],
                          "rationale": "SECRET_DO_NOT_EXPORT"}],
            "warnings": ["/private/path/DO_NOT_EXPORT"]}


class V11SecurityBoundaryTests(unittest.TestCase):
    def test_github_internal_routes_are_statically_scoped_to_selected_repo(self):
        reader = PublicGitHubReader("https://github.com/Example/Repo", "feature/main")
        allowed = ("", "/commits/feature/main", "/git/trees/" + "a" * 40 + "?recursive=1",
                   "/git/blobs/" + "b" * 40)
        denied = ("/../../other", "/git/trees/" + "a"*40 + "?recursive=0",
                  "/git/blobs/" + "b"*40 + "/../../other", "/issues",
                  "https://localhost:1234", "/commits/../danger",
                  "/commits/main?token=XYZ", "/commits/feature//evil")
        with patch("reqea.core.github_source._json_get", return_value={"ok": True}) as get:
            for path in allowed:
                with self.subTest(allowed=path):
                    self.assertEqual(reader._read(path), {"ok": True})
            self.assertEqual(get.call_count, len(allowed))
            for path in denied:
                with self.subTest(denied=path), self.assertRaises(ValueError):
                    reader._read(path)
            self.assertEqual(get.call_count, len(allowed), "denied routes must never reach transport")

    def test_redirect_handler_rejects_cross_host_and_same_host_redirects(self):
        handler = _RejectRedirect()
        for url in ("https://evil.example/data", "https://api.github.com/repos/other/repo"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "redirect refused"):
                handler.redirect_request(None, None, 302, "moved", {}, url)

    def test_url_with_embedded_secret_rejected_before_remote_read(self):
        with patch("reqea.core.github_source._json_get") as get:
            for candidate in (
                "https://github.com/owner/repo?token=GH_SECRET",
                "https://token@github.com/owner/repo",
                "https://github.com.evil.invalid/owner/repo",
                "http://github.com/owner/repo",
            ):
                with self.subTest(url=candidate), self.assertRaises(ValueError):
                    parse_public_github_url(candidate)
            get.assert_not_called()

    def test_case_colliding_public_tree_fails_before_blob_open(self):
        records=[
            {"path": "src/Unit.py", "type": "blob", "mode": "100644",
             "sha": "a"*40, "size": 3},
            {"path": "src/unit.py", "type": "blob", "mode": "100644",
             "sha": "b"*40, "size": 4},
        ]
        with patch("reqea.core.snapshot.PublicGitHubReader.pinned_tree",
                   return_value=("c"*40, "d"*40, records)):
            with patch("reqea.core.snapshot.PublicGitHubReader.read_blob") as blob:
                with self.assertRaisesRegex(ValueError, "casefold-colliding"):
                    with public_github_snapshot("https://github.com/owner/repo"):
                        pass
                blob.assert_not_called()

    def test_corrupted_history_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            root=base/"source"; root.mkdir()
            out=base/"out"
            delta=compare_audits(_audit("GAP_CANDIDATE"), _audit("CODE_CANDIDATE"))
            initial=save_delta(delta, out_dir=str(out), source_root=str(root))
            record=Path(initial["file"])
            raw=record.read_bytes()
            self.assertNotIn(b"SECRET_DO_NOT_EXPORT", raw)
            self.assertNotIn(b"/private/", raw)
            tampered=b"tampered record; do not delete"
            record.write_bytes(tampered)
            with self.assertRaises(ValueError):
                save_delta(delta, out_dir=str(out), source_root=str(root))
            with self.assertRaises(ValueError):
                load_deltas(out_dir=str(out))
            self.assertEqual(record.read_bytes(), tampered)

    def test_symlinked_history_folder_never_writes_outside_approved_destination(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            approved=base/"approved"; approved.mkdir()
            external=base/"outside"; external.mkdir()
            try:
                (approved/"reqea-history").symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(type(exc).__name__)
            delta=compare_audits(_audit("UNASSESSED"), _audit("CODE_CANDIDATE"))
            with self.assertRaises((ValueError, OSError)):
                save_delta(delta, out_dir=str(approved))
            self.assertFalse(list(external.iterdir()))

    def test_compare_cli_never_prints_absolute_paths_or_source_fragments(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            root=base/"private-synthetic-source"
            root.mkdir()
            prior,after=base/"prior.json",base/"after.json"
            prior.write_text(json.dumps(_audit("UNASSESSED")), encoding="utf-8")
            after.write_text(json.dumps(_audit("CODE_CANDIDATE")), encoding="utf-8")
            out=base/"approved-output"
            stdout=io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result=main(["compare", "--before",str(prior), "--after",str(after),
                             "--source-root",str(root), "--out",str(out)])
            self.assertEqual(result,0)
            data=json.loads(stdout.getvalue())
            self.assertEqual(data["status"],"CANDIDATE_DIFF_ONLY")
            self.assertEqual(data["verification_status"],"NOT_RUN")
            self.assertTrue(data["record_name"].startswith("reqea-delta-"))
            self.assertNotIn(str(base),stdout.getvalue())
            self.assertNotIn("SECRET_DO_NOT_EXPORT",stdout.getvalue())
            self.assertNotIn("/private/",stdout.getvalue())

    def test_registered_local_project_cannot_store_metadata_inside_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"root"
            root.mkdir()
            original=root/"code.py"
            original.write_bytes(b"DO_NOT_CHANGE")
            with self.assertRaisesRegex(ValueError, "outside audited source"):
                register_project({"kind":"local","source":str(root),
                                  "requirements":None},out_dir=str(root/"hidden-output"))
            self.assertEqual(original.read_bytes(),b"DO_NOT_CHANGE")
            self.assertFalse((root/"hidden-output").exists())


if __name__ == "__main__":
    unittest.main()
