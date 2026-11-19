"""A-14 candidate-only REQ delta, append-only safe history and bookmark contracts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from reqea.core.history import compare_audits, save_delta, register_project, load_projects
from reqea.cli import main


def audit(state: str, *, sha: str = "UNVERIFIED", token: str = "SECRETS_IN_SOURCE_NEVER_EXPORT"):
    return {"schema_version": "reqea.v1", "source_sha": sha,
            "verification_status": "NOT_RUN",
            "warnings": ["raw_abs_path:/private/" + token],
            "findings": [{"req_id": "REQ-001", "status": state,
                          "rationale": token, "evidence": [{"path": "/private/" + token}]}]}


class DeltaHistory(unittest.TestCase):
    def test_comparison_only_candidate_states_no_source_payload(self):
        before = audit("GAP_CANDIDATE")
        after = audit("CODE_CANDIDATE")
        result = compare_audits(before, after, before_snapshot="a"*64, after_snapshot="b"*64)
        self.assertEqual(result["status"], "CANDIDATE_DIFF_ONLY")
        self.assertEqual(result["verification_status"], "NOT_RUN")
        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(result["changes"][0]["req_id"], "REQ-001")
        self.assertEqual(result["changes"][0]["before"], "GAP_CANDIDATE")
        self.assertEqual(result["changes"][0]["after"], "CODE_CANDIDATE")
        self.assertEqual(result["changes"][0]["before_evidence_count"], 1)
        self.assertEqual(result["before"]["scope"]["req_count"], 1)
        self.assertNotIn("SECRETS_IN_SOURCE_NEVER_EXPORT", json.dumps(result))
        self.assertNotIn("/private/", json.dumps(result))

    def test_save_append_only_preserves_owner_files_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "source"
            root.mkdir()
            (root / "app.py").write_bytes(b"keep original")
            out = base / "report"
            out.mkdir()
            foreign = out / "owner-keep.txt"
            foreign.write_bytes(b"OWNER")
            result = compare_audits(audit("UNASSESSED"), audit("CODE_CANDIDATE"),
                                    before_snapshot="a"*64, after_snapshot="b"*64)
            saved = save_delta(result, out_dir=str(out), source_root=str(root))
            self.assertEqual(saved["status"], "SAVED")
            record = Path(saved["file"])
            data = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(data["changed_count"], 1)
            self.assertEqual(data["verification_status"], "NOT_RUN")
            self.assertNotIn("SECRETS_IN_SOURCE_NEVER_EXPORT", record.read_text())
            self.assertEqual(saved["sha256"], hashlib.sha256(record.read_bytes()).hexdigest())
            again = save_delta(result, out_dir=str(out), source_root=str(root))
            self.assertEqual(again["status"], "EXISTS")
            self.assertEqual(foreign.read_bytes(), b"OWNER")
            self.assertEqual((root / "app.py").read_bytes(), b"keep original")

    def test_evidence_change_with_same_candidate_status_is_not_lost(self):
        before = audit("CODE_CANDIDATE")
        after = audit("CODE_CANDIDATE")
        after["findings"][0]["evidence"].append({"path": "/secret/NON_EXPORT"})
        result = compare_audits(before, after)
        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(result["changes"][0]["before"], "CODE_CANDIDATE")
        self.assertEqual(result["changes"][0]["after"], "CODE_CANDIDATE")
        self.assertEqual(result["changes"][0]["before_evidence_count"], 1)
        self.assertEqual(result["changes"][0]["after_evidence_count"], 2)
        self.assertEqual(result["after"]["scope"]["evidence_count"], 2)
        self.assertNotIn("/secret/NON_EXPORT", json.dumps(result))

    def test_source_interior_and_malformed_audit_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "source"
            root.mkdir()
            delta = compare_audits(audit("GAP_CANDIDATE"), audit("UNASSESSED"))
            with self.assertRaisesRegex(ValueError, "outside audited"):
                save_delta(delta, out_dir=str(root / "reports"), source_root=str(root))
            self.assertFalse((root / "reports").exists())
            bad = audit("VERIFIED")
            with self.assertRaises(ValueError):
                compare_audits(bad, audit("UNASSESSED"))
            duplicated = audit("UNASSESSED")
            duplicated["findings"].append(duplicated["findings"][0])
            with self.assertRaises(ValueError):
                compare_audits(duplicated, audit("UNASSESSED"))

    def test_session_project_bookmarks_persist_only_approved_local_output(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root, out = base / "source", base / "approved"
            root.mkdir()
            first = register_project({"kind": "local", "source": str(root),
                                      "requirements": "requirements.md"}, out_dir=str(out))
            second = register_project({"kind": "github",
                                       "source": "https://github.com/Owner/Repo",
                                       "ref": "feature/branch",
                                       "requirements": "docs/FINAL_BLUEPRINT.md"}, out_dir=str(out))
            self.assertEqual(first["status"], "SAVED")
            self.assertEqual(second["status"], "SAVED")
            records = load_projects(out_dir=str(out))
            self.assertEqual({r["kind"] for r in records}, {"local", "github"})
            self.assertEqual(len(records), 2)
            self.assertEqual(register_project({"kind": "local", "source": str(root),
                "requirements": "requirements.md"}, out_dir=str(out))["status"], "EXISTS")
            with self.assertRaises(ValueError):
                register_project({"kind": "github",
                                  "source": "https://github.com/o/r?token=SECRET",
                                  "ref": "main"}, out_dir=str(out))
            self.assertEqual(load_projects(out_dir=str(out)), records)

    def test_reopen_saved_delta_and_explicit_bookmark_removal(self):
        from reqea.core.history import load_deltas, unregister_project
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "root"
            root.mkdir()
            out = base / "approved"
            profile = {"kind": "local", "source": str(root), "requirements": "requirements.md"}
            register_project(profile, out_dir=str(out))
            delta = compare_audits(audit("GAP_CANDIDATE"), audit("UNASSESSED"),
                                   before_snapshot="a"*64, after_snapshot="b"*64)
            save_delta(delta, out_dir=str(out), source_root=str(root))
            records = load_deltas(out_dir=str(out))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["changed_count"], 1)
            self.assertTrue(unregister_project(profile, out_dir=str(out)))
            self.assertFalse(unregister_project(profile, out_dir=str(out)))
            self.assertEqual(load_projects(out_dir=str(out)), [])
            self.assertEqual(len(load_deltas(out_dir=str(out))), 1)

    def test_cli_project_registration_listing_selection_and_explicit_forget(self):
        with tempfile.TemporaryDirectory() as d:
            import contextlib, io
            base=Path(d)
            root=base/"sample"
            root.mkdir()
            (root/"src").mkdir()
            (root/"src"/"app.py").write_text("def f(): return 1\n", encoding="utf-8")
            (root/"requirements.md").write_text(
                "# REQ-001 CLI saved\nReference src/app.py\n"
                "Acceptance criteria:\n- static only\n", encoding="utf-8")
            out=base/"approved"
            def execute(*parts):
                stdout=io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    rc=main(list(parts))
                return rc,json.loads(stdout.getvalue())
            rc,created=execute("projects","--out",str(out),
                               "--add-repo",str(root),"--requirements","requirements.md")
            self.assertEqual(rc,0)
            ident=created["id"]
            self.assertEqual(len(ident),64)
            rc,listing=execute("projects","--out",str(out))
            self.assertEqual(rc,0)
            self.assertEqual(listing["projects"],[{"id":ident,"kind":"local"}])
            self.assertNotIn(str(root),json.dumps(listing))
            rc,found=execute("discover","--registered",ident,"--out",str(out))
            self.assertEqual(rc,0)
            self.assertEqual(found["status"],"SINGLE_CANDIDATE")
            rc,report=execute("audit-source","--registered",ident,"--out",str(out))
            self.assertEqual(rc,0,report)
            self.assertEqual(json.loads((out/"audit.json").read_text(encoding="utf-8"))["schema_version"],
                             "reqea.v1")
            rc,removed=execute("projects","--out",str(out),"--forget",ident)
            self.assertEqual(rc,0)
            self.assertEqual(removed["status"],"FORGOTTEN")
            self.assertEqual((root/"src"/"app.py").read_text(encoding="utf-8"),
                             "def f(): return 1\n")
            self.assertTrue((out/"manifest.json").exists())

    def test_cli_compare_existing_v1_output(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            source=base/"source"
            source.mkdir()
            out=base/"out"
            out.mkdir()
            prior=base/"prior.json"; current=base/"current.json"
            prior.write_text(json.dumps(audit("UNASSESSED")), encoding="utf-8")
            current.write_text(json.dumps(audit("CODE_CANDIDATE")), encoding="utf-8")
            import contextlib, io
            stdout=io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc=main(["compare","--before",str(prior),"--after",str(current),
                         "--source-root",str(source),"--out",str(out)])
            self.assertEqual(rc,0)
            summary=json.loads(stdout.getvalue())
            self.assertEqual(summary["status"],"CANDIDATE_DIFF_ONLY")
            self.assertEqual(summary["changed_count"],1)
            self.assertEqual(summary["verification_status"],"NOT_RUN")
            denied = main(["compare", "--before", str(prior), "--after", str(current),
                           "--source-root", str(source), "--out", str(source / "unsafe")])
            self.assertEqual(denied, 2)
            self.assertFalse((source / "unsafe").exists())



if __name__ == "__main__":
    unittest.main()
