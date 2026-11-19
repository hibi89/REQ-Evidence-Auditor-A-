"""Explicit, content-bound selection of one discovered requirements candidate."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .source_ref import inspect_local_source, read_checked_requirements


def select_requirements(discovery: dict, path: str | None = None) -> dict:
    """Resolve exactly one immutable discovery candidate or fail closed.

    Multiple documents are NEVER auto-selected. A human-selected path is
    accepted only when present in the discovered list and its bytes still match.
    """
    if not isinstance(discovery, dict) or discovery.get("status") in ("BLOCKED", "NO_CANDIDATE"):
        raise ValueError("discovery incomplete; choose another root or repair documents")
    candidates = discovery.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("no usable requirements candidates")
    if path is None and len(candidates) != 1:
        raise ValueError("ambiguous requirements: explicit selection is required")
    if path is not None and (not isinstance(path, str) or not path):
        raise ValueError("invalid selected requirements path")
    chosen = [c for c in candidates if isinstance(c, dict)
              and c.get("path") == (path if path is not None else candidates[0]["path"])]
    if len(chosen) != 1:
        raise ValueError("selected document is not a discovered candidate")
    candidate = chosen[0]
    relative = candidate["path"]
    if not isinstance(relative, str) or "\\" in relative or relative.startswith("/") or any(
            p in ("", ".", "..") for p in relative.split("/")):
        raise ValueError("unsafe selected document")
    root = Path(discovery["root"])
    source = inspect_local_source(str(root), str(root.joinpath(*relative.split("/"))))
    actual = hashlib.sha256(read_checked_requirements(source)).hexdigest()
    if actual != candidate.get("sha256"):
        raise ValueError("requirements document changed since discovery")
    return {"requirements_path": str(root.joinpath(*relative.split("/"))),
            "relative_path": relative, "sha256": actual,
            "source_sha": source["source_sha"], "status": "SELECTED_UNVERIFIED"}
