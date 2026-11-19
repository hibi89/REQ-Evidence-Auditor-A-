"""V1.1 A-11 CLI caller -> canonical -> A/B/C -> local-only artifacts."""
from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reqea.cli import main


def _make(root: Path, *, second: bool = False) -> None:
    (root / "docs").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "unit.py").write_text("def unit(): return 1\n", encoding="utf-8")
    (root / "docs" / "FINAL_BLUEPRINT.md").write_text(
        "# REQ-001 scan\nReference src/unit.py\nAcceptance criteria:\n- exists\n",
        encoding="utf-8",
    )
    if second:
        (root / "docs" / "FINAL_BLUEPRINT_V11.md").write_text(
            "# REQ-031 scan extension\nAcceptance criteria:\n- source appears\n",
            encoding="utf-8",
        )


def _call(*args: str) -> tuple[int, dict]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        result = main(list(args))
    payload = json.loads(stdout.getvalue() if stdout.getvalue() else stderr.getvalue())
    return result, payload


class CallerToCalleeSourceAudit(unittest.TestCase):
    def test_approved_local_auto_candidate_to_v1_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root, out = base / "repo", base / "out"
            root.mkdir()
            _make(root)
            rc, data = _call("audit-source", "--repo", str(root), "--out", str(out))
            self.assertEqual(rc, 0)
            self.assertEqual(data["canonical_document"], "docs/FINAL_BLUEPRINT.md")
            self.assertEqual(data["verification_status"], "NOT_RUN")
            saved = json.loads((out / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["schema_version"], "reqea.v1")
            self.assertEqual([x["req_id"] for x in saved["findings"]], ["REQ-001"])
            self.assertNotEqual(saved["status"], "VERIFIED")
            rc2, denied = _call("audit-source", "--repo", str(root), "--out", str(out))
            self.assertEqual(rc2, 2, denied)
            self.assertTrue((out / "manifest.json").exists())

    def test_ambiguous_requires_explicit_document_and_stale_path_denied(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root, out = base / "repo", base / "out"
            root.mkdir()
            _make(root, second=True)
            rc, result = _call("audit-source", "--repo", str(root), "--out", str(out))
            self.assertEqual(rc, 2, result)
            self.assertFalse(out.exists(), "ambiguous choice must not save files")
            selected = "docs/FINAL_BLUEPRINT_V11.md"
            rc, data = _call("audit-source", "--repo", str(root),
                             "--requirements", selected, "--out", str(out))
            self.assertEqual(rc, 0, data)
            self.assertEqual(data["canonical_document"], selected)
            self.assertEqual(json.loads((out / "audit.json").read_text())["findings"][0]["req_id"],
                             "REQ-031")

    def test_github_snapshot_pinned_sha_distinguished_from_verified_source(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root, out = base / "synthetic-gh", base / "report"
            root.mkdir()
            _make(root)

            @contextmanager
            def fake_public(url: str, ref: str | None = None):
                self.assertEqual(url, "https://github.com/example/example")
                self.assertEqual(ref, "feature/branch")
                yield {"root": str(root), "owner": "example", "repository": "example",
                       "commit_sha": "a" * 40, "tree_sha": "b" * 40,
                       "source_sha": "UNVERIFIED"}

            with patch("reqea.cli.public_github_snapshot", side_effect=fake_public):
                rc, result = _call("audit-source", "--github-url",
                                   "https://github.com/example/example",
                                   "--ref", "feature/branch", "--out", str(out))
            self.assertEqual(rc, 0, result)
            self.assertEqual(result["pinned_commit_sha"], "a" * 40)
            self.assertEqual(result["source_sha"], "UNVERIFIED")
            self.assertEqual(result["verification_status"], "NOT_RUN")
            self.assertEqual(json.loads((out / "manifest.json").read_text())["source_sha"],
                             "UNVERIFIED")

    def test_gui_registered_selection_revalidates_current_registry_and_fails_closed(self):
        # Exercise the real GUI callback methods without requiring a window.
        # This catches reuse of a cached selection after changing the approved
        # output folder, deleting a bookmark or corrupting its on-disk bytes.
        from reqea.core.history import register_project
        from reqea.gui.app import AuditorApp
        from types import SimpleNamespace

        class Variable:
            def __init__(self, value=""):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class Picker:
            def __init__(self):
                self.values = []

            def configure(self, *, values):
                self.values = list(values)

        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "owner-project"
            root.mkdir()
            (root / "keep.py").write_bytes(b"OWNER_SOURCE_UNCHANGED")
            valid = base / "approved-output"
            unrelated = base / "other-output"
            profile = {"kind": "local", "source": str(root),
                       "requirements": "requirements.md"}
            created = register_project(profile, out_dir=str(valid))
            original = Path(created["file"]).read_bytes()
            gui = SimpleNamespace(
                mode=Variable("registered"),
                paths={"out": Variable(str(valid))},
                profile_choice=Variable(), profile_picker=Picker(),
                status_text=Variable(), _profiles=[], _profile_labels=[],
            )
            AuditorApp.load_registered_projects(gui)
            self.assertEqual(len(gui._profiles), 1)
            self.assertEqual(AuditorApp._source(gui)["source"], str(root))
            selected_label = gui.profile_choice.get()

            gui.paths["out"].set(str(unrelated))
            with self.assertRaisesRegex(ValueError, "saved project registry changed"):
                AuditorApp._source(gui)
            self.assertFalse(unrelated.exists(), "stale selection must never create output")
            self.assertEqual(gui.profile_choice.get(), selected_label)
            AuditorApp.load_registered_projects(gui)
            self.assertEqual(gui._profiles, [])
            self.assertEqual(gui._profile_labels, [])
            self.assertEqual(gui.profile_picker.values, [])
            self.assertEqual(gui.profile_choice.get(), "")
            with self.assertRaises(ValueError):
                AuditorApp._source(gui)

            gui.paths["out"].set(str(valid))
            AuditorApp.load_registered_projects(gui)
            self.assertEqual(len(gui._profiles), 1)
            Path(created["file"]).write_bytes(original + b" ")
            with self.assertRaisesRegex(ValueError, "modified registered project record"):
                AuditorApp._source(gui)
            AuditorApp.load_registered_projects(gui)
            self.assertEqual(gui._profiles, [])
            self.assertEqual(gui.profile_choice.get(), "")
            self.assertEqual(Path(created["file"]).read_bytes(), original + b" ")
            self.assertEqual((root / "keep.py").read_bytes(), b"OWNER_SOURCE_UNCHANGED")

    def test_gui_registration_relative_document_is_root_scoped_not_process_cwd(self):
        from types import SimpleNamespace
        from reqea.gui.app import AuditorApp
        from reqea.core.history import load_projects

        class Var:
            def __init__(self, v=""):
                self.value = v
            def get(self):
                return self.value
            def set(self, v):
                self.value = v

        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "owner-project"
            docs = root / "docs"
            docs.mkdir(parents=True)
            requirement = docs / "requirements.md"
            requirement.write_bytes(b"# REQ-001 synthetic\\n")
            original = requirement.read_bytes()
            out = base / "approved-output"
            target = {"kind": "local", "source": str(root),
                      "requirements": "docs/requirements.md", "ref": None}
            loads = []
            fake = SimpleNamespace(
                mode=Var("local"), status_text=Var(),
                paths={"out": Var(str(out))},
                _source=lambda: dict(target),
                load_registered_projects=lambda: loads.append(True))
            AuditorApp.register_selected_project(fake)
            self.assertIn("프로젝트 등록 SAVED", fake.status_text.get())
            self.assertEqual(loads, [True])
            saved = load_projects(out_dir=str(out))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["requirements"], "docs/requirements.md")
            self.assertEqual(saved[0]["source"], str(root))
            self.assertEqual(requirement.read_bytes(), original)

            # Absolute path outside the selected project is never a valid
            # registration, and a root-relative '..' cannot escape either.
            for refused in (str(base / "outside" / "requirements.md"),
                            "../outside/requirements.md"):
                with self.subTest(refused=refused):
                    target["requirements"] = refused
                    AuditorApp.register_selected_project(fake)
                    self.assertIn("프로젝트 등록 차단", fake.status_text.get())
                    self.assertEqual(len(load_projects(out_dir=str(out))), 1)
                    self.assertEqual(requirement.read_bytes(), original)
            self.assertEqual(loads, [True])

    def test_ref_on_local_root_and_output_inside_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            _make(root)
            rc, err = _call("audit-source", "--repo", str(root), "--ref", "main",
                            "--out", str(Path(d) / "out"))
            self.assertEqual(rc, 2, err)
            rc2, err2 = _call("audit-source", "--repo", str(root),
                             "--out", str(root / "unsafe-output"))
            self.assertEqual(rc2, 2, err2)
            self.assertFalse((root / "unsafe-output").exists())


if __name__ == "__main__":
    unittest.main()
