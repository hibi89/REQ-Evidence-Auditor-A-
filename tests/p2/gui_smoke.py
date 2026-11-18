"""Exercise Tk GUI callback/event-loop with synthetic local files (not visual UX)."""
from pathlib import Path
import tempfile
import time
from reqea.gui.app import AuditorApp

with tempfile.TemporaryDirectory() as d:
    base = Path(d)
    repo = base / "synthetic GUI 한글"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "unit.py").write_bytes(b"def unit():\n    return 1\n")
    req = repo / "requirements.md"
    req.write_text("# REQ-001 UI synthetic\nReference src/unit.py\nAcceptance criteria:\n- function exists\n", encoding="utf-8")
    out = base / "output"
    app = AuditorApp()
    app.withdraw()
    try:
        app.paths["repo"].set(str(repo))
        app.paths["requirements"].set(str(req))
        app.paths["out"].set(str(out))
        app.start_audit()
        limit = time.monotonic() + 20
        while time.monotonic() < limit:
            app.update()
            if (out / "audit.json").exists() and str(app.start_button.cget("state")) != "disabled":
                break
            time.sleep(0.05)
        assert (out / "audit.json").is_file(), "GUI did not write audit.json"
        assert (out / "report.html").is_file(), "GUI did not write report.html"
        assert "저장:" in app.status_text.get(), app.status_text.get()
        print("GUI Tk callback/event loop synthetic PASS; not Windows 11 visual acceptance")
    finally:
        app.destroy()
