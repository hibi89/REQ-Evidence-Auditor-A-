"""Secure temporary pinned public-GitHub snapshot for offline A/B/C processing."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Callable
import re
import tempfile

from reqea_codegraph.walk import SOURCE_EXTENSIONS, SKIP_NAMES, SKIP_SUFFIXES
from .github_source import PublicGitHubReader

_MAX_FILES = 200
_MAX_FILE_BYTES = 512_000
_MAX_TOTAL_BYTES = 8_000_000
_DENIED_PARTS = frozenset({"secrets", "secret", "credential", "credentials", "private",
                           ".git", ".ssh", ".aws", "node_modules", "venv", "env",
                           "dist", "build", "__pycache__"})
_WINDOWS_NAMES = frozenset({"con", "prn", "aux", "nul",
                            *(f"com{i}" for i in range(1, 10)),
                            *(f"lpt{i}" for i in range(1, 10))})
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")


def _safe_file(path: object) -> bool:
    if not isinstance(path, str) or not 1 <= len(path) <= 700:
        return False
    if "\\" in path or "//" in path or path.startswith("/") or ":" in path:
        return False
    if any(ord(ch) < 32 or ch in '<>"|?*' for ch in path):
        return False
    parts = path.split("/")
    for part in parts:
        key = part.casefold()
        if (not part or part in (".", "..") or part.startswith(".") or part.endswith((".", " "))
                or key in _DENIED_PARTS or key.startswith((".env", "secret", "credential"))
                or part.split(".", 1)[0].casefold() in _WINDOWS_NAMES):
            return False
    return Path(path).suffix.casefold() in SOURCE_EXTENSIONS and \
        parts[-1].casefold() not in SKIP_NAMES and \
        not parts[-1].casefold().endswith(SKIP_SUFFIXES)


@contextmanager
def public_github_snapshot(url: str, ref: str | None = None, *,
                           before_request: Callable[[], None] | None = None):
    """Yield validated ephemeral source; abort at every new GET when cancelled."""
    reader = PublicGitHubReader(url, ref, before_request=before_request)
    commit_sha, tree_sha, entries = reader.pinned_tree()
    planned: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    total = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("invalid GitHub tree record")
        path = entry.get("path")
        if not isinstance(path, str) or len(path) > 700:
            raise ValueError("invalid GitHub tree path")
        if entry.get("type") == "tree":
            continue
        # Hidden/unsafe material is never fetched. Links/submodules in allowed
        # scope are rejected, not followed.
        if not _safe_file(path):
            continue
        if entry.get("type") != "blob" or entry.get("mode") not in ("100644", "100755"):
            raise ValueError("unsafe GitHub tree entry")
        lower = path.casefold()
        if lower in seen:
            raise ValueError("casefold-colliding GitHub paths")
        seen.add(lower)
        sha, size = entry.get("sha"), entry.get("size")
        if (not isinstance(sha, str) or not _SHA.fullmatch(sha) or
                type(size) is not int or size < 0 or size > _MAX_FILE_BYTES):
            raise ValueError("invalid or oversized source blob")
        total += size
        planned.append((path, sha, size))
        if len(planned) > _MAX_FILES or total > _MAX_TOTAL_BYTES:
            raise ValueError("GitHub snapshot exceeds bounded scope")
    if not planned:
        raise ValueError("no eligible source files in pinned snapshot")
    with tempfile.TemporaryDirectory(prefix="reqea-public-gh-") as temporary:
        root = Path(temporary) / "source"
        root.mkdir()
        for rel, sha, size in sorted(planned):
            payload = reader.read_blob(sha, max_bytes=_MAX_FILE_BYTES)
            # STOP while one GET was in flight must discard its result, not
            # write a new temporary source file after cancellation.
            if before_request is not None:
                before_request()
            if len(payload) != size:
                raise ValueError("GitHub tree/blob byte sizes disagree")
            destination = root.joinpath(*rel.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as handle:
                handle.write(payload)
        if before_request is not None:
            before_request()
        yield {"root": str(root), "owner": reader.owner, "repository": reader.repo,
               "requested_ref": reader.requested_ref, "commit_sha": commit_sha,
               "tree_sha": tree_sha, "file_count": len(planned),
               "source_sha": "UNVERIFIED", "verification_status": "NOT_RUN"}
