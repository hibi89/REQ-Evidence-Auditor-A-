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
            app.paths["requirements"].set(str(small_req))
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
            app.mode.set("local")
            app.start_watch()
            pump(app, lambda: app._watcher is not None and app._watcher.active,
                 "explicit local watch startup")
            watcher = app._watcher
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
            app.stop_watch()
            assert not watcher.active, "Stop must make subsequent polling inactive"
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
            print("V1.1 registered project, opt-in watch, local-only delta and "
                  "public-GitHub GUI source route: synthetic PASS; live network NOT_RUN")

            print("GUI event-loop Unicode long-path, no-clobber, fail-closed output, "
                  "approved overwrite and source immutability: synthetic PASS; "
                  "Windows 11 actual UX NOT_RUN")
    finally:
        app.destroy()
