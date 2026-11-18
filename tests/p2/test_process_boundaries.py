"""Cross-process local-only P2 evidence for interrupted artifact transactions."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from reqea.core.orchestrator import build_audit, render_audit_html
from reqea.core.output import save_artifacts


# Child scripts execute on synthetic local fixture paths only. os._exit skips
# Python finally blocks and models abrupt process death (NOT a power failure).
_ABRUPT_CHILD = r"""
import os
from pathlib import Path
import sys
from reqea.core.orchestrator import build_audit, render_audit_html
from reqea.core import output

root, req, out, mode = sys.argv[1:]
audit = build_audit(root, req)
audit["tool_version"] = "SYNTHETIC_ABRUPT_CHILD"
html = render_audit_html(audit)

if mode == "overwrite":
    original = output.os.replace
    def kill_after_first(src, dst, *args, **kwargs):
        result = original(src, dst, *args, **kwargs)
        if Path(dst).name == "audit.json":
            os._exit(73)
        return result
    output.os.replace = kill_after_first
    output.save_artifacts(audit, html, source_root=root, out_dir=out, overwrite=True)
else:
    original = output.os.link
    def kill_after_first(src, dst, *args, **kwargs):
        result = original(src, dst, *args, **kwargs)
        if Path(dst).name == "audit.json":
            os._exit(73)
        return result
    output.os.link = kill_after_first
    output.save_artifacts(audit, html, source_root=root, out_dir=out)
raise RuntimeError("expected synthetic abrupt termination")
"""

_PAUSED_CHILD = r"""
import os
from pathlib import Path
import sys
import time
from reqea.core.orchestrator import build_audit, render_audit_html
from reqea.core import output

root, req, out, ready, release = sys.argv[1:]
audit = build_audit(root, req)
html = render_audit_html(audit)
original = output._regular_output_target
entered = False
def block_after_lock(target):
    global entered
    if not entered:
        entered = True
        Path(ready).write_bytes(b"LOCK_ACQUIRED")
        deadline = time.monotonic() + 15
        while not Path(release).exists():
            if time.monotonic() >= deadline:
                os._exit(74)
            time.sleep(0.02)
    return original(target)
output._regular_output_target = block_after_lock
output.save_artifacts(audit, html, source_root=root, out_dir=out)
"""


def _child_environment() -> dict[str, str]:
    env = dict(os.environ)
    repo_root = Path(__file__).resolve().parents[2]
    source_dir = str(repo_root / "src")
    env["PYTHONPATH"] = source_dir + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _fixture(base: Path) -> tuple[Path, Path, Path]:
    root = base / "project"
    root.mkdir()
    (root / "sample.py").write_text("def answer(): return 42\n", encoding="utf-8")
    req = root / "REQ.md"
    req.write_text(
        "# REQ-001 inspect\nReference sample.py\nAcceptance criteria:\n- exists\n",
        encoding="utf-8",
    )
    return root, req, base / "results"


class CrossProcessOutputBoundaries(unittest.TestCase):
    def test_abrupt_process_exit_preserves_manual_recovery_evidence(self):
        for mode in ("fresh", "overwrite"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                base = Path(d)
                root, req, out = _fixture(base)
                original_source = {p.name: p.read_bytes() for p in root.iterdir()}
                original_outputs: dict[str, bytes] = {}
                if mode == "overwrite":
                    audit = build_audit(str(root), str(req))
                    html = render_audit_html(audit)
                    save_artifacts(audit, html, source_root=str(root), out_dir=str(out))
                    original_outputs = {
                        p.name: p.read_bytes() for p in out.iterdir()
                    }
                out.mkdir(exist_ok=True)
                unrelated = out / "unrelated-owner-data.txt"
                unrelated.write_bytes(b"DO_NOT_TOUCH")
                p = subprocess.run(
                    [sys.executable, "-c", _ABRUPT_CHILD, str(root), str(req),
                     str(out), mode],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=20,
                    env=_child_environment(),
                    check=False,
                )
                self.assertEqual(
                    p.returncode, 73,
                    f"abrupt child did not reach guarded write: {p.stderr[-800:]!r}",
                )
                self.assertTrue((out / ".reqea-transaction.lock").is_dir())
                self.assertEqual(unrelated.read_bytes(), b"DO_NOT_TOUCH")
                self.assertEqual(
                    {p.name: p.read_bytes() for p in root.iterdir()},
                    original_source,
                )
                if mode == "overwrite":
                    self.assertEqual(
                        (out / "report.html").read_bytes(),
                        original_outputs["report.html"],
                    )
                    backups = [
                        p.read_bytes() for p in out.iterdir()
                        if p.name.startswith(".reqea-prev-") and p.is_file()
                    ]
                    self.assertIn(
                        original_outputs["audit.json"], backups,
                        "killed overwrite must preserve old audit bytes",
                    )
                else:
                    self.assertTrue((out / "audit.json").is_file())
                    self.assertFalse((out / "report.html").exists())
                retry_audit = build_audit(str(root), str(req))
                retry_html = render_audit_html(retry_audit)
                observed = {p.name: p.read_bytes() for p in out.iterdir()
                            if p.is_file()}
                with self.assertRaisesRegex(FileExistsError, "transaction"):
                    save_artifacts(
                        retry_audit, retry_html, source_root=str(root),
                        out_dir=str(out), overwrite=True,
                    )
                self.assertEqual(
                    {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()},
                    observed,
                    "retry must not mutate partial crash evidence",
                )

    def test_two_independent_processes_cannot_commit_same_output(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root, req, out = _fixture(base)
            ready = base / "child-ready"
            release = base / "child-release"
            child = subprocess.Popen(
                [sys.executable, "-c", _PAUSED_CHILD, str(root), str(req),
                 str(out), str(ready), str(release)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_child_environment(),
            )
            try:
                deadline = time.monotonic() + 12
                while not ready.exists() and child.poll() is None:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.02)
                self.assertTrue(
                    ready.exists(),
                    "independent writer failed to acquire its lock",
                )
                self.assertEqual(ready.read_bytes(), b"LOCK_ACQUIRED")
                self.assertIsNone(child.poll())
                audit = build_audit(str(root), str(req))
                html = render_audit_html(audit)
                with self.assertRaisesRegex(FileExistsError, "transaction"):
                    save_artifacts(
                        audit, html, source_root=str(root),
                        out_dir=str(out), overwrite=True,
                    )
                release.write_bytes(b"CONTINUE")
                _, stderr = child.communicate(timeout=15)
                self.assertEqual(child.returncode, 0, stderr[-800:])
                self.assertFalse((out / ".reqea-transaction.lock").exists())
                self.assertEqual(
                    sorted(p.name for p in out.iterdir()),
                    ["audit.json", "manifest.json", "report.html"],
                )
            finally:
                release.write_bytes(b"RELEASE_FOR_CLEANUP")
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()
