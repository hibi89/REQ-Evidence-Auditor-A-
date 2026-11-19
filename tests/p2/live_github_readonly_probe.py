"""Opt-in by this integration CI: read the *already public* REQEA-A source at its own SHA.

No credentials, secrets, customer files, remote writes, cloning or hooks.
Only reads one pinned public source blob. This P2 smoke is not an audit of
other users' repositories and is distinct from mocked unit tests.
"""
from __future__ import annotations

import os
import re

from reqea.core.github_source import PublicGitHubReader


def main() -> int:
    sha = os.environ.get("REQEA_PUBLIC_SELF_SHA", "")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise ValueError("integration commit SHA is not a 40-hex Git ID")
    reader = PublicGitHubReader(
        "https://github.com/hibi89/REQ-Evidence-Auditor-A-", ref=sha
    )
    try:
        pinned_sha, tree_sha, entries = reader.pinned_tree()
        if pinned_sha != sha.lower():
            raise AssertionError("remote commit does not match exact CI checkout")
        source = [e for e in entries if e.get("path") == "src/reqea/cli.py"]
        if len(source) != 1 or source[0].get("type") != "blob":
            raise AssertionError("pinned public tree lacks exactly one CLI source")
        entry = source[0]
        content = reader.read_blob(entry["sha"], max_bytes=512_000)
        if len(content) != entry["size"] or b"def main(" not in content:
            raise AssertionError("pinned CLI content failed expected read-only smoke")
    except ValueError as exc:
        # CI runners share unauthenticated GitHub API quotas. Skipping due to
        # external 403/429/offline is explicitly NOT success and is reported
        # separately from the synthetic test results.
        if str(exc) in ("GitHub rate limited or access denied",
                        "GitHub API network unavailable"):
            print("LIVE_PUBLIC_GITHUB_P2_SKIP: quota/network unavailable; NOT_VERIFIED")
            return 0
        raise
    print("LIVE_PUBLIC_GITHUB_P2_PASS: immutable self-repository tree and one blob; "
          "read-only; source contents suppressed; no upload")
    print("PINNED_COMMIT_SHA=" + pinned_sha)
    print("PINNED_TREE_SHA=" + tree_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
