"""P2-06 offline HTML browser/CSP regression using only synthetic local inputs."""
from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from playwright.sync_api import sync_playwright
from reqea.core.orchestrator import build_audit, render_audit_html
from reqea.core.output import save_artifacts


with tempfile.TemporaryDirectory() as folder:
    base = Path(folder)
    root = base / "public-synthetic"
    (root / "src").mkdir(parents=True)
    token = "NEVER_RENDER_SYNTHETIC_SECRET_831"
    (root / "src" / "feature.py").write_text(
        "def run():\n    return " + repr(token) + "\n", encoding="utf-8"
    )
    req = root / "requirements.md"
    req.write_text(
        "# REQ-001 Candidate\n"
        "Reference src/feature.py\n"
        "Acceptance criteria:\n- a human must verify behavior\n"
        "# REQ-002 Missing\n"
        "Reference src/absent.py\n"
        "Acceptance criteria:\n- manual acceptance required\n"
        "# REQ-003 - <script>window.injection=1</script>\n"
        "Acceptance criteria:\n- <img src='https://bad.invalid/track'>\n",
        encoding="utf-8",
    )
    out = base / "local-results"
    audit = build_audit(str(root), str(req))
    html = render_audit_html(audit)
    save_artifacts(audit, html, source_root=str(root), out_dir=str(out))
    report = out / "report.html"

    with sync_playwright() as pw:
        chrome = (shutil.which("google-chrome") or shutil.which("chromium")
                  or shutil.which("chromium-browser"))
        browser = pw.chromium.launch(headless=True, executable_path=chrome)
        context = browser.new_context()
        attempts: list[str] = []
        context.route("http://**/*", lambda route: route.abort())
        context.route("https://**/*", lambda route: route.abort())
        page = context.new_page()
        page.on("request", lambda request: attempts.append(request.url)
                if request.url.startswith(("http://", "https://")) else None)
        try:
            page.goto(report.resolve().as_uri(), wait_until="load")
            assert page.title() == "REQ Evidence Audit (static candidates only)"
            ids = [s for s in page.locator("section h2").all_inner_texts()
                   if s.startswith("REQ-")]
            assert len(ids) == 3, ids
            body = page.locator("body").inner_text()
            assert "Static candidates only" in body
            assert "REQ-001" in body and "REQ-002" in body and "REQ-003" in body
            assert token not in body
            assert "<script>" not in body
            assert page.locator("script").count() == 0
            assert not attempts, attempts

            # Challenge the final generated page with an injected executable
            # element; CSP must block execution even if a renderer regresses.
            malicious = out / "csp-challenge.html"
            malicious.write_text(
                html.replace("</body>",
                             "<script>window.__reqeaXssCanary=1</script></body>", 1),
                encoding="utf-8",
            )
            page.goto(malicious.resolve().as_uri(), wait_until="load")
            assert page.evaluate("window.__reqeaXssCanary === undefined")
            assert not attempts, attempts
            print("P2-06 Chromium: offline HTML, 3 REQs, CSP challenge, zero network, "
                  "secret canary not rendered: PASS")
        finally:
            context.close()
            browser.close()
