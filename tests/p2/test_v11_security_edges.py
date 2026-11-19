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
from reqea.core.history import compare_audits, save_delta, load_deltas, register_project, load_projects
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

    def test_hash_consistent_forged_history_is_rejected_on_read(self):
        # An attacker can compute a correct SHA256 filename for arbitrary JSON.
        # Such a file is NOT trustworthy candidate history just because its
        # bytes and name agree. The GUI must never display its raw fields.
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            root.mkdir()
            canonical = compare_audits(_audit("UNASSESSED"),
                                       _audit("CODE_CANDIDATE"),
                                       before_snapshot="a" * 64,
                                       after_snapshot="b" * 64)
            written = save_delta(canonical, out_dir=str(Path(d) / "approved"),
                                 source_root=str(root))
            record = json.loads(Path(written["file"]).read_text(encoding="utf-8"))
            self.assertEqual(len(load_deltas(out_dir=str(Path(d) / "approved"))), 1)
            variants = {
                "forged_verified": dict(record, verification_status="VERIFIED"),
                "raw_source_field": dict(record, raw_source="PRIVATE_SOURCE"),
                "unsafe_warnings": dict(record, warnings=["PRIVATE_PATH"]),
                "extra_evidence": dict(record, evidence=[{"path": "secret"}]),
                "unhashable_status": dict(record, changes=[dict(record["changes"][0],
                                                               before=["VERIFIED"])]),
                "duplicate_req": dict(record, changes=[record["changes"][0],
                                                        record["changes"][0]]),
            }
            for label, forged in variants.items():
                with self.subTest(variant=label):
                    out = Path(d) / label
                    folder = out / "reqea-history"
                    folder.mkdir(parents=True)
                    encoded = (json.dumps(forged, ensure_ascii=False, sort_keys=True,
                                          separators=(",", ":")) + "\n").encode("utf-8")
                    sha = hashlib.sha256(encoded).hexdigest()
                    (folder / f"reqea-delta-{sha}.json").write_bytes(encoded)
                    with self.assertRaises(ValueError):
                        load_deltas(out_dir=str(out))

    def test_hash_consistent_forged_project_registry_is_rejected_before_cli_selection(self):
        # Project bookmarks and delta history require the same canonical
        # on-disk trust boundary: hash-addressing alone cannot authorize
        # extra fields, hidden source text or a forged verification claim.
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source = base / "owner-source"
            source.mkdir()
            sentinel = source / "keep.py"
            sentinel.write_bytes(b"OWNER_ORIGINAL")
            approved = base / "approved"
            original = register_project(
                {"kind": "local", "source": str(source), "requirements": "docs/REQ.md"},
                out_dir=str(approved))
            original_bytes = Path(original["file"]).read_bytes()
            record = json.loads(original_bytes.decode("utf-8"))
            self.assertEqual(load_projects(out_dir=str(approved)), [record])
            variants = {
                "extra_verification_claim": dict(record, verification_status="VERIFIED"),
                "hidden_source": dict(record, raw_private_source="SYNTHETIC_PRIVATE_SOURCE"),
                "wrong_schema": dict(record, schema_version="reqea.project.v99"),
                "unexpected_ref": dict(record, ref="main"),
                "extra_key": dict(record, export_secret="SYNTHETIC_CANARY"),
            }
            for label, forged in variants.items():
                with self.subTest(label=label):
                    out = base / label
                    folder = out / "reqea-projects"
                    folder.mkdir(parents=True)
                    data = (json.dumps(forged, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")) + "\n").encode("utf-8")
                    path = folder / ("reqea-profile-" + hashlib.sha256(data).hexdigest() + ".json")
                    path.write_bytes(data)
                    with self.assertRaisesRegex(ValueError, "noncanonical"):
                        load_projects(out_dir=str(out))
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        self.assertEqual(main(["projects", "--out", str(out)]), 2)
                    self.assertIn('"status": "UNASSESSED"', err.getvalue())
                    self.assertNotIn("SYNTHETIC_", err.getvalue())
                    self.assertEqual(path.read_bytes(), data, "preserve forged record as evidence")
            # Even with an internally valid record, duplicated JSON keys or
            # noncanonical bytes must never be silently normalized on read.
            bad = original_bytes.rstrip(b"\\n") + b" "
            out = base / "noncanonical-encoding"
            folder = out / "reqea-projects"
            folder.mkdir(parents=True)
            path = folder / ("reqea-profile-" + hashlib.sha256(bad).hexdigest() + ".json")
            path.write_bytes(bad)
            with self.assertRaisesRegex(ValueError, "noncanonical"):
                load_projects(out_dir=str(out))
            self.assertEqual(path.read_bytes(), bad)
            self.assertEqual(Path(original["file"]).read_bytes(), original_bytes)
            self.assertEqual(sentinel.read_bytes(), b"OWNER_ORIGINAL")

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

    def test_malformed_unhashable_req_status_fails_closed_without_history(self):
        # The CLI accepts explicit local audit JSON, which is untrusted even
        # when well-formed JSON. List/dict statuses must not crash with
        # TypeError or create any candidate-diff record.
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source = base / "approved-source"
            source.mkdir()
            sentinel = source / "keep.py"
            sentinel.write_bytes(b"OWNER_SOURCE_PRESERVE")
            before, after = base / "before.json", base / "after.json"
            out = base / "approved-output"
            baseline = _audit("GAP_CANDIDATE")
            before.write_text(json.dumps(baseline), encoding="utf-8")
            for status in ([], {}, ["VERIFIED"], {"status": "VERIFIED"}, None, 0):
                with self.subTest(status=status):
                    malformed = _audit("CODE_CANDIDATE")
                    malformed["findings"][0]["status"] = status
                    with self.assertRaisesRegex(ValueError, "untrusted REQ ID or status"):
                        compare_audits(baseline, malformed)
                    after.write_text(json.dumps(malformed), encoding="utf-8")
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        result = main(["compare", "--before", str(before), "--after", str(after),
                                       "--source-root", str(source), "--out", str(out)])
                    self.assertEqual(result, 2)
                    self.assertEqual(stdout.getvalue(), "")
                    self.assertEqual(json.loads(stderr.getvalue()),
                                     {"status": "UNASSESSED", "error_type": "ValueError"})
                    self.assertFalse((out / "reqea-history").exists())
            self.assertEqual(sentinel.read_bytes(), b"OWNER_SOURCE_PRESERVE")

    def test_deeply_nested_audit_json_does_not_crash_cli_or_write_output(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source = base / "approved-source"
            source.mkdir()
            before, after = base / "before.json", base / "after.json"
            out = base / "approved-output"
            before.write_text(json.dumps(_audit("UNASSESSED")), encoding="utf-8")
            # Valid JSON within the 2 MB file limit, but exceeds the Python
            # parser's recursion bound. Never propagate a raw RecursionError.
            after.write_text("[" * 1500 + "0" + "]" * 1500, encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main(["compare", "--before", str(before), "--after", str(after),
                               "--source-root", str(source), "--out", str(out)])
            self.assertEqual(result, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(json.loads(stderr.getvalue()),
                             {"status": "UNASSESSED", "error_type": "ValueError"})
            self.assertFalse(out.exists())

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
