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
    if value is None or value == "UNVERIFIED":
        return "UNVERIFIED"
    if isinstance(value, str) and (_HEX40.fullmatch(value.lower()) or _HEX64.fullmatch(value.lower())):
        return value.lower()
    raise ValueError("invalid snapshot fingerprint")


def _findings(audit: dict) -> tuple[dict[str, dict], dict]:
    """Only bounded status and numeric scope; never retain private evidence paths."""
    if not isinstance(audit, dict) or audit.get("schema_version") != "reqea.v1":
        raise ValueError("only reqea.v1 candidate audits are comparable")
    if audit.get("verification_status") != "NOT_RUN":
        raise ValueError("unexpected verification status")
    records = audit.get("findings")
    if not isinstance(records, list) or len(records) > _MAX_REQS:
        raise ValueError("invalid REQ findings collection")
    found: dict[str, dict] = {}
    evidence_total, criteria_total = 0, 0
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("invalid REQ finding")
        req, status = item.get("req_id"), item.get("status")
        # JSON permits lists/objects here; never perform a set-membership
        # check on an unhashable value before validating its type.
        if (not isinstance(req, str) or not _REQ.fullmatch(req)
                or not isinstance(status, str) or status not in _STATES):
            raise ValueError("untrusted REQ ID or status")
        if req in found:
            raise ValueError("duplicate REQ ID in audit")
        evidence = item.get("evidence", [])
        criteria = item.get("acceptance_criteria", [])
        if not isinstance(evidence, list) or len(evidence) > _MAX_REQS:
            raise ValueError("invalid evidence boundary")
        if not isinstance(criteria, list) or len(criteria) > _MAX_REQS:
            raise ValueError("invalid acceptance boundary")
        found[req] = {"status": status, "evidence_count": len(evidence),
                      "criteria_count": len(criteria)}
        evidence_total += len(evidence)
        criteria_total += len(criteria)
    warnings = audit.get("warnings", [])
    if not isinstance(warnings, list) or len(warnings) > _MAX_REQS:
        raise ValueError("invalid warnings boundary")
    scope = {"req_count": len(found), "evidence_count": evidence_total,
             "criteria_count": criteria_total, "warning_count": len(warnings)}
    return found, scope


