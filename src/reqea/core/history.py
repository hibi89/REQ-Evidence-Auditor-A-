"""Private, append-only, candidate-only report differences and project bookmarks.

Never embeds source code, evidence paths, absolute paths or raw warning text
in audit DELTA documents. Bookmarks hold user-selected paths only inside the
explicitly approved local output folder. No network, source execution or delete.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path

from .github_source import parse_public_github_url, validate_ref
from .output import _check_no_symlinks

_STATES = frozenset(("CODE_CANDIDATE", "GAP_CANDIDATE", "REVIEW_REQUIRED", "UNASSESSED"))
_REQ = re.compile(r"REQ-[0-9]{3,}\Z")
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_REQS = 10_000
_MAX_PROFILES = 32


def _source_id(value: object) -> str:
    if value == "UNVERIFIED":
        return value
    if isinstance(value, str) and _HEX40.fullmatch(value.lower()):
        return value.lower()
    raise ValueError("invalid source SHA provenance")


def _snapshot_token(value: object) -> str:
    if value is None:
        return "UNVERIFIED"
    if isinstance(value, str) and (_HEX40.fullmatch(value.lower()) or _HEX64.fullmatch(value.lower())):
        return value.lower()
    raise ValueError("invalid snapshot fingerprint")


def _findings(audit: dict) -> dict[str, str]:
    if not isinstance(audit, dict) or audit.get("schema_version") != "reqea.v1":
        raise ValueError("only reqea.v1 candidate audits are comparable")
    if audit.get("verification_status") != "NOT_RUN":
        raise ValueError("unexpected verification status")
    records = audit.get("findings")
    if not isinstance(records, list) or len(records) > _MAX_REQS:
        raise ValueError("invalid REQ findings collection")
    found: dict[str, str] = {}
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("invalid REQ finding")
        req, status = item.get("req_id"), item.get("status")
        if not isinstance(req, str) or not _REQ.fullmatch(req) or status not in _STATES:
            raise ValueError("untrusted REQ ID or status")
        if req in found:
            raise ValueError("duplicate REQ ID in audit")
        found[req] = status
    return found


def compare_audits(before: dict, after: dict, *,
                   before_snapshot: str | None = None,
                   after_snapshot: str | None = None) -> dict:
    """Produce a deterministic, bounded, *unverified* REQ candidate status diff."""
    old, new = _findings(before), _findings(after)
    changed = [{"req_id": key, "before": old.get(key, "NOT_PRESENT"),
                "after": new.get(key, "NOT_PRESENT")}
               for key in sorted(old.keys() | new.keys())
               if old.get(key) != new.get(key)]
    return {
        "schema_version": "reqea.delta.v11",
        "verification_status": "NOT_RUN",
        "status": "CANDIDATE_DIFF_ONLY",
        "before": {"source_sha": _source_id(before.get("source_sha")),
                   "snapshot": _snapshot_token(before_snapshot),
                   "req_count": len(old)},
        "after": {"source_sha": _source_id(after.get("source_sha")),
                  "snapshot": _snapshot_token(after_snapshot),
                  "req_count": len(new)},
        "changes": changed,
        "changed_count": len(changed),
        "warnings": ["STATIC_CANDIDATES_ARE_NOT_VERIFIED"]
        + (["UNVERIFIED_SOURCE_PROVENANCE"]
           if "UNVERIFIED" in (_source_id(before.get("source_sha")),
                               _source_id(after.get("source_sha"))) else []),
    }


def _safe_output(out_dir: str, *, source_root: str | None = None) -> Path:
    if not isinstance(out_dir, str) or not out_dir or "\x00" in out_dir or out_dir.startswith(("\\\\", "//")):
        raise ValueError("unsafe approved output directory")
    dest = Path(out_dir).absolute()
    _check_no_symlinks(dest)
    if source_root is not None:
        root = Path(source_root).resolve(strict=True)
        _check_no_symlinks(Path(source_root).absolute())
        target = dest.resolve(strict=False)
        if target == root or root in target.parents:
            raise ValueError("output must be outside audited source root")
    if dest.exists() and not dest.is_dir():
        raise ValueError("output location is not a directory")
    return dest


def _append_json(out_dir: str, subdir: str, prefix: str, payload: dict,
                 *, source_root: str | None = None) -> dict:
    dest = _safe_output(out_dir, source_root=source_root)
    content = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(content) > 512_000:
        raise ValueError("candidate report exceeds bound")
    digest = hashlib.sha256(content).hexdigest()
    folder = dest / subdir
    _check_no_symlinks(folder)
    folder.mkdir(parents=True, exist_ok=True)
    _check_no_symlinks(folder)
    target = folder / (prefix + digest + ".json")
    if target.exists():
        if target.is_symlink() or not target.is_file() or target.stat().st_size > 512_000:
            raise ValueError("unsafe existing candidate report")
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("existing candidate report has changed")
        return {"status": "EXISTS", "file": str(target), "sha256": digest}
    fd, temporary = tempfile.mkstemp(prefix=".reqea-pending-", dir=folder)
    pending = Path(temporary)
    linked = False
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        _check_no_symlinks(folder)
        try:
            os.link(pending, target)  # exclusive destination creation
            linked = True
        except FileExistsError:
            if not target.is_file() or target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError("candidate record collision")
        return {"status": "SAVED" if linked else "EXISTS",
                "file": str(target), "sha256": digest}
    finally:
        pending.unlink(missing_ok=True)


def save_delta(delta: dict, *, out_dir: str, source_root: str | None = None) -> dict:
    if (not isinstance(delta, dict) or delta.get("schema_version") != "reqea.delta.v11"
            or delta.get("verification_status") != "NOT_RUN"
            or not isinstance(delta.get("changes"), list)):
        raise ValueError("invalid candidate delta")
    # Reconstruct only permitted fields to avoid persisting caller-provided code,
    # paths or arbitrary warning contents.
    old, new = delta.get("before", {}), delta.get("after", {})
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise ValueError("invalid candidate provenance")
    safe = {
        "schema_version": "reqea.delta.v11",
        "status": "CANDIDATE_DIFF_ONLY",
        "verification_status": "NOT_RUN",
        "before": {"source_sha": _source_id(old.get("source_sha")),
                   "snapshot": _snapshot_token(old.get("snapshot"))},
        "after": {"source_sha": _source_id(new.get("source_sha")),
                  "snapshot": _snapshot_token(new.get("snapshot"))},
        "changes": [],
    }
    for entry in delta["changes"]:
        if not isinstance(entry, dict):
            raise ValueError("invalid delta entry")
        req, old_status, new_status = entry.get("req_id"), entry.get("before"), entry.get("after")
        if not isinstance(req, str) or not _REQ.fullmatch(req):
            raise ValueError("invalid delta REQ")
        if old_status not in _STATES | {"NOT_PRESENT"} or new_status not in _STATES | {"NOT_PRESENT"}:
            raise ValueError("invalid delta status")
        safe["changes"].append({"req_id": req, "before": old_status, "after": new_status})
    if len(safe["changes"]) > _MAX_REQS or len({r["req_id"] for r in safe["changes"]}) != len(safe["changes"]):
        raise ValueError("invalid delta bounds or duplicate IDs")
    safe["changes"].sort(key=lambda r: r["req_id"])
    safe["changed_count"] = len(safe["changes"])
    safe["warnings"] = ["STATIC_CANDIDATES_ARE_NOT_VERIFIED"]
    return _append_json(out_dir, "reqea-history", "reqea-delta-", safe,
                        source_root=source_root)


def _validated_profile(profile: dict) -> dict:
    if not isinstance(profile, dict):
        raise ValueError("invalid project registration")
    kind, source = profile.get("kind"), profile.get("source")
    selected = profile.get("requirements")
    if selected is not None and (not isinstance(selected, str) or len(selected) > 700
                                 or selected.startswith("/") or "\\" in selected
                                 or any(p in ("", ".", "..") for p in selected.split("/"))):
        raise ValueError("invalid registered requirements document")
    if kind == "github":
        parse_public_github_url(source)
        ref = validate_ref(profile.get("ref"))
        return {"schema_version": "reqea.project.v11", "kind": kind,
                "source": source, "ref": ref, "requirements": selected}
    if kind == "local" and isinstance(source, str) and source and "\x00" not in source:
        root = Path(source)
        if not root.is_absolute() or not root.is_dir():
            raise ValueError("registered root must be an existing absolute folder")
        from .source_ref import _safe_path
        _safe_path(root)
        return {"schema_version": "reqea.project.v11", "kind": kind,
                "source": str(root), "ref": None, "requirements": selected}
    raise ValueError("invalid registered project mode")


def register_project(profile: dict, *, out_dir: str) -> dict:
    """User-initiated append-only bookmark. No overwrite, upload or source edit."""
    safe = _validated_profile(profile)
    root = safe["source"] if safe["kind"] == "local" else None
    return _append_json(out_dir, "reqea-projects", "reqea-profile-", safe,
                        source_root=root)


def load_projects(*, out_dir: str) -> list[dict]:
    dest = _safe_output(out_dir)
    folder = dest / "reqea-projects"
    _check_no_symlinks(folder)
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise ValueError("project registry is not a directory")
    paths = list(folder.iterdir())
    if len(paths) > _MAX_PROFILES:
        raise ValueError("too many saved projects for bounded loading")
    records: list[dict] = []
    for p in sorted(paths):
        if not re.fullmatch(r"reqea-profile-[0-9a-f]{64}\.json", p.name):
            raise ValueError("unexpected project registry entry")
        info = p.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
            raise ValueError("unsafe registered project entry")
        encoded = p.read_bytes()
        fingerprint = hashlib.sha256(encoded).hexdigest()
        if fingerprint != p.stem.removeprefix("reqea-profile-"):
            raise ValueError("modified registered project record")
        parsed = json.loads(encoded.decode("utf-8"))
        records.append(_validated_profile(parsed))
    return records
