"""Validate local read-only input provenance, without traversing or executing source."""
from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DENIED = {".git", ".ssh", "node_modules", ".venv", "venv", "__pycache__", "secrets", "credentials"}


def _safe_path(path: Path) -> None:
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for part in path.parts:
        if part.lower() in _DENIED or part.lower().startswith(".env"):
            raise ValueError("protected input path is not permitted")
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & reparse:
            raise ValueError("input symlink or junction path is not permitted")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        # Untrusted repository config may define an executable core.fsmonitor hook.
        # Disable it even for read-only git status/rev-parse probes.
        return subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                               "-C", str(root), *args],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=4, check=False, encoding="utf-8", errors="strict",
                              env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, 1, "", "git_unavailable")


def inspect_local_source(repo_root: str, requirements_path: str, *, baseline_sha: str | None = None) -> dict:
    """Return frozen SHA when HEAD is unambiguous and checkout is clean.

    This routine never clones, fetches, imports source or writes inside the repo.
    """
    if not isinstance(repo_root, str) or not isinstance(requirements_path, str):
        raise ValueError("paths must be strings")
    for raw in (repo_root, requirements_path):
        if raw.startswith(("\\\\", "//")) or "\x00" in raw:
            raise ValueError("UNC or malformed path is not permitted")
    root_input, file_input = Path(repo_root).absolute(), Path(requirements_path).absolute()
    _safe_path(root_input)
    _safe_path(file_input)
    if not root_input.is_dir() or not file_input.is_file():
        raise ValueError("source root or requirement file does not exist")
    root, req = root_input.resolve(strict=True), file_input.resolve(strict=True)
    try:
        relative = req.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("requirements file must be inside source root") from exc
    if not relative or any(part in _DENIED or part.startswith(".env") for part in relative.lower().split("/")):
        raise ValueError("protected requirements path")
    req_meta = req.lstat()
    # Requirements are an explicit trust input: reject hardlinks to files outside
    # the selected tree before parsing potentially private contents.
    if req_meta.st_nlink > 1 or not stat.S_ISREG(req_meta.st_mode):
        raise ValueError("hardlinked or nonregular requirements file is prohibited")
    if req_meta.st_size > 2_000_000:
        raise ValueError("requirements file exceeds 2 MB limit")
    if baseline_sha is not None and (not isinstance(baseline_sha, str) or not _SHA.fullmatch(baseline_sha.lower())):
        raise ValueError("baseline_sha must be a 40-hex commit")
    warnings: list[str] = []
    source_sha = "UNVERIFIED"
    head = _git(root, "rev-parse", "--verify", "HEAD")
    top = _git(root, "rev-parse", "--show-toplevel")
    if head.returncode == 0 and _SHA.fullmatch(head.stdout.strip().lower()) and top.returncode == 0 and Path(top.stdout.strip()).resolve() == root:
        candidate = head.stdout.strip().lower()
        status = _git(root, "status", "--porcelain", "--untracked-files=all")
        if baseline_sha is not None and candidate != baseline_sha.lower():
            warnings.append("baseline_sha_mismatch")
        elif status.returncode != 0 or status.stdout.strip():
            warnings.append("working_tree_dirty")
        else:
            source_sha = candidate
    else:
        warnings.append("git_head_unavailable_or_nested_root")
    result = {"schema_version": "reqea.v1", "source_sha": source_sha,
              "source_document": relative, "root": str(root), "requirements_path": str(req),
              "_requirements_identity": _file_identity(req_meta),
              "warnings": sorted(set(warnings))}
    # Bind the later parser read to these exact bytes as well as filesystem IDs.
    # Some Windows metadata aliases cannot reliably detect a same-sized rename.
    result["_requirements_digest"] = hashlib.sha256(read_checked_requirements(result)).digest()
    return result



def source_snapshot_still_clean(source: dict) -> bool:
    """Reject an exact-HEAD claim if the worktree changes during analysis.

    This is a second cooperative Git snapshot check, not a guarantee against
    a malicious change-and-revert race or filesystem power loss.
    """
    sha = source.get("source_sha")
    if sha == "UNVERIFIED":
        return True  # No exact Git snapshot was asserted in the first place.
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        return False
    try:
        root = Path(source["root"])
        _safe_path(root)
        head = _git(root, "rev-parse", "--verify", "HEAD")
        top = _git(root, "rev-parse", "--show-toplevel")
        status = _git(root, "status", "--porcelain", "--untracked-files=all")
        return (head.returncode == 0 and top.returncode == 0
                and status.returncode == 0
                and head.stdout.strip().lower() == sha
                and Path(top.stdout.strip()).resolve() == root
                and not status.stdout.strip())
    except (ValueError, OSError, KeyError, TypeError):
        return False


def source_index_is_tracked_at_head(source: dict, code_index: dict) -> bool:
    """Never attach a clean HEAD to ignored or untracked scanned source files.

    Git status excludes paths ignored by .gitignore, but the static index scans
    allowed source extensions even when ignored. Those bytes are not guaranteed
    to exist at HEAD; all indexed evidence and the selected REQ must be tracked
    before a commit SHA can be reported as provenance.
    """
    if source.get("source_sha") == "UNVERIFIED":
        return True  # Caller already labels provenance as unverified.
    try:
        files = code_index["files"]
        if not isinstance(files, list):
            return False
        root = Path(source["root"])
        _safe_path(root)
        listed = _git(root, "ls-files", "--cached", "--full-name", "-z")
        if listed.returncode != 0:
            return False
        paths = set(listed.stdout.split("\0"))
        req = source["source_document"]
        if not isinstance(req, str) or req not in paths:
            return False
        return all(isinstance(item, dict) and isinstance(item.get("path"), str)
                   and item["path"] in paths for item in files)
    except (OSError, KeyError, TypeError, ValueError):
        return False


def _file_identity(st: os.stat_result) -> tuple[int, int, int, int]:
    """Device, inode, byte count and nanosecond write time of a trusted regular file."""
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def read_checked_requirements(source: dict) -> bytes:
    """Read a bounded exact input handle, refusing replacement after provenance check.

    Never import, execute, follow a newly inserted link, or read a changed inode.
    A concurrent rename/overwrite forces an explicit failed audit rather than
    silently attributing different REQ bytes to the original source SHA.
    """
    path = Path(source["requirements_path"])
    root = Path(source["root"])
    expected = source.get("_requirements_identity")
    if not isinstance(expected, tuple) or len(expected) != 4:
        raise ValueError("requirements identity is unavailable")
    try:
        path.relative_to(root)
        _safe_path(path)
        before_path = path.lstat()
    except (OSError, ValueError) as exc:
        raise ValueError("requirements path changed before read") from exc
    if not stat.S_ISREG(before_path.st_mode) or before_path.st_nlink != 1 or (
            _file_identity(before_path) != expected):
        raise ValueError("requirements changed before read")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("requirements could not be safely opened") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or (
                _file_identity(opened) != expected):
            raise ValueError("requirements identity changed during open")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(2_000_001)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    _safe_path(path)
    try:
        now = path.lstat()
    except OSError as exc:
        raise ValueError("requirements vanished during read") from exc
    if (_file_identity(after) != expected or _file_identity(now) != expected
            or not stat.S_ISREG(now.st_mode) or now.st_nlink != 1):
        raise ValueError("requirements changed during read")
    if len(data) > 2_000_000:
        raise ValueError("requirements too large")
    expected_digest = source.get("_requirements_digest")
    if expected_digest is not None and hashlib.sha256(data).digest() != expected_digest:
        raise ValueError("requirements contents changed during audit")
    return data
