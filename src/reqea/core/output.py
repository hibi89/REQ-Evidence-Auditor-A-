"""Write only approved, outside-repository deterministic audit artifacts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


def _check_no_symlinks(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("output symlink path is prohibited")


def save_artifacts(audit: dict, html: str, *, source_root: str, out_dir: str,
                   overwrite: bool = False) -> dict:
    if not isinstance(audit, dict) or not isinstance(html, str) or not isinstance(out_dir, str):
        raise ValueError("invalid artifact inputs")
    if out_dir.startswith(("\\\\", "//")) or not out_dir or "\x00" in out_dir:
        raise ValueError("unsafe output directory")
    root = Path(source_root).resolve(strict=True)
    destination = Path(out_dir).absolute()
    _check_no_symlinks(destination)
    resolved = destination.resolve(strict=False)
    if resolved == root or root in resolved.parents:
        raise ValueError("output must be outside scanned repository")
    files = {
        "audit.json": (json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        "report.html": html.encode("utf-8"),
    }
    manifest = {"schema_version": "reqea.v1", "source_sha": audit.get("source_sha", "UNVERIFIED"),
                "policy_sha": audit.get("policy_sha", "UNVERIFIED"),
                "tool_version": audit.get("tool_version", "0.1.0-p1"),
                "verification_status": "NOT_RUN", "artifacts":
                {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    # Manifest carries sanitized warning codes, not arbitrary source paths or values.
    raw_warnings = audit.get("warnings", [])
    if not isinstance(raw_warnings, list):
        raise ValueError("invalid audit warnings contract")
    manifest["status"] = audit.get("status", "UNASSESSED")
    manifest["warnings"] = sorted({
        re.sub(r"[^A-Za-z0-9_]", "_", w.split(":", 1)[0])[:64]
        for w in raw_warnings if isinstance(w, str)
    })[:2049]
    files["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if destination.exists() and not destination.is_dir():
        raise ValueError("output is not a directory")
    destination.mkdir(parents=True, exist_ok=True)
    _check_no_symlinks(destination)
    if not overwrite and any((destination / name).exists() for name in files):
        raise FileExistsError("audit artifacts already exist: use --overwrite explicitly")
    temps: list[Path] = []
    try:
        for name, data in files.items():
            fd, temp = tempfile.mkstemp(prefix=".reqea-", dir=destination)
            temps.append(Path(temp))
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        for (name, _), temp in zip(files.items(), temps):
            target = destination / name
            if overwrite:
                os.replace(temp, target)
            else:
                os.link(temp, target)  # exclusive/no clobber, same filesystem
                temp.unlink()
    finally:
        for temp in temps:
            temp.unlink(missing_ok=True)
    return {"artifacts": sorted(files), "source_sha": manifest["source_sha"],
            "verification_status": "NOT_RUN"}
