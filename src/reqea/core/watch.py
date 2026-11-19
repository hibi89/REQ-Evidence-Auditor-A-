"""Explicit foreground-only V1.1 local and public-GitHub change watchers.

Poll calls are made by the owner application after the user turns monitoring on.
No daemon, Actions schedule, remote writing, or post-exit background activity.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Lock
import time

from reqea_codegraph.files import read_file
from reqea_codegraph.walk import scan_tree
from .discovery import discover_local_requirements
from .github_source import PublicGitHubReader
from .orchestrator import build_audit
from .selector import select_requirements
from .snapshot import public_github_snapshot
from .source_ref import inspect_local_source, read_checked_requirements

_FATAL = frozenset({"required_B_or_C_module_unavailable", "B_contract_or_SHA_mismatch",
                    "C_contract_or_SHA_mismatch", "C_invalid_or_untrusted_status",
                    "C_invalid_finding_status", "C_invalid_warning_contract",
                    "analysis_failed_without_verified_evidence"})
_MIN_LOCAL_SECONDS = 30.0
_MIN_GITHUB_SECONDS = 900.0
_DEBOUNCE_SECONDS = 5.0


def _candidate_audit(root: str, selected: str | None) -> tuple[dict, dict]:
    found = discover_local_requirements(root)
    choice = select_requirements(found, selected)
    result = build_audit(root, choice["requirements_path"])
    if _FATAL.intersection(result.get("warnings", [])):
        raise ValueError("analysis contract failed; do not promote a new snapshot")
    return choice, result


def _local_fingerprint(root: str) -> str:
    """Hash the same allowed, bounded code scope; stop on incomplete scans."""
    scan = scan_tree(root, {"max_files": 10_000, "max_file_bytes": 2_000_000,
                            "max_total_bytes": 50_000_000, "max_depth": 32})
    if scan.truncated or scan.warning_limited:
        raise ValueError("local change fingerprint incomplete")
    digest = hashlib.sha256()
    for entry in scan.files:
        file_data = read_file(scan.root, entry, 2_000_000)
        digest.update(entry.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_data.record["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


class LocalChangeWatch:
    """Owner-driven local polling, debounced and content-bound to one REQ doc."""

    def __init__(self, root: str, requirements: str, *,
                 interval_seconds: float = _MIN_LOCAL_SECONDS,
                 debounce_seconds: float = _DEBOUNCE_SECONDS):
        if not isinstance(interval_seconds, (int, float)) or interval_seconds < _MIN_LOCAL_SECONDS:
            raise ValueError("local poll interval must be at least 30 seconds")
        if not isinstance(debounce_seconds, (int, float)) or debounce_seconds < _DEBOUNCE_SECONDS:
            raise ValueError("local debounce must be at least 5 seconds")
        self.root = root
        self.requirements = requirements
        self.interval = float(interval_seconds)
        self.debounce = float(debounce_seconds)
        self.active = False
        self._baseline_doc: str | None = None
        self._fingerprint: str | None = None
        self._pending: tuple[str, float] | None = None
        self._checked_at = float("-inf")
        self._audit: dict | None = None
        self._generation = 0
        self._state_lock = Lock()
        self._polling = False

    def start(self, *, now: float | None = None) -> dict:
        """Explicit opt-in only; do not persist any source or automatically save."""
        with self._state_lock:
            generation = self._generation
        found = discover_local_requirements(self.root)
        selected_path = Path(self.requirements)
        if selected_path.is_absolute():
            try:
                selected_path = selected_path.relative_to(Path(self.root).absolute())
            except ValueError as exc:
                raise ValueError("canonical requirements must be inside selected root") from exc
        selected = select_requirements(found, selected_path.as_posix())
        # Do not bless an initial audit if source changed mid-analysis.
        initial_fingerprint = _local_fingerprint(self.root)
        candidate = build_audit(self.root, selected["requirements_path"])
        if _FATAL.intersection(candidate.get("warnings", [])):
            raise ValueError("initial local audit unavailable")
        later_fingerprint = _local_fingerprint(self.root)
        if initial_fingerprint != later_fingerprint:
            raise ValueError("local source changed during initial audit")
        source = inspect_local_source(self.root, selected["requirements_path"])
        if hashlib.sha256(read_checked_requirements(source)).hexdigest() != selected["sha256"]:
            raise ValueError("canonical requirements changed during initial audit")
        # STOP may arrive while the initial audit is running in another thread.
        # Commit the new monitoring state only while holding the same lock as stop().
        with self._state_lock:
            if generation != self._generation:
                return {"status": "STOPPED"}
            self.requirements = selected["requirements_path"]
            self._baseline_doc = selected["sha256"]
            self._audit = candidate
            self._fingerprint = later_fingerprint
            self._pending = None
            self._checked_at = time.monotonic() if now is None else float(now)
            self._generation += 1
            self.active = True
            return {"status": "STARTED", "audit": self._audit,
                    "fingerprint": self._fingerprint, "verification_status": "NOT_RUN"}

    def stop(self) -> dict:
        with self._state_lock:
            self.active = False
            self._generation += 1
            self._pending = None
        return {"status": "STOPPED"}

    def tick(self, *, now: float | None = None) -> dict:
        """One bounded poll. STOP and concurrent ticks cannot publish stale state."""
        moment = time.monotonic() if now is None else float(now)
        with self._state_lock:
            if not self.active:
                return {"status": "STOPPED"}
            if self._polling or moment - self._checked_at < self.interval:
                return {"status": "WAIT"}
            self._checked_at = moment
            self._polling = True
            generation = self._generation
            previous_fingerprint = self._fingerprint
            pending = self._pending
            requirements = self.requirements
            baseline_doc = self._baseline_doc
        try:
            fingerprint = _local_fingerprint(self.root)
            if fingerprint == previous_fingerprint:
                with self._state_lock:
                    if not self.active or generation != self._generation:
                        return {"status": "STOPPED"}
                    self._pending = None
                return {"status": "UNCHANGED"}
            source = inspect_local_source(self.root, requirements)
            latest_digest = hashlib.sha256(read_checked_requirements(source)).hexdigest()
            if latest_digest != baseline_doc:
                raise ValueError("canonical requirements changed; human confirmation required")
            if pending is None or pending[0] != fingerprint:
                with self._state_lock:
                    if not self.active or generation != self._generation:
                        return {"status": "STOPPED"}
                    self._pending = (fingerprint, moment)
                return {"status": "DEBOUNCING"}
            if moment - pending[1] < self.debounce:
                with self._state_lock:
                    if not self.active or generation != self._generation:
                        return {"status": "STOPPED"}
                return {"status": "DEBOUNCING"}
            new_audit = build_audit(self.root, requirements)
            if _FATAL.intersection(new_audit.get("warnings", [])):
                raise ValueError("new local audit contract incomplete")
            if _local_fingerprint(self.root) != fingerprint:
                raise ValueError("local source changed during audit")
            source = inspect_local_source(self.root, requirements)
            if hashlib.sha256(read_checked_requirements(source)).hexdigest() != baseline_doc:
                raise ValueError("canonical requirements changed during audit")
            with self._state_lock:
                if not self.active or generation != self._generation:
                    return {"status": "STOPPED"}
                previous = self._audit
                self._audit = new_audit
                self._fingerprint = fingerprint
                self._pending = None
                return {"status": "CHANGED", "previous": previous, "current": new_audit,
                        "fingerprint": fingerprint,
                        "source_sha": new_audit.get("source_sha", "UNVERIFIED"),
                        "verification_status": "NOT_RUN"}
        except (ValueError, OSError, UnicodeError):
            with self._state_lock:
                if not self.active or generation != self._generation:
                    return {"status": "STOPPED"}
                self.active = False
                self._generation += 1
            return {"status": "PAUSED", "reason": "LOCAL_INPUT_CHANGED_OR_UNSAFE"}
        finally:
            with self._state_lock:
                self._polling = False

class PublicGitHubChangeWatch:
    """Opt-in 15-minute+ public-ref polling with fail-closed backoff."""

    def __init__(self, url: str, ref: str | None = None,
                 requirements: str | None = None, *,
                 interval_seconds: float = _MIN_GITHUB_SECONDS):
        if not isinstance(interval_seconds, (int, float)) or interval_seconds < _MIN_GITHUB_SECONDS:
            raise ValueError("GitHub poll interval must be at least 900 seconds")
        self.reader = PublicGitHubReader(url, ref)
        self.url = url
        self.ref = self.reader.requested_ref
        self.requirements = requirements
        self.interval = float(interval_seconds)
        self.active = False
        self._head: str | None = None
        self._document_digest: str | None = None
        self._selected: str | None = None
        self._checked_at = float("-inf")
        self._backoff = self.interval
        self._audit: dict | None = None
        self._generation = 0
        self._state_lock = Lock()
        self._polling = False

    def start(self, *, now: float | None = None) -> dict:
        """Explicit consent begins one pinned public snapshot analysis."""
        with self._state_lock:
            generation = self._generation
        with public_github_snapshot(self.url, self.ref) as snapshot:
            selection, audit = _candidate_audit(snapshot["root"], self.requirements)
            head = snapshot["commit_sha"]
        with self._state_lock:
            if generation != self._generation:
                return {"status": "STOPPED"}
            self._selected = selection["relative_path"]
            self._document_digest = selection["sha256"]
            self._audit = audit
            self._head = head
            self._checked_at = time.monotonic() if now is None else float(now)
            self._backoff = self.interval
            self._generation += 1
            self.active = True
            return {"status": "STARTED", "repository": self.reader.owner + "/" + self.reader.repo,
                    "pinned_commit_sha": head, "source_sha": "UNVERIFIED",
                    "verification_status": "NOT_RUN", "audit": audit}

    def stop(self) -> dict:
        with self._state_lock:
            self.active = False
            self._generation += 1
        return {"status": "STOPPED"}

    def tick(self, *, now: float | None = None) -> dict:
        """No concurrent remote polling, stale state, or post-STOP promotion."""
        moment = time.monotonic() if now is None else float(now)
        with self._state_lock:
            if not self.active:
                return {"status": "STOPPED"}
            if self._polling or moment - self._checked_at < self._backoff:
                return {"status": "WAIT"}
            self._checked_at = moment
            self._polling = True
            generation = self._generation
            previous_head = self._head
            selected = self._selected
            document_digest = self._document_digest
        try:
            head = self.reader.head_commit_sha()
            if head == previous_head:
                with self._state_lock:
                    if not self.active or generation != self._generation:
                        return {"status": "STOPPED"}
                    self._backoff = self.interval
                return {"status": "UNCHANGED"}
            # Pin the observed commit: moving the branch during transfer is safe.
            with public_github_snapshot(self.url, head) as snapshot:
                if snapshot["commit_sha"] != head:
                    raise ValueError("ref changed during snapshot")
                selection, audit = _candidate_audit(snapshot["root"], selected)
                if selection["sha256"] != document_digest:
                    raise ValueError("canonical document changed; explicit review required")
            with self._state_lock:
                if not self.active or generation != self._generation:
                    return {"status": "STOPPED"}
                old_audit = self._audit
                self._audit = audit
                self._head = head
                self._backoff = self.interval
                return {"status": "CHANGED", "previous": old_audit, "current": audit,
                        "pinned_commit_sha": head, "source_sha": "UNVERIFIED",
                        "verification_status": "NOT_RUN"}
        except (ValueError, OSError, UnicodeError) as exc:
            with self._state_lock:
                if not self.active or generation != self._generation:
                    return {"status": "STOPPED"}
                if "rate limited" in str(exc):
                    self._backoff = min(max(self._backoff * 2, self.interval), 14_400.0)
                    return {"status": "BACKOFF", "retry_seconds": self._backoff}
                self.active = False
                self._generation += 1
            return {"status": "PAUSED", "reason": "REMOTE_REF_OR_SCOPE_UNSAFE"}
        finally:
            with self._state_lock:
                self._polling = False