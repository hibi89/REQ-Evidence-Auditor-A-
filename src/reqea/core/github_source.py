"""Explicit public-GitHub-only, read-only API source acquisition.

No user credentials, clone, git hooks, redirects, remote writes or filesystem
side effects outside a disposable, owned temporary directory.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import re
import ssl
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import (HTTPRedirectHandler, HTTPSHandler, ProxyHandler,
                            Request, build_opener)

_OWNER = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
_REPO = r"[A-Za-z0-9_.-]{1,100}"
_URL = re.compile(r"https://github\.com/(" + _OWNER + r")/(" + _REPO + r")/?\Z")
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_REF = re.compile(r"[A-Za-z0-9_./\-]{1,160}\Z")
_API_PREFIX = "https://api.github.com/repos/"
_MAX_JSON = 2_000_000
_MAX_RETRY_SECONDS = 86_400


class GitHubRetryableError(ValueError):
    """Constrained retry hint, excluding untrusted remote error messages."""

    def __init__(self, message: str, retry_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_seconds = retry_seconds


class GitHubRateLimitError(GitHubRetryableError):
    """A GitHub quota or secondary-rate-limit response."""

    def __init__(self, retry_seconds: float | None = None) -> None:
        super().__init__("GitHub rate limited", retry_seconds)


class GitHubTransientError(GitHubRetryableError):
    """Temporary remote HTTP failure; never a permission or scope bypass."""

    def __init__(self, retry_seconds: float | None = None) -> None:
        super().__init__("GitHub temporarily unavailable", retry_seconds)


def _retry_delay(headers) -> float | None:
    """Use trusted bounded retry hints; pause on malformed/oversized values."""
    if headers is None:
        return None
    retry = headers.get("Retry-After")
    if retry is not None:
        if not isinstance(retry, str) or len(retry) > 100:
            raise ValueError("invalid GitHub retry hint")
        if re.fullmatch(r"[0-9]{1,10}", retry):
            seconds = float(int(retry))
        else:
            try:
                deadline = parsedate_to_datetime(retry)
                if deadline.tzinfo is None:
                    raise ValueError("missing timezone")
                seconds = max(0.0, (deadline - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError, IndexError):
                raise ValueError("invalid GitHub retry hint") from None
        if not 0 <= seconds <= _MAX_RETRY_SECONDS:
            raise ValueError("GitHub retry window exceeds safety limit")
        return seconds
    if headers.get("X-RateLimit-Remaining") == "0":
        reset = headers.get("X-RateLimit-Reset")
        if reset is None:
            return None
        if not isinstance(reset, str) or not re.fullmatch(r"[0-9]{1,11}", reset):
            raise ValueError("invalid GitHub reset hint")
        seconds = max(0.0, float(int(reset)) - time.time())
        if seconds > _MAX_RETRY_SECONDS:
            raise ValueError("GitHub reset window exceeds safety limit")
        return seconds
    return None


def parse_public_github_url(url: str) -> tuple[str, str]:
    """Accept exactly a bare github.com owner/repo HTTPS URL, nothing embedded."""
    if not isinstance(url, str) or len(url) > 260:
        raise ValueError("invalid public GitHub URL")
    match = _URL.fullmatch(url)
    if match is None or match.group(2).casefold() in (".", "..") or match.group(2).endswith(".git"):
        raise ValueError("GitHub URL must be https://github.com/OWNER/REPO")
    return match.group(1), match.group(2)


def validate_ref(ref: str | None) -> str | None:
    if ref is None or ref == "":
        return None
    if not isinstance(ref, str) or not _REF.fullmatch(ref):
        raise ValueError("invalid GitHub ref")
    if ref.startswith(("-", "/", ".")) or ref.endswith(("/", ".", ".lock")):
        raise ValueError("invalid GitHub ref")
    if (".." in ref or "//" in ref or any(
            part in ("", ".", "..") or part.startswith(".") or part.endswith(".")
            for part in ref.split("/"))):
        raise ValueError("invalid GitHub ref")
    return ref


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("GitHub API redirect refused")


def _json_get(path: str, *, cap: int = _MAX_JSON) -> dict:
    """GET a generated GitHub API route only; refuse redirects and oversized data."""
    if (not isinstance(path, str) or not path.startswith("/repos/")
            or "?" in path.split("/", 2)[0] or not 1024 <= cap <= _MAX_JSON):
        raise ValueError("unsafe GitHub API request")
    url = "https://api.github.com" + path
    request = Request(url, headers={"User-Agent": "REQEA-local-readonly-v11",
                                    "Accept": "application/vnd.github+json"},
                      method="GET")
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()),
                          _RejectRedirect())
    try:
        with opener.open(request, timeout=8) as response:
            if response.geturl() != url or response.status != 200:
                raise ValueError("unexpected GitHub API response")
            body = response.read(cap + 1)
            if len(body) > cap:
                raise ValueError("GitHub API payload exceeds limit")
    except HTTPError as exc:
        # A bare 403 is often a permission/access denial, not throttling.
        # Only an explicit GitHub quota/reset signal warrants retry/backoff.
        headers = exc.headers
        limited = exc.code == 429 or (exc.code == 403 and headers is not None and (
            headers.get("X-RateLimit-Remaining") == "0"
            or headers.get("Retry-After") is not None))
        if limited:
            raise GitHubRateLimitError(_retry_delay(headers)) from None
        # A transient GitHub service failure must not permanently disable
        # an already-approved foreground watch. Keep auth/ref errors fatal.
        if exc.code in (408, 500, 502, 503, 504):
            raise GitHubTransientError(_retry_delay(headers)) from None
        if exc.code == 403:
            raise ValueError("GitHub access denied") from None
        if exc.code in (401, 404):
            raise ValueError("GitHub repository/ref unavailable or not public") from None
        raise ValueError("GitHub API rejected request") from None
    except (URLError, TimeoutError, OSError) as exc:
        raise ValueError("GitHub API network unavailable") from None
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid GitHub API JSON") from None
    if not isinstance(result, dict):
        raise ValueError("unexpected GitHub API JSON type")
    return result


class PublicGitHubReader:
    """Bounded read-only repository metadata/commit/tree/blob API reader."""

    def __init__(self, url: str, ref: str | None = None, *,
                 before_request: Callable[[], None] | None = None) -> None:
        self.owner, self.repo = parse_public_github_url(url)
        self.requested_ref = validate_ref(ref)
        self._calls = 0
        self._before_request = before_request

    def _read(self, suffix: str, cap: int = _MAX_JSON, *,
              before_request: Callable[[], None] | None = None) -> dict:
        # An already in-flight GET can finish, but STOP must prevent the next.
        if self._before_request is not None:
            self._before_request()
        if before_request is not None:
            before_request()
        self._calls += 1
        # 200 allowed snapshot source blobs plus metadata/commit/tree GETs.
        # Keep this per-operation cap explicit; never unbounded.
        if self._calls > 203:
            raise ValueError("GitHub request budget exceeded")
        owner = quote(self.owner, safe="")
        repo = quote(self.repo, safe="")
        # Limit even internal callers to explicit read-only routes inside the
        # chosen repository. Never accept traversal, ad-hoc query or URL paths.
        if suffix == "":
            pass
        elif suffix.startswith("/commits/"):
            selected = suffix[len("/commits/"):]
            if not selected or validate_ref(selected) != selected:
                raise ValueError("invalid GitHub commit route")
        elif re.fullmatch(r"/git/trees/[0-9a-fA-F]{40}\?recursive=1", suffix):
            pass
        elif re.fullmatch(r"/git/blobs/[0-9a-fA-F]{40}", suffix):
            pass
        else:
            raise ValueError("invalid GitHub API route")
        return _json_get("/repos/" + owner + "/" + repo + suffix, cap=cap)

    def head_commit_sha(self, *,
                        before_request: Callable[[], None] | None = None) -> str:
        """Lightweight explicit public-ref poll (no tree or blob downloads)."""
        # This Reader persists for hours in PublicGitHubChangeWatch. The
        # 128-call ceiling belongs to one operation, not to its entire life:
        # otherwise harmless 15-minute polling pauses permanently after
        # ~64 polls (~16 hours), even when all API calls succeed.
        self._calls = 0
        metadata = self._read("", before_request=before_request)
        fullname = metadata.get("full_name")
        if (metadata.get("private") is not False or not isinstance(fullname, str)
                or fullname.casefold() != (self.owner + "/" + self.repo).casefold()):
            raise ValueError("repository is not confirmed public")
        ref = self.requested_ref
        if ref is None:
            ref = validate_ref(metadata.get("default_branch"))
        if ref is None:
            raise ValueError("GitHub ref unavailable")
        commit = self._read("/commits/" + quote(ref, safe="/"), before_request=before_request)
        sha = commit.get("sha")
        if not isinstance(sha, str) or not _SHA.fullmatch(sha):
            raise ValueError("GitHub ref SHA invalid")
        if _SHA.fullmatch(ref) and sha.lower() != ref.lower():
            raise ValueError("pinned GitHub commit mismatch")
        return sha.lower()

    def pinned_tree(self) -> tuple[str, str, list[dict]]:
        metadata = self._read("")
        if (metadata.get("private") is not False
                or not isinstance(metadata.get("full_name"), str)
                or metadata["full_name"].casefold()
                != (self.owner + "/" + self.repo).casefold()):
            raise ValueError("repository is not confirmed public")
        ref = self.requested_ref
        if ref is None:
            ref = validate_ref(metadata.get("default_branch"))
            if ref is None:
                raise ValueError("GitHub default branch unavailable")
        commit = self._read("/commits/" + quote(ref, safe="/"))
        sha = commit.get("sha")
        tree_info = commit.get("commit")
        tree_info = tree_info.get("tree") if isinstance(tree_info, dict) else None
        tree_sha = tree_info.get("sha") if isinstance(tree_info, dict) else None
        if (not isinstance(sha, str) or not _SHA.fullmatch(sha)
                or not isinstance(tree_sha, str) or not _SHA.fullmatch(tree_sha)):
            raise ValueError("commit/tree SHA missing or invalid")
        if _SHA.fullmatch(ref) and sha.lower() != ref.lower():
            raise ValueError("requested commit does not match pinned SHA")
        tree = self._read("/git/trees/" + tree_sha + "?recursive=1")
        entries = tree.get("tree")
        if (tree.get("sha") != tree_sha or tree.get("truncated") is not False
                or not isinstance(entries, list) or len(entries) > 750):
            raise ValueError("GitHub tree scope truncated or inconsistent")
        return sha.lower(), tree_sha.lower(), entries

    def read_blob(self, sha: str, *, max_bytes: int) -> bytes:
        import base64
        import binascii
        import hashlib
        if not _SHA.fullmatch(sha):
            raise ValueError("invalid blob SHA")
        info = self._read("/git/blobs/" + sha, cap=min(_MAX_JSON, max_bytes * 2 + 8192))
        if info.get("sha") != sha or info.get("encoding") != "base64":
            raise ValueError("GitHub blob SHA or encoding mismatch")
        declared = info.get("size")
        encoded = info.get("content")
        if type(declared) is not int or declared > max_bytes or declared < 0 or not isinstance(encoded, str):
            raise ValueError("GitHub blob exceeds permitted size")
        try:
            raw = base64.b64decode("".join(encoded.split()), validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("invalid GitHub blob encoding") from None
        digest = hashlib.sha1(  # Git object ID interoperability, not a security hash
            b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw,
            usedforsecurity=False,
        ).hexdigest()
        if len(raw) != declared or digest != sha.lower():
            raise ValueError("GitHub blob content failed SHA check")
        return raw
