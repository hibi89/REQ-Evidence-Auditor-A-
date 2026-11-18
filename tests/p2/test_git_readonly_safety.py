"""P2 regression: examining an untrusted Git worktree must not execute hooks."""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from reqea.core.source_ref import _git, inspect_local_source


@unittest.skipUnless(shutil.which("git"), "git executable unavailable")
class GitReadOnlySafety(unittest.TestCase):
    def test_git_invocation_overrides_untrusted_fsmonitor_config(self):
        with patch("reqea.core.source_ref.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            _git(Path("."), "status", "--porcelain", "--untracked-files=all")
        command = run.call_args.args[0]
        self.assertIn(["-c", "core.fsmonitor=false"],
                      [command[i:i + 2] for i in range(len(command) - 1)])

    @unittest.skipUnless(os.name == "posix", "POSIX executable hook fixture")
    def test_untrusted_repository_cannot_execute_fsmonitor_hook(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "synthetic-checkout"
            root.mkdir()
            requirements = root / "REQ.md"
            requirements.write_text("# REQ-001 synthetic\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "REQ.md"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=P2 Fixture",
                            "-c", "user.email=p2-fixture@example.invalid",
                            "commit", "-qm", "synthetic baseline"], check=True)
            marker = base / "UNTRUSTED_HOOK_EXECUTED"
            hook = base / "fsmonitor.sh"
            hook.write_text("#!/bin/sh\nprintf triggered > "
                            + shlex.quote(str(marker)) + "\nexit 0\n",
                            encoding="utf-8")
            hook.chmod(0o700)
            subprocess.run(["git", "-C", str(root), "config", "core.fsmonitor",
                            str(hook)], check=True)
            result = inspect_local_source(str(root), str(requirements))
            self.assertFalse(marker.exists(), "Git provenance check executed untrusted hook")
            self.assertNotEqual(result["source_sha"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
