"""Opt-in by this integration CI: read the *already public* REQEA-A source at its own SHA.

No credentials, secrets, customer files, remote writes, cloning or hooks.
Verifies one pinned public A blob plus an ephemeral, multi-blob B snapshot.
This smoke never processes customer files and is not independent auditing.
"""
from __future__ import annotations

import os
from pathlib import Path
import re

from reqea.core.github_source import GitHubRateLimitError, PublicGitHubReader
from reqea.core.snapshot import public_github_snapshot

_SELF_REPO = "https://github.com/hibi89/REQ-Evidence-Auditor-A-"
_PUBLIC_B_REPO = "https://github.com/hibi89/REQ-Evidence-Auditor-B-"
_PUBLIC_B_SHA = "f9a94c26db445badae6c6e476eb6d40246f9ff4c"


def main() -> int:
    sha = os.environ.get("REQEA_PUBLIC_SELF_SHA", "")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise ValueError("integration commit SHA is not a 40-hex Git ID")
    reader = PublicGitHubReader(_SELF_REPO, ref=sha)
    try:
        # Exercise the actual public ref API before pinned tree/blob retrieval.
        if reader.head_commit_sha() != sha.lower():
            raise AssertionError("public GitHub ref did not resolve to exact CI SHA")
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

        # A second, small *owned and already public* source verifies the actual
        # bounded tree->blob->temporary filesystem path (not a mocked API).
        temporary_root: Path | None = None
        with public_github_snapshot(_PUBLIC_B_REPO, _PUBLIC_B_SHA) as snapshot:
            if snapshot["commit_sha"] != _PUBLIC_B_SHA:
                raise AssertionError("public B snapshot is not pinned")
            if snapshot["source_sha"] != "UNVERIFIED":
                raise AssertionError("source snapshot is not an independent certification")
            if not 8 <= snapshot["file_count"] <= 40:
                raise AssertionError("public B snapshot is incomplete or unbounded")
            temporary_root = Path(snapshot["root"])
            walk = temporary_root / "src" / "reqea_codegraph" / "walk.py"
            if not walk.is_file() or b"def scan_tree(" not in walk.read_bytes():
                raise AssertionError("public B bounded snapshot lost a code blob")
        if temporary_root is None or temporary_root.exists():
            raise AssertionError("public B temporary source was not removed")
    except ValueError as exc:
        # CI runners share unauthenticated GitHub API quotas. Skipping due to
        # external 403/429/offline is explicitly NOT success and is reported
        # separately from the synthetic test results.
        if isinstance(exc, GitHubRateLimitError) or str(exc) == "GitHub API network unavailable":
            print("LIVE_PUBLIC_GITHUB_P2_SKIP: quota/network unavailable; NOT_VERIFIED")
            return 0
        raise
    print("LIVE_PUBLIC_GITHUB_P2_PASS: immutable self-repository tree and one blob; "
          "read-only; source contents suppressed; no upload")
    print("LIVE_PUBLIC_B_SNAPSHOT_P2_PASS: pinned multi-blob temporary source removed")
    print("PINNED_COMMIT_SHA=" + pinned_sha)
    print("PINNED_TREE_SHA=" + tree_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
