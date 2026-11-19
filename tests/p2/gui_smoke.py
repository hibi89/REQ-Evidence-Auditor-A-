"""Exercise real Tk GUI callbacks including Unicode paths and recovery (synthetic only).

This is runner-hosted GUI behavior verification, NOT Windows 11 desktop UX acceptance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

from reqea.gui.app import AuditorApp


def pump(app: AuditorApp, predicate, label: str, *, timeout: float = 25) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.update()
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(f"GUI did not reach {label}: {app.status_text.get()}")


with tempfile.TemporaryDirectory() as d:
    base = Path(d)
    repo = base / "synthetic GUI 한글"
    src = repo / "src"
    src.mkdir(parents=True)
    (src / "unit.py").write_bytes(b"def unit():\n    return 1\n")
    deep = src
    for n in range(9):
        deep = deep / (f"한글_심층경로_{n}_" + "a" * 22)
        deep.mkdir()
    deep_file = deep / "long.py"
    deep_file.write_bytes(b"def deep_unit():\n    return 1\n")
    long_ref = deep_file.relative_to(repo).as_posix()
    assert len(str(deep_file)) > 260, "long Unicode path was not constructed"
    req = repo / "requirements.md"
    req.write_text(
        "# REQ-001 UI synthetic\n"
        f"Reference src/unit.py and {long_ref}\n"
        "Acceptance criteria:\n- both files statically present\n",
        encoding="utf-8",
    )
    out = base / "output"
    before_source = {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in repo.rglob("*") if p.is_file()}
    app = AuditorApp()
    app.withdraw()
    try:
        app.paths["repo"].set(str(repo))
        app.paths["requirements"].set(str(req))
        app.paths["out"].set(str(out))
        with patch("reqea.gui.app.messagebox.showwarning") as warning:
            app.start_audit()
            pump(app, lambda: (out / "audit.json").is_file()
                 and "저장:" in app.status_text.get()
                 and app.start_button.instate(["!disabled"]), "first GUI audit")
            assert warning.call_count == 0
            assert (out / "report.html").is_file() and (out / "manifest.json").is_file()
            audit = json.loads((out / "audit.json").read_text(encoding="utf-8"))
            assert audit["schema_version"] == "reqea.v1"
            assert audit["verification_status"] == "NOT_RUN"
            evidence_paths = [e.get("path") for f in audit["findings"] for e in f.get("evidence", [])]
            assert long_ref in evidence_paths, "long Unicode source did not reach GUI report"
            originals = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
            unrelated = out / "owner-keep.txt"
            unrelated.write_bytes(b"DO_NOT_TOUCH")

            app.start_audit()
            pump(app, lambda: "분석 중단: FileExistsError" in app.status_text.get()
                 and app.start_button.instate(["!disabled"]), "GUI no-clobber rejection")
            assert warning.call_count == 1
            assert {name: (out / name).read_bytes() for name in originals} == originals
            assert unrelated.read_bytes() == b"DO_NOT_TOUCH"
            assert not (out / ".reqea-transaction.lock").exists()

            app.paths["out"].set(str(repo / "denied-inside-source"))
            app.start_audit()
            pump(app, lambda: "분석 중단: ValueError" in app.status_text.get()
                 and app.start_button.instate(["!disabled"]), "GUI inside-source rejection")
            assert warning.call_count == 2
            assert not (repo / "denied-inside-source").exists()

            app.paths["out"].set(str(out))
            app.allow_overwrite.set(True)
            app.start_audit()
            pump(app, lambda: "저장:" in app.status_text.get()
                 and app.start_button.instate(["!disabled"]), "GUI approved overwrite")
            assert warning.call_count == 2
            assert (out / "manifest.json").is_file()
            assert unrelated.read_bytes() == b"DO_NOT_TOUCH"
            after_source = {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in repo.rglob("*") if p.is_file()}
            assert after_source == before_source, "GUI must not mutate scanned project"
            assert sorted(p.name for p in out.iterdir()) == [
                "audit.json", "manifest.json", "owner-keep.txt", "report.html"
            ]
            # V1.1: additional small root avoids the long-path limit fixture,
            # and exercises the actual GUI caller -> registered project -> core.
            small = base / "simple-v11-project"
            (small / "src").mkdir(parents=True)
            (small / "src" / "app.py").write_text("def run(): return 1\n", encoding="utf-8")
            small_req = small / "requirements.md"
            small_req.write_text(
                "# REQ-001 - GUI extended\nReference src/app.py\n"
                "Acceptance criteria:\n- static candidate only\n", encoding="utf-8")
            v11out = base / "v11-output"
            app.paths["repo"].set(str(small))
            # Real Tk caller: a project-relative document must register even
            # though the process working directory is not the selected root.
            app.paths["requirements"].set("requirements.md")
            app.paths["out"].set(str(v11out))
            app.allow_overwrite.set(True)
            app.mode.set("local")
            app.register_selected_project()
            assert app._profiles and app._profiles[0]["kind"] == "local", "GUI must persist local registration"
            app.mode.set("registered")
            app.start_audit()
            pump(app, lambda: "저장:" in app.status_text.get()
                 and app.start_button.instate(["!disabled"]), "registered project audit")
            assert (v11out / "audit.json").is_file()
            # A cached registered project is never authorization to audit from
            # another output folder. Real Tk button path must reject it.
            app.paths["out"].set(str(base / "unapproved-registry"))
            with patch("reqea.gui.app.messagebox.showerror") as denied_stale:
                app.start_audit()
                denied_stale.assert_called_once()
            assert not (base / "unapproved-registry").exists()
            assert app.start_button.instate(["!disabled"])
            app.paths["out"].set(str(v11out))
            app.mode.set("local")
            app.start_watch()
            pump(app, lambda: app._watcher is not None and app._watcher.active,
                 "explicit local watch startup")
            watcher = app._watcher
            # A 1.2-second Tk timer must not launch a Python thread for
            # 30-second local WAIT or (for GitHub) 900-second WAIT.
            with patch("reqea.gui.app.threading.Thread.start") as started:
                for _ in range(5):
                    app._watch_cycle()
                started.assert_not_called()
            prior_audit = {"schema_version": "reqea.v1", "source_sha": "UNVERIFIED",
                           "verification_status": "NOT_RUN",
                           "findings": [{"req_id": "REQ-001", "status": "UNASSESSED"}]}
            current_audit = {"schema_version": "reqea.v1", "source_sha": "UNVERIFIED",
                             "verification_status": "NOT_RUN",
                             "findings": [{"req_id": "REQ-001", "status": "CODE_CANDIDATE"}]}
            with patch.object(watcher, "tick", return_value={
                     "status": "CHANGED", "previous": prior_audit, "current": current_audit,
                     "fingerprint": "a" * 64}):
                app._watch_tick_worker(app._watch_generation, watcher,
                                       str(v11out), str(small), app._watch_token)
            pump(app, lambda: "REQ 근거·상태 변화 1개" in app.status_text.get(),
                 "GUI watch change and saved history")
            assert list((v11out / "reqea-history").glob("reqea-delta-*.json"))
            # Editing an unrelated remote input must not cancel a local watch.
            app.remote_ref.set("feature/not-selected")
            assert watcher.active
            # Editing the approved output/source while watching must STOP
            # immediately; it must not keep polling the old source silently.
            preserved = sorted((v11out / "reqea-history").glob("reqea-delta-*.json"))
            app.paths["out"].set(str(base / "different-output"))
            assert not watcher.active and app._watcher is None
            assert app._watch_input_scope is None
            assert "감시 중지" in app.status_text.get()
            assert sorted((v11out / "reqea-history").glob("reqea-delta-*.json")) == preserved
            app.paths["out"].set(str(v11out))
            app.remote_ref.set("")
            app.start_watch()
            pump(app, lambda: app._watcher is not None and app._watcher.active,
                 "re-consented local watch after changing output")
            watcher = app._watcher
            app.stop_watch()
            assert not watcher.active, "Stop must make subsequent polling inactive"
            # STOP between clicking Start and worker entry must cancel
            # pending explicit permission, not merely the active watcher.
            with patch("reqea.gui.app.threading.Thread.start") as suppressed_launch:
                app.start_watch()
                pending = app._starting_watcher
                assert pending is not None and app._watcher is None
                suppressed_launch.assert_called_once()
                app.stop_watch()
                assert pending.start(now=0)["status"] == "STOPPED"
                assert not pending.active
                assert app._starting_watcher is None
            # On a real running worker, a STOP between delta computation and
            # persistence must not create additional change-history records.
            app.start_watch()
            pump(app, lambda: app._watcher is not None and app._watcher.active,
                 "restart with a newly authorized watch instance")
            watcher = app._watcher
            prior_records = sorted((v11out / "reqea-history").glob("reqea-delta-*.json"))
            def stop_during_compare(*args, **kwargs):
                app.stop_watch()
                return {"changed_count": 1}
            with patch.object(watcher, "tick", return_value={
                     "status": "CHANGED", "previous": prior_audit, "current": current_audit,
                     "fingerprint": "b" * 64}), \
                 patch("reqea.gui.app.compare_audits", side_effect=stop_during_compare), \
                 patch("reqea.gui.app.save_delta") as write:
                app._watch_tick_worker(app._watch_generation, watcher, str(v11out),
                                       str(small), app._watch_token)
                write.assert_not_called()
            assert sorted((v11out / "reqea-history").glob("reqea-delta-*.json")) == prior_records
            assert not watcher.active

            from contextlib import contextmanager

            @contextmanager
            def fake_snapshot(url, ref=None):
                assert url == "https://github.com/example/example"
                assert ref == "main"
                yield {"root": str(small), "owner": "example",
                       "repository": "example", "commit_sha": "a"*40,
                       "source_sha": "UNVERIFIED", "tree_sha": "b"*40}
            app.mode.set("github")
            app.remote_url.set("https://github.com/example/example")
            app.remote_ref.set("main")
            app.document_choice.set("requirements.md")
            with patch("reqea.gui.app.public_github_snapshot", side_effect=fake_snapshot):
                app.start_audit()
                pump(app, lambda: "저장:" in app.status_text.get()
                     and app.start_button.instate(["!disabled"]), "GUI public GitHub source audit")
            assert (v11out / "manifest.json").is_file()
            # Changing a GitHub ref while its start worker has not run must
            # revoke permission before the first network request.
            with patch("reqea.gui.app.threading.Thread.start") as queued:
                app.start_watch()
                pending_remote = app._starting_watcher
                assert pending_remote is not None
                queued.assert_called_once()
                app.remote_ref.set("feature/other-ref")
                assert app._starting_watcher is None and app._watcher is None
                assert pending_remote.start(now=0)["status"] == "STOPPED"
                assert not pending_remote.active
            app.remote_ref.set("main")
            # Change selected ref before a queued discovery starts: no GET.
            with patch("reqea.gui.app.threading.Thread.start") as queued:
                app.discover_documents()
                assert app._discovering and app._discovery_cancel_event is not None
                first_gen = app._generation
                first_cancel = app._discovery_cancel_event
                old_target = app._source()
                queued.assert_called_once()
                app.remote_ref.set("feature/new-branch")
                assert first_cancel.is_set() and not app._discovering
                assert app.discover_button.instate(["!disabled"])
                assert app._discovery_input_scope is None
                assert app.remote_discovery is None
                with patch("reqea.gui.app.public_github_snapshot") as forbidden:
                    app._discover_remote(first_gen, old_target, first_cancel)
                    forbidden.assert_not_called()
                app.poll()
                assert app.remote_discovery is None
            # Change ref during in-flight GET: no follow-up GET/stale result.
            with patch("reqea.gui.app.threading.Thread.start") as queued:
                app.discover_documents()
                second_gen = app._generation
                second_cancel = app._discovery_cancel_event
                second_target = app._source()
                queued.assert_called_once()
            @contextmanager
            def interrupted(url, ref, *, before_request=None):
                assert ref == "feature/new-branch"
                before_request()
                app.remote_ref.set("feature/changed-again")
                before_request()
                yield {"root": str(small), "commit_sha": "a" * 40}
            with patch("reqea.gui.app.public_github_snapshot", side_effect=interrupted):
                app._discover_remote(second_gen, second_target, second_cancel)
            app.poll()
            assert second_cancel.is_set() and not app._discovering
            assert app.remote_discovery is None
            assert not app.candidate_picker.cget("values"), "cancelled discovery must clear candidates"
            assert app.discover_button.instate(["!disabled"])
            print("V1.1 registered project, opt-in watch, local-only delta and "
                  "public-GitHub GUI source route: synthetic PASS; live network NOT_RUN")

            print("GUI event-loop Unicode long-path, no-clobber, fail-closed output, "
                  "approved overwrite and source immutability: synthetic PASS; "
                  "Windows 11 actual UX NOT_RUN")
    finally:
        app.destroy()
