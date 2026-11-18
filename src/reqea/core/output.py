"""Write only approved, outside-repository deterministic audit artifacts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path


def _check_no_symlinks(path: Path) -> None:
    """Reject symlinks and Windows junction/reparse ancestors, even at destination."""
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue  # Destination need not exist yet.
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & reparse:
            raise ValueError("output symlink or junction path is prohibited")


def _regular_output_target(path: Path) -> bool:
    """Return whether a safe regular result exists; reject links and special files."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & reparse):
        raise ValueError("unsafe existing output target")
    return True


def _reserved_link_path(destination: Path, prefix: str) -> Path:
    """Create a unique reserved local name, then link with no-clobber semantics."""
    fd, raw = tempfile.mkstemp(prefix=prefix, dir=destination)
    os.close(fd)
    path = Path(raw)
    path.unlink()
    return path


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
    # Snapshot the three explicitly approved result names before touching any.
    # Reject symlinks, Windows reparse points and nonregular targets even with
    # --overwrite, rather than silently replacing an untrusted filesystem entry.
    existing = {name: _regular_output_target(destination / name) for name in files}
    if not overwrite and any(existing.values()):
        raise FileExistsError("audit artifacts already exist: use --overwrite explicitly")
    temps: list[Path] = []
    links: list[tuple[Path, Path]] = []
    backups: dict[str, Path] = {}
    installed: list[tuple[str, Path, Path]] = []
    holds: list[Path] = []
    retain_backups: set[Path] = set()
    try:
        for name, data in files.items():
            fd, temp = tempfile.mkstemp(prefix=".reqea-", dir=destination)
            temps.append(Path(temp))
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        if overwrite:
            # Back up original inodes via same-directory hardlinks; originals
            # remain available even after os.replace swaps each target name.
            for name, had_original in existing.items():
                if had_original:
                    target = destination / name
                    backup = _reserved_link_path(destination, ".reqea-prev-")
                    os.link(target, backup)
                    backups[name] = backup
                    if not os.path.samefile(target, backup):
                        raise ValueError("output target changed while backing up")
        for (name, _), temp in zip(files.items(), temps):
            target = destination / name
            _check_no_symlinks(destination)
            if overwrite:
                present = _regular_output_target(target)
                if existing[name]:
                    if not present or not os.path.samefile(target, backups[name]):
                        raise ValueError("output changed concurrently before overwrite")
                elif present:
                    raise ValueError("new output appeared concurrently")
                # A second local hardlink proves which target inode this
                # invocation installed, avoiding rollback of external changes.
                hold = _reserved_link_path(destination, ".reqea-new-")
                os.link(temp, hold)
                holds.append(hold)
                os.replace(temp, target)
                installed.append((name, target, hold))
            else:
                os.link(temp, target)  # exclusive/no existing file clobbered
                links.append((target, temp))
    except BaseException:
        if overwrite:
            for name, target, hold in reversed(installed):
                previous = backups.get(name)
                try:
                    if os.path.samefile(target, hold):
                        if previous is not None:
                            os.replace(previous, target)
                        else:
                            target.unlink()
                    elif previous is not None:
                        # A third party changed this target: keep the old bytes.
                        retain_backups.add(previous)
                except (FileNotFoundError, OSError):
                    # Never erase a backup after unproven or failed rollback.
                    if previous is not None:
                        retain_backups.add(previous)
            # If a target changed during backup but before our install, retain
            # its original snapshot rather than silently discarding evidence.
            for name, previous in backups.items():
                if name not in {item[0] for item in installed}:
                    try:
                        if not os.path.samefile(destination / name, previous):
                            retain_backups.add(previous)
                    except (FileNotFoundError, OSError):
                        retain_backups.add(previous)
        else:
            for target, staging in reversed(links):
                try:
                    if os.path.samefile(target, staging):
                        target.unlink()
                except (FileNotFoundError, OSError):
                    pass
        raise
    finally:
        for item in [*temps, *holds]:
            item.unlink(missing_ok=True)
        for previous in backups.values():
            if previous not in retain_backups:
                previous.unlink(missing_ok=True)
    return {"artifacts": sorted(files), "source_sha": manifest["source_sha"],
            "verification_status": "NOT_RUN"}