def compare_audits(before: dict, after: dict, *,
                   before_snapshot: str | None = None,
                   after_snapshot: str | None = None) -> dict:
    """Deterministic REQ statuses and evidence *counts*, never code or path text."""
    old, old_scope = _findings(before)
    new, new_scope = _findings(after)
    empty = {"status": "NOT_PRESENT", "evidence_count": 0, "criteria_count": 0}
    changed = []
    for key in sorted(old.keys() | new.keys()):
        previous = old.get(key, empty)
        current = new.get(key, empty)
        if previous == current:
            continue
        changed.append({
            "req_id": key, "before": previous["status"], "after": current["status"],
            "before_evidence_count": previous["evidence_count"],
            "after_evidence_count": current["evidence_count"],
            "before_criteria_count": previous["criteria_count"],
            "after_criteria_count": current["criteria_count"],
        })
    old_id, new_id = _source_id(before.get("source_sha")), _source_id(after.get("source_sha"))
    return {
        "schema_version": "reqea.delta.v11",
        "verification_status": "NOT_RUN",
        "status": "CANDIDATE_DIFF_ONLY",
        "before": {"source_sha": old_id, "snapshot": _snapshot_token(before_snapshot),
                   "scope": old_scope},
        "after": {"source_sha": new_id, "snapshot": _snapshot_token(after_snapshot),
                  "scope": new_scope},
        "changes": changed,
        "changed_count": len(changed),
        "warnings": ["STATIC_CANDIDATES_ARE_NOT_VERIFIED"]
        + (["UNVERIFIED_SOURCE_PROVENANCE"]
           if "UNVERIFIED" in (old_id, new_id) else []),
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


def _committed_records(folder: Path, prefix: str, limit: int) -> list[Path]:
    """List committed SHA-named files without trusting abandoned staging files.

    A killed writer may leave its private mkstemp file. Keep the file as crash
    evidence, but never interpret it as a committed record or let it make
    valid earlier records unreadable. Unknown/symlink entries still fail closed.
    """
    paths = sorted(folder.iterdir())
    if len(paths) > limit + 64:
        raise ValueError("approved history/registry directory exceeds bounded entry count")
    records: list[Path] = []
    pending_count = 0
    for path in paths:
        staged = re.fullmatch(r"\.reqea-pending-[a-z0-9_]{8}", path.name) is not None
        if not staged and not re.fullmatch(
                re.escape(prefix) + r"[0-9a-f]{64}\.json", path.name):
            raise ValueError("unexpected history/registry entry")
        try:
            info = path.lstat()
        except FileNotFoundError:
            if staged:
                # A concurrently successful writer removed its staging file.
                continue
            raise
        bound = 4_096 if prefix == "reqea-profile-" else 512_000
        if not stat.S_ISREG(info.st_mode) or info.st_size > bound:
            raise ValueError("unsafe history/registry entry")
        if staged:
            pending_count += 1
            if pending_count > 64:
                raise ValueError("too many abandoned or active staging files")
            continue
        records.append(path)
        if len(records) > limit:
            raise ValueError("too many committed history/registry records")
    return records


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
    cap = 128 if subdir == "reqea-history" else _MAX_PROFILES
    existing = _committed_records(folder, prefix, cap)
    if not target.exists() and len(existing) >= cap:
        raise ValueError("approved output history/registry capacity reached; use another output folder")
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


def _safe_delta_record(delta: dict) -> dict:
    """Canonical candidate-only history contract for BOTH write and read.

    A SHA256 filename verifies integrity against its own bytes, not the
    authority of an untrusted file. Reject a self-consistent forged status,
    raw evidence text, or extra fields before returning data to the GUI.
    """
    if (not isinstance(delta, dict) or delta.get("schema_version") != "reqea.delta.v11"
            or delta.get("verification_status") != "NOT_RUN"
            or not isinstance(delta.get("changes"), list)):
        raise ValueError("invalid candidate delta")
    if len(delta["changes"]) > _MAX_REQS:
        raise ValueError("candidate delta exceeds bounded REQ scope")
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
    for side, provided in (("before", old), ("after", new)):
        scope = provided.get("scope", {})
        if not isinstance(scope, dict):
            raise ValueError("invalid candidate scan scope")
        safe_scope = {}
        for key in ("req_count", "evidence_count", "criteria_count", "warning_count"):
            number = scope.get(key, 0)
            if type(number) is not int or number < 0 or number > 100_000_000:
                raise ValueError("invalid candidate scope count")
            safe_scope[key] = number
        safe[side]["scope"] = safe_scope
    for entry in delta["changes"]:
        if not isinstance(entry, dict):
            raise ValueError("invalid delta entry")
        req, old_status, new_status = entry.get("req_id"), entry.get("before"), entry.get("after")
        if not isinstance(req, str) or not _REQ.fullmatch(req):
            raise ValueError("invalid delta REQ")
        if (not isinstance(old_status, str) or not isinstance(new_status, str)
                or old_status not in _STATES | {"NOT_PRESENT"}
                or new_status not in _STATES | {"NOT_PRESENT"}):
            raise ValueError("invalid delta status")
        record = {"req_id": req, "before": old_status, "after": new_status}
        for key in ("before_evidence_count", "after_evidence_count",
                    "before_criteria_count", "after_criteria_count"):
            number = entry.get(key, 0)
            if type(number) is not int or number < 0 or number > _MAX_REQS:
                raise ValueError("invalid REQ scope count")
            record[key] = number
        safe["changes"].append(record)
    if len(safe["changes"]) > _MAX_REQS or len({r["req_id"] for r in safe["changes"]}) != len(safe["changes"]):
        raise ValueError("invalid delta bounds or duplicate IDs")
    safe["changes"].sort(key=lambda r: r["req_id"])
    safe["changed_count"] = len(safe["changes"])
    safe["warnings"] = ["STATIC_CANDIDATES_ARE_NOT_VERIFIED"]
    return safe


def save_delta(delta: dict, *, out_dir: str, source_root: str | None = None) -> dict:
    safe = _safe_delta_record(delta)
    return _append_json(out_dir, "reqea-history", "reqea-delta-", safe,
                        source_root=source_root)

def _validated_profile(profile: dict, *, allow_missing_local: bool = False) -> dict:
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
        # New registrations and analyses require an existing root. Historical
        # bookmarks remain listable/forgetable after an owner moves the source.
        if not root.is_absolute() or (not allow_missing_local and not root.is_dir()):
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
    paths = _committed_records(folder, "reqea-profile-", _MAX_PROFILES)
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
        safe = _validated_profile(parsed, allow_missing_local=True)
        # A self-consistent SHA256 filename does not make arbitrary JSON
        # trustworthy. Accept only the exact canonical record we write;
        # otherwise an extra private-source/authority field or duplicated JSON
        # key is silently discarded and shown as an approved GUI bookmark.
        canonical = (json.dumps(safe, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")) + "\n").encode("utf-8")
        if encoded != canonical:
            raise ValueError("noncanonical registered project record")
        records.append(safe)
    return records


def load_deltas(*, out_dir: str) -> list[dict]:
    """Read bounded, fingerprint-verified candidate history from chosen output."""
    dest = _safe_output(out_dir)
    folder = dest / "reqea-history"
    _check_no_symlinks(folder)
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise ValueError("history output is not a directory")
    paths = _committed_records(folder, "reqea-delta-", 128)
    records: list[dict] = []
    for path in sorted(paths):
        if not re.fullmatch(r"reqea-delta-[0-9a-f]{64}\.json", path.name):
            raise ValueError("unexpected history entry; inspect transaction evidence")
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 512_000:
            raise ValueError("unsafe history entry")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != path.stem.removeprefix("reqea-delta-"):
            raise ValueError("local history record changed")
        item = json.loads(raw.decode("utf-8"))
        if not isinstance(item, dict) or item.get("schema_version") != "reqea.delta.v11":
            raise ValueError("invalid local history schema")
        # Hash-addressing alone cannot authenticate fields. Even if an
        # attacker recomputed a filename, the GUI must never show a forged
        # VERIFIED state, extra raw-source field, or untrusted warning.
        if _safe_delta_record(item) != item:
            raise ValueError("noncanonical local history candidate record")
        records.append(item)
    return records


def unregister_project(profile: dict, *, out_dir: str) -> bool:
    """Explicitly forget a bookmark record only; never delete audit or source."""
    safe = _validated_profile(profile, allow_missing_local=True)
    encoded = (json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    # Only a verified, existing source requires a live containment test.
    # Missing source: touch only the exact canonical hash-named bookmark.
    live_root = safe["source"] if safe["kind"] == "local" and Path(safe["source"]).is_dir() else None
    dest = _safe_output(out_dir, source_root=live_root)
    path = dest / "reqea-projects" / ("reqea-profile-" + digest + ".json")
    _check_no_symlinks(path)
    if not path.exists():
        return False
    if not path.is_file() or path.read_bytes() != encoded:
        raise ValueError("registered project record has changed; refuse deletion")
    path.unlink()
    return True


def project_id(profile: dict) -> str:
    """Stable SHA256 bookmark identifier without requiring the old source."""
    safe = _validated_profile(profile, allow_missing_local=True)
    raw = (json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
