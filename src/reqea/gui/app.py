"""Explicit local/public-GitHub REQ candidate auditing and opt-in foreground watch."""
from __future__ import annotations

import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from reqea.core.discovery import discover_local_requirements
from reqea.core.github_source import parse_public_github_url, validate_ref
from reqea.core.history import (compare_audits, load_deltas, load_projects,
                                register_project, save_delta, unregister_project,
                                _safe_output)
from reqea.core.orchestrator import build_audit, render_audit_html
from reqea.core.output import save_artifacts
from reqea.core.selector import select_requirements
from reqea.core.snapshot import public_github_snapshot
from reqea.core.watch import LocalChangeWatch, PublicGitHubChangeWatch

_FATAL = frozenset(("required_B_or_C_module_unavailable", "B_contract_or_SHA_mismatch",
                    "C_contract_or_SHA_mismatch", "C_invalid_or_untrusted_status",
                    "C_invalid_finding_status", "C_invalid_warning_contract",
                    "analysis_failed_without_verified_evidence"))


class AuditorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("REQ Evidence Auditor — local / public GitHub")
        self.minsize(780, 570)
        self.paths = {"repo": tk.StringVar(), "requirements": tk.StringVar(),
                      "out": tk.StringVar()}
        self.mode = tk.StringVar(value="local")
        self.remote_url = tk.StringVar()
        self.remote_ref = tk.StringVar()
        self.status_text = tk.StringVar(value="로컬 폴더 또는 공개 GitHub 저장소를 명시적으로 선택하세요.")
        self.allow_overwrite = tk.BooleanVar(value=False)
        self.messages: queue.Queue[tuple[bool, str]] = queue.Queue()  # V1 legacy callback
        self.events: queue.Queue[tuple[str, int, object]] = queue.Queue()
        self.local_discovery: dict | None = None
        self.remote_discovery: dict | None = None
        self.document_choice = tk.StringVar()
        self.profile_choice = tk.StringVar()
        self._profile_labels: list[str] = []
        self._profiles: list[dict] = []
        self._generation = 0
        self._discovering = False
        self._watch_generation = 0
        self._watch_busy = False
        self._watcher: LocalChangeWatch | PublicGitHubChangeWatch | None = None
        self._watch_out = ""
        self._watch_source_root: str | None = None
        self._watch_token: str | None = None
        self._closing = False

        content = ttk.Frame(self, padding=14)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="REQ Evidence Auditor", font=("Arial", 18, "bold")).pack(anchor="w")
        ttk.Label(content, text="정적 근거 후보 · 실행/검증 PASS 아님 · GitHub는 선택한 공개 저장소만 읽기 전용").pack(anchor="w", pady=(2, 9))
        mode_line = ttk.Frame(content)
        mode_line.pack(fill="x", pady=3)
        ttk.Label(mode_line, text="소스 모드", width=24).pack(side="left")
        self.mode_picker = ttk.Combobox(mode_line, textvariable=self.mode, state="readonly",
                                        values=("local", "github", "registered"), width=18)
        self.mode_picker.pack(side="left")
        self.mode_picker.bind("<<ComboboxSelected>>", lambda _event: self.mode_changed())
        ttk.Label(mode_line, text="GitHub/감시는 사용자 버튼 전까지 OFF").pack(side="left", padx=10)

        for name, title, folder in (
            ("repo", "내 PC 프로젝트 폴더", True),
            ("requirements", "로컬 요구사항 파일", False),
            ("out", "승인된 결과 폴더 (원본 외부)", True),
        ):
            line = ttk.Frame(content)
            line.pack(fill="x", pady=3)
            ttk.Label(line, text=title, width=24).pack(side="left")
            ttk.Entry(line, textvariable=self.paths[name]).pack(side="left", fill="x", expand=True)
            ttk.Button(line, text="찾기", command=lambda k=name, f=folder: self.choose(k, f)).pack(side="left", padx=(6, 0))

        for variable, title in ((self.remote_url, "공개 GitHub URL"),
                                (self.remote_ref, "브랜치/tag/commit (선택)")):
            line = ttk.Frame(content)
            line.pack(fill="x", pady=3)
            ttk.Label(line, text=title, width=24).pack(side="left")
            ttk.Entry(line, textvariable=variable).pack(side="left", fill="x", expand=True)

        discover_line = ttk.Frame(content)
        discover_line.pack(fill="x", pady=7)
        self.discover_button = ttk.Button(discover_line, text="설계도 자동 찾기", command=self.discover_documents)
        self.discover_button.pack(side="left")
        self.candidate_picker = ttk.Combobox(discover_line, textvariable=self.document_choice,
                                               state="readonly", values=[], width=44)
        self.candidate_picker.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(discover_line, text="선택 적용", command=self.accept_discovered_document).pack(side="left")

        profile_line = ttk.Frame(content)
        profile_line.pack(fill="x", pady=5)
        self.profile_picker = ttk.Combobox(profile_line, textvariable=self.profile_choice,
                                           state="readonly", values=[], width=48)
        self.profile_picker.pack(side="left", fill="x", expand=True)
        ttk.Button(profile_line, text="프로젝트 등록", command=self.register_selected_project).pack(side="left", padx=(6, 0))
        ttk.Button(profile_line, text="등록 불러오기", command=self.load_registered_projects).pack(side="left", padx=(6, 0))
        ttk.Button(profile_line, text="등록 해제", command=self.forget_registered_project).pack(side="left", padx=(6, 0))

        ttk.Checkbutton(content, text="기존 분석 결과 덮어쓰기 명시적으로 허용",
                        variable=self.allow_overwrite).pack(anchor="w", pady=(8, 3))
        actions = ttk.Frame(content)
        actions.pack(fill="x", pady=6)
        self.start_button = ttk.Button(actions, text="분석 실행", command=self.start_audit)
        self.start_button.pack(side="left")
        self.watch_button = ttk.Button(actions, text="감시 시작 (명시적 ON)", command=self.start_watch)
        self.watch_button.pack(side="left", padx=7)
        self.stop_button = ttk.Button(actions, text="감시 중지", command=self.stop_watch)
        self.stop_button.pack(side="left")
        ttk.Button(actions, text="변경 이력 열기", command=self.show_history).pack(side="left", padx=7)
        ttk.Label(content, textvariable=self.status_text, wraplength=730,
                  justify="left").pack(fill="x", anchor="w", pady=8)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self.poll)
        self.after(1200, self._watch_cycle)

    def mode_changed(self) -> None:
        if self._watcher is not None or self._watch_busy:
            self.stop_watch()
        self._generation += 1
        self.local_discovery = None
        self.remote_discovery = None
        self.document_choice.set("")
        self.candidate_picker.configure(values=[])
        self.status_text.set("모드를 선택했습니다. 프로젝트/URL을 확인하고 설계도를 탐색하세요.")

    def _source(self) -> dict:
        mode = self.mode.get()
        if mode == "registered":
            choice = self.profile_choice.get()
            if choice not in self._profile_labels:
                raise ValueError("select a saved project from approved output")
            saved = self._profiles[self._profile_labels.index(choice)]
            return dict(saved)
        if mode == "local":
            root = self.paths["repo"].get().strip()
            if not root:
                raise ValueError("local project root required")
            return {"kind": "local", "source": root,
                    "requirements": self.paths["requirements"].get().strip() or None, "ref": None}
        if mode == "github":
            url = self.remote_url.get().strip()
            parse_public_github_url(url)
            ref = validate_ref(self.remote_ref.get().strip())
            return {"kind": "github", "source": url, "ref": ref,
                    "requirements": self.document_choice.get().strip() or None}
        raise ValueError("unknown source mode")

    def choose(self, key: str, folder: bool) -> None:
        selected = (filedialog.askdirectory(parent=self) if folder
                    else filedialog.askopenfilename(
                        parent=self, filetypes=[("Requirements", "*.md *.markdown *.json"),
                                               ("All files", "*.*")]))
        if selected:
            self.paths[key].set(selected)

    def discover_documents(self) -> None:
        if self._discovering:
            return
        try:
            target = self._source()
        except (ValueError, OSError):
            self.status_text.set("입력 오류 · 프로젝트/공개 GitHub URL을 확인하세요")
            return
        self._generation += 1
        gen = self._generation
        self.local_discovery = None
        self.remote_discovery = None
        self.document_choice.set("")
        self.candidate_picker.configure(values=[])
        self.paths["requirements"].set("" if target["kind"] == "local" else self.paths["requirements"].get())
        if target["kind"] == "local":
            try:
                discovered = discover_local_requirements(target["source"])
            except (ValueError, OSError, UnicodeError):
                self.status_text.set("설계도 탐색 차단 · 범위/권한/문서를 확인하세요")
                return
            self.local_discovery = discovered
            self._show_candidates(discovered)
            return
        self._discovering = True
        self.discover_button.state(["disabled"])
        self.status_text.set("선택한 공개 GitHub 저장소에서 읽기 전용 설계도 탐색 중...")
        threading.Thread(target=self._discover_remote, args=(gen, target),
                         daemon=True).start()

    def _discover_remote(self, gen: int, target: dict) -> None:
        try:
            with public_github_snapshot(target["source"], target.get("ref")) as snap:
                found = discover_local_requirements(snap["root"])
                result = {
                    "url": target["source"], "ref": target.get("ref"),
                    "commit_sha": snap["commit_sha"],
                    "candidates": found["candidates"], "status": found["status"],
                    "warnings": found["warnings"],
                }
            self.events.put(("discovery", gen, result))
        except (ValueError, OSError, UnicodeError, TypeError, KeyError) as exc:
            self.events.put(("discovery", gen, {"error": type(exc).__name__}))

    def _show_candidates(self, found: dict) -> None:
        candidates = [c["path"] for c in found.get("candidates", [])]
        self.candidate_picker.configure(values=candidates)
        if found["status"] == "SINGLE_CANDIDATE":
            self.document_choice.set(candidates[0])
            self.accept_discovered_document()
        elif found["status"] == "AMBIGUOUS":
            self.status_text.set(f"설계도 후보 {len(candidates)}개 · 직접 선택 후 '선택 적용' (NOT VERIFIED)")
        else:
            self.status_text.set(f"설계도 {found['status']} · 분석 시작 차단 (UNASSESSED)")

    def accept_discovered_document(self) -> None:
        try:
            target = self._source()
        except ValueError:
            self.status_text.set("프로젝트를 먼저 선택하세요")
            return
        candidate = self.document_choice.get()
        if target["kind"] == "local":
            if not self.local_discovery:
                self.status_text.set("프로젝트를 다시 탐색하세요")
                return
            try:
                selected = select_requirements(self.local_discovery, candidate)
                if Path(self.local_discovery["root"]) != Path(target["source"]).absolute():
                    raise ValueError("project root changed")
            except (ValueError, OSError, UnicodeError):
                self.paths["requirements"].set("")
                self.status_text.set("정본 선택 차단 · 후보/경로/변경 사항 확인")
                return
            self.paths["requirements"].set(selected["requirements_path"])
            self.status_text.set(f"로컬 정본 선택: {selected['relative_path']} (NOT VERIFIED)")
            return
        if (not self.remote_discovery or
                self.remote_discovery.get("url") != target["source"] or
                self.remote_discovery.get("ref") != target.get("ref") or
                self.remote_discovery.get("status") not in ("SINGLE_CANDIDATE", "AMBIGUOUS") or
                candidate not in {c["path"] for c in self.remote_discovery["candidates"]}):
            self.status_text.set("원격 정본 선택 불가 · GitHub 설계도 재탐색 필요")
            return
        self.status_text.set(f"공개 GitHub 정본: {candidate} · 검수 실행 대기 (NOT VERIFIED)")

    def _render_and_save(self, audit: dict, root: str, out: str,
                         overwrite: bool) -> None:
        if _FATAL.intersection(audit.get("warnings", [])):
            raise ValueError("B/C contract unavailable")
        html = render_audit_html(audit)
        save_artifacts(audit, html, source_root=root, out_dir=out, overwrite=overwrite)

    def start_audit(self) -> None:
        try:
            target = self._source()
        except (ValueError, OSError):
            messagebox.showerror("입력 필요", "프로젝트 또는 공개 GitHub URL을 확인하세요", parent=self)
            return
        out = self.paths["out"].get().strip()
        if not out or (target["kind"] == "local" and not target.get("requirements")):
            messagebox.showerror("입력 필요", "결과 폴더와 요구사항 문서를 선택하세요", parent=self)
            return
        if self.start_button.instate(["disabled"]):
            return
        chosen = self.document_choice.get().strip() if target["kind"] == "github" and self.mode.get() != "registered" else target.get("requirements")
        # Remote analysis pins the SHA observed at candidate discovery rather
        # than silently adopting a ref that changed before user confirmation.
        pin = None
        expected_doc_sha = None
        if target["kind"] == "github" and self.remote_discovery:
            state = self.remote_discovery
            if state.get("url") != target["source"] or state.get("ref") != target.get("ref"):
                self.status_text.set("GitHub URL/ref가 변경되었습니다 · 정본을 다시 탐색하세요")
                return
            pin = state["commit_sha"]
            if chosen:
                matches = [c for c in state["candidates"] if c["path"] == chosen]
                if not matches:
                    self.status_text.set("선택한 원격 문서가 후보에 없습니다")
                    return
                expected_doc_sha = matches[0]["sha256"]
        self.start_button.state(["disabled"])
        self.status_text.set("선택된 소스만 읽기 전용 분석 중...")
        threading.Thread(target=self._run, args=(target, out, self.allow_overwrite.get(),
                                                  chosen, pin, expected_doc_sha),
                         daemon=True).start()

    def _run(self, target: dict, out: str, overwrite: bool,
             chosen: str | None = None, pin: str | None = None,
             expected_doc_sha: str | None = None) -> None:
        try:
            if target["kind"] == "local":
                root = target["source"]
                doc = Path(target["requirements"])
                if not doc.is_absolute():
                    doc = Path(root) / doc
                audit = build_audit(root, str(doc))
                self._render_and_save(audit, root, out, overwrite)
            else:
                with public_github_snapshot(target["source"], pin or target.get("ref")) as snap:
                    found = discover_local_requirements(snap["root"])
                    selected = select_requirements(found, chosen)
                    if expected_doc_sha and selected["sha256"] != expected_doc_sha:
                        raise ValueError("remote canonical content changed")
                    audit = build_audit(snap["root"], selected["requirements_path"])
                    self._render_and_save(audit, snap["root"], out, overwrite)
            self.messages.put((True, f"상태: {audit['status']} · 저장: audit.json, report.html, manifest.json · P2 NOT_RUN"))
        except (ValueError, OSError, ImportError, UnicodeError, TypeError, KeyError) as exc:
            self.messages.put((False, f"분석 중단: {type(exc).__name__} · 입력/권한/계약 확인 (UNASSESSED)"))

    def register_selected_project(self) -> None:
        if self.mode.get() == "registered":
            self.status_text.set("등록할 로컬 또는 GitHub 모드를 먼저 선택하세요")
            return
        try:
            target = self._source()
            if target["kind"] == "local" and target.get("requirements"):
                root = Path(target["source"]).absolute()
                selected = Path(target["requirements"]).absolute()
                target["requirements"] = selected.relative_to(root).as_posix()
            info = register_project(target, out_dir=self.paths["out"].get().strip())
            self.status_text.set(f"프로젝트 등록 {info['status']} · 사용자 지정 결과 폴더에만 기록")
            self.load_registered_projects()
        except (ValueError, OSError, UnicodeError):
            self.status_text.set("프로젝트 등록 차단 · 결과 폴더/소스 입력 확인")

    def load_registered_projects(self) -> None:
        try:
            self._profiles = load_projects(out_dir=self.paths["out"].get().strip())
        except (ValueError, OSError, UnicodeError):
            self.status_text.set("등록 프로젝트 읽기 차단 · 결과 폴더 확인")
            return
        self._profile_labels = [f"{i+1}. {item['kind']}: {item['source']}"
                                for i, item in enumerate(self._profiles)]
        self.profile_picker.configure(values=self._profile_labels)
        self.profile_choice.set(self._profile_labels[0] if self._profile_labels else "")
        self.status_text.set(f"승인 결과 폴더에서 등록 프로젝트 {len(self._profiles)}개 확인")

    def forget_registered_project(self) -> None:
        selected = self.profile_choice.get()
        if selected not in self._profile_labels:
            self.status_text.set("삭제할 등록 항목을 선택하세요")
            return
        if not messagebox.askyesno("등록 항목 해제", "선택한 프로젝트 등록 기록만 지울까요? 원본/감사 백업은 유지됩니다.",
                                   parent=self):
            return
        try:
            result = unregister_project(self._profiles[self._profile_labels.index(selected)],
                                        out_dir=self.paths["out"].get().strip())
            self.load_registered_projects()
            self.status_text.set("등록 항목 해제 완료" if result else "등록 항목이 이미 없습니다")
        except (ValueError, OSError, UnicodeError):
            self.status_text.set("등록 해제 거부 · 파일 무결성을 확인하세요")

    def start_watch(self) -> None:
        if self._watcher is not None or self._watch_busy:
            self.status_text.set("이미 감시 시작/진행 중입니다")
            return
        try:
            target = self._source()
            out = self.paths["out"].get().strip()
            _safe_output(out, source_root=target["source"] if target["kind"] == "local" else None)
            if target["kind"] == "local":
                if not target.get("requirements"):
                    raise ValueError("local canonical file must be explicitly selected")
                selected = target["requirements"]
                if not Path(selected).is_absolute():
                    selected = str(Path(target["source"]) / selected)
                watcher = LocalChangeWatch(target["source"], selected)
                source_root = target["source"]
            else:
                chosen = self.document_choice.get().strip() if self.mode.get() == "github" else target.get("requirements")
                watcher = PublicGitHubChangeWatch(target["source"], target.get("ref"), chosen or None)
                source_root = None
        except (ValueError, OSError, UnicodeError):
            self.status_text.set("감시 시작 거부 · 선택한 정본/결과 폴더/소스 확인")
            return
        self._watch_generation += 1
        gen = self._watch_generation
        self._watch_busy = True
        self.watch_button.state(["disabled"])
        self.status_text.set("선택 프로젝트 감시를 명시적으로 시작 중...")
        threading.Thread(target=self._watch_start_worker,
                         args=(gen, watcher, out, source_root), daemon=True).start()

    def _watch_start_worker(self, gen: int, watcher, out: str, root: str | None) -> None:
        try:
            started = watcher.start()
            self.events.put(("watch_start", gen, (watcher, out, root, started)))
        except (ValueError, OSError, UnicodeError, TypeError, KeyError) as exc:
            watcher.stop()
            self.events.put(("watch_start", gen, {"error": type(exc).__name__}))

    def stop_watch(self) -> None:
        self._watch_generation += 1
        current = self._watcher
        self._watcher = None
        self._watch_busy = False
        if current is not None:
            current.stop()
        self.watch_button.state(["!disabled"])
        if not self._closing:
            self.status_text.set("감시 중지 · 이후 자동 GitHub 요청 없음")

    def _watch_cycle(self) -> None:
        if self._closing:
            return
        if self._watcher is not None and self._watcher.active and not self._watch_busy:
            self._watch_busy = True
            gen = self._watch_generation
            watcher = self._watcher
            threading.Thread(target=self._watch_tick_worker,
                             args=(gen, watcher, self._watch_out,
                                   self._watch_source_root, self._watch_token),
                             daemon=True).start()
        self.after(1200, self._watch_cycle)

    def _watch_tick_worker(self, gen, watcher, out, root, prior_token) -> None:
        try:
            event = watcher.tick()
            if event["status"] == "CHANGED":
                token = event.get("fingerprint") or event.get("pinned_commit_sha")
                diff = compare_audits(event["previous"], event["current"],
                                      before_snapshot=prior_token, after_snapshot=token)
                # A user might stop the watch while a poll is running.
                if not watcher.active or gen != self._watch_generation:
                    return
                saved = save_delta(diff, out_dir=out, source_root=root)
                event = {"status": "CHANGED", "token": token,
                         "changed_count": diff["changed_count"],
                         "saved": saved["status"]}
            self.events.put(("watch_tick", gen, event))
        except (ValueError, OSError, UnicodeError, TypeError, KeyError):
            watcher.stop()
            self.events.put(("watch_tick", gen, {"status": "PAUSED",
                                                "reason": "HISTORY_OR_SOURCE_UNSAFE"}))

    def show_history(self) -> None:
        try:
            records = load_deltas(out_dir=self.paths["out"].get().strip())
        except (ValueError, OSError, UnicodeError):
            self.status_text.set("이력 읽기 차단 · 결과 폴더/파일 무결성 확인")
            return
        if not records:
            self.status_text.set("저장된 REQ 변경 이력이 없습니다")
            return
        view = tk.Toplevel(self)
        view.title("REQ 후보 변경 이력 · NOT VERIFIED")
        view.geometry("700x440")
        text = tk.Text(view, wrap="word")
        text.pack(fill="both", expand=True)
        for item in records[-15:]:
            text.insert("end", json.dumps(item, ensure_ascii=False, sort_keys=True, indent=2) + "\n\n")
        text.configure(state="disabled")

    def poll(self) -> None:
        if self._closing:
            return
        try:
            success, message = self.messages.get_nowait()
        except queue.Empty:
            pass
        else:
            self.status_text.set(message)
            self.start_button.state(["!disabled"])
            if not success:
                messagebox.showwarning("분석 미완료", message, parent=self)
        for _ in range(30):
            try:
                kind, gen, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "discovery":
                if gen != self._generation:
                    continue
                self._discovering = False
                self.discover_button.state(["!disabled"])
                if isinstance(payload, dict) and "error" not in payload:
                    self.remote_discovery = payload
                    self._show_candidates(payload)
                else:
                    self.status_text.set("원격 설계도 탐색 실패 · 공개 URL/네트워크/한도 확인")
            elif kind == "watch_start":
                if gen != self._watch_generation:
                    if isinstance(payload, tuple):
                        payload[0].stop()
                    continue
                self._watch_busy = False
                self.watch_button.state(["!disabled"])
                if isinstance(payload, tuple):
                    self._watcher, self._watch_out, self._watch_source_root, data = payload
                    self._watch_token = data.get("fingerprint") or data.get("pinned_commit_sha")
                    self.status_text.set("선택한 프로젝트 감시 ON · 변경 전에는 재분석/이력 저장 없음")
                else:
                    self._watcher = None
                    self.status_text.set("감시 시작 실패 · 범위/권한/정본 재확인")
            elif kind == "watch_tick":
                if gen != self._watch_generation:
                    continue
                self._watch_busy = False
                if not isinstance(payload, dict):
                    continue
                if payload.get("status") == "CHANGED":
                    self._watch_token = payload.get("token")
                    self.status_text.set(f"REQ 상태 변경 {payload['changed_count']}개 · 이력 {payload['saved']} · P2 NOT_RUN")
                elif payload.get("status") in ("PAUSED", "STOPPED"):
                    self._watcher = None
                    self.watch_button.state(["!disabled"])
                    self.status_text.set("감시 일시중지 · 정본/경합/출력 파일 점검 (UNASSESSED)")
                elif payload.get("status") == "BACKOFF":
                    self.status_text.set("GitHub 요청 제한 · 안전한 재시도 간격 적용 (NOT VERIFIED)")
        self.after(100, self.poll)

    def _on_close(self) -> None:
        self._closing = True
        self.stop_watch()
        self.destroy()


def main() -> None:
    AuditorApp().mainloop()


if __name__ == "__main__":
    main()
