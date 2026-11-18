"""Validate local read-only input provenance, without traversing or executing source."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DENIED = {".git", ".ssh", "node_modules", ".venv", "venv", "__pycache__", "secrets", "credentials"}


def _safe_path(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("symlink path is not permitted")
    for part in path.parts:
        if part.lower() in _DENIED or part.lower().startswith(".env"):
            raise ValueError("protected input path is not permitted")
    ancestor = path.parent
    while ancestor != ancestor.parent:
        if ancestor.is_symlink():
            raise ValueError("symlink ancestor is not permitted")
        ancestor = ancestor.parent


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=4, check=False, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    except (OSError, subprocess.TimeoutExpired):
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
    if req.stat().st_size > 2_000_000:
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
    return {"schema_version": "reqea.v1", "source_sha": source_sha,
            "source_document": relative, "root": str(root), "requirements_path": str(req),
            "warnings": sorted(set(warnings))}
