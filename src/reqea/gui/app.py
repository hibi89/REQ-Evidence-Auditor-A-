"""Tk GUI for explicit local, read-only REQ evidence auditing."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from reqea.core.orchestrator import build_audit, render_audit_html
from reqea.core.output import save_artifacts


class AuditorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("REQ Evidence Auditor — Local")
        self.minsize(680, 370)
        self.paths = {"repo": tk.StringVar(), "requirements": tk.StringVar(), "out": tk.StringVar()}
        self.status_text = tk.StringVar(value="프로젝트와 요구사항 파일을 선택하세요.")
        self.allow_overwrite = tk.BooleanVar(value=False)
        self.messages: queue.Queue[tuple[bool, str]] = queue.Queue()
        content = ttk.Frame(self, padding=18)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="REQ Evidence Auditor", font=("Arial", 18, "bold")).pack(anchor="w")
        ttk.Label(content, text="정적 근거 후보만 생성 · 코드 실행/네트워크 전송 없음 · 검증 PASS 아님").pack(anchor="w", pady=(2, 16))
        entries = (("repo", "프로젝트 폴더", True), ("requirements", "요구사항 파일", False), ("out", "결과 저장 폴더 (프로젝트 외부)", True))
        for name, description, folder in entries:
            line = ttk.Frame(content)
            line.pack(fill="x", pady=5)
            ttk.Label(line, text=description, width=31).pack(side="left")
            ttk.Entry(line, textvariable=self.paths[name]).pack(side="left", fill="x", expand=True)
            ttk.Button(line, text="찾기", command=lambda k=name, f=folder: self.choose(k, f)).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(content, text="기존 결과 파일 덮어쓰기 명시적으로 허용", variable=self.allow_overwrite).pack(anchor="w", pady=(12, 5))
        self.start_button = ttk.Button(content, text="로컬 분석 실행", command=self.start_audit)
        self.start_button.pack(anchor="w", pady=(5, 12))
        ttk.Label(content, textvariable=self.status_text, wraplength=620).pack(fill="x", anchor="w")
        self.after(100, self.poll)

    def choose(self, key: str, folder: bool) -> None:
        selected = filedialog.askdirectory(parent=self) if folder else filedialog.askopenfilename(
            parent=self, filetypes=[("Requirements", "*.md *.markdown *.json"), ("All files", "*.*")])
        if selected:
            self.paths[key].set(selected)

    def start_audit(self) -> None:
        values = {name: entry.get().strip() for name, entry in self.paths.items()}
        if not all(values.values()):
            messagebox.showerror("입력 필요", "세 경로를 모두 선택하세요.", parent=self)
            return
        self.start_button.state(["disabled"])
        self.status_text.set("읽기 전용 정적 분석 중...")
        threading.Thread(target=self._run, args=(values, self.allow_overwrite.get()), daemon=True).start()

    def _run(self, values: dict[str, str], overwrite: bool) -> None:
        try:
            audit = build_audit(values["repo"], values["requirements"])
            if any(w in audit.get("warnings", []) for w in ("required_B_or_C_module_unavailable",
                    "B_contract_or_SHA_mismatch", "C_contract_or_SHA_mismatch",
                    "C_invalid_or_untrusted_status", "C_invalid_finding_status",
                    "C_invalid_warning_contract", "analysis_failed_without_verified_evidence")):
                self.messages.put((False, "B/C 계약/모듈 미준비: UNASSESSED (결과 저장 없음)"))
                return
            html = render_audit_html(audit)
            info = save_artifacts(audit, html, source_root=values["repo"],
                                  out_dir=values["out"], overwrite=overwrite)
            self.messages.put((True, f"상태: {audit['status']} · 저장: {', '.join(info['artifacts'])} · P2 NOT_RUN"))
        except (ValueError, OSError, ImportError, UnicodeError, TypeError, KeyError) as exc:
            self.messages.put((False, f"분석 중단: {type(exc).__name__} · 입력·권한·모듈을 확인하세요 (UNASSESSED)"))

    def poll(self) -> None:
        try:
            success, message = self.messages.get_nowait()
        except queue.Empty:
            pass
        else:
            self.status_text.set(message)
            self.start_button.state(["!disabled"])
            if not success:
                messagebox.showwarning("분석 미완료", message, parent=self)
        self.after(100, self.poll)


def main() -> None:
    AuditorApp().mainloop()


if __name__ == "__main__":
    main()
