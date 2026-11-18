"""File hashing and safe text extraction (B-02); no source text leaves the package."""
from __future__ import annotations

import hashlib
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from .walk import WalkFile, _is_reparse, safe_relative

# Capability is stable for a running interpreter; cache before test interception.
_ANCHORED_OPEN_AVAILABLE = (os.open in getattr(os, "supports_dir_fd", set())
                          and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"))

LANGUAGES = {
    ".py": "python", ".pyi": "python", ".js": "javascript",
    ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript",
    ".cts": "typescript",
}


@dataclass(frozen=True)
class FileData:
    record: dict
    text: str



def _check_path_components(root: Path, relative: str) -> None:
    """Do not trust a path component that has become a link or reparse point."""
    current = root
    for part in relative.split("/"):
        current = current / part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise ValueError("symlink_or_reparse_disallowed")
    if os.path.commonpath((os.path.realpath(root), os.path.realpath(current))) != os.path.realpath(root):
        raise ValueError("path_escape")


def _check_windows_open_handle(root: Path, relative: str, descriptor: int) -> None:
    """Fail closed before reading if Win32 resolves a handle outside its chosen path.

    Python os.open on Windows cannot pin ancestor folders with dir_fd. A renamed
    ancestor followed by a junction can retain the original inode while
    resolving outside the selected source tree. Inspect the opened handle,
    not a path string that may point to a different object by the time we read.
    This is an additional guard, not an atomic defense against arbitrary
    rename-back races or malicious filesystems.
    """
    if sys.platform != "win32":
        return
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_name = kernel32.GetFinalPathNameByHandleW
    get_name.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    get_name.restype = wintypes.DWORD
    try:
        handle = msvcrt.get_osfhandle(descriptor)
        capacity = 32768
        buffer = ctypes.create_unicode_buffer(capacity)
        length = get_name(wintypes.HANDLE(handle), buffer, capacity, 0)
        if length == 0 or length >= capacity:
            raise ValueError("windows_open_handle_provenance_unavailable")
        actual = buffer.value
        # GetFinalPathNameByHandleW normally returns \\?\C:\\... . Reject
        # unsupported namespace forms instead of treating them as safe.
        prefix = "\\\\?\\"
        if not actual.startswith(prefix):
            raise ValueError("windows_open_handle_provenance_unavailable")
        actual = actual[len(prefix):]
        if len(actual) < 3 or actual[1:3] != ":\\":
            raise ValueError("windows_open_handle_provenance_unavailable")
        # Windows may receive a short 8.3 alias for the selected root (RUNNER~1)
        # even though opened HANDLE names use long paths. Canonicalize only
        # the selected root, never the child path: following a swapped junction
        # in the latter would make an out-of-tree file look acceptable.
        selected_root = os.path.realpath(root)
        expected = os.path.normcase(os.path.abspath(
            Path(selected_root).joinpath(*relative.split("/"))))
        if os.path.normcase(os.path.normpath(actual)) != expected:
            raise ValueError("file_changed_or_unsafe")
    except (OSError, OverflowError, TypeError) as exc:
        raise ValueError("windows_open_handle_provenance_unavailable") from exc


def _open_without_ancestor_links(root: Path, relative: str, flags: int) -> int:
    """On POSIX, open every ancestor by directory FD, never by a traversed symlink.

    A hostile rename of an already opened directory cannot redirect later
    lookup through a newly inserted symlink. Windows retains the older path
    checks until native handle-relative, reparse-safe directory opens exist.
    """
    if not _ANCHORED_OPEN_AVAILABLE:
        return os.open(root.joinpath(*relative.split("/")), flags)
    absolute = Path(os.path.abspath(root))
    if not absolute.is_absolute():
        raise ValueError("unsafe_root")
    directory_flags = (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                       | getattr(os, "O_CLOEXEC", 0))
    fd = os.open(absolute.anchor, directory_flags)
    try:
        # Anchor at the filesystem root to prevent a replaced ancestor of the
        # chosen repository root from redirecting the path lookup.
        for component in [*absolute.parts[1:], *relative.split("/")[:-1]]:
            if component in ("", ".", ".."):
                raise ValueError("unsafe_directory_component")
            next_fd = os.open(component, directory_flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return os.open(relative.split("/")[-1], flags, dir_fd=fd)
    finally:
        os.close(fd)


def read_file(root: Path, entry: WalkFile, max_file_bytes: int) -> FileData:
    if not safe_relative(entry.path):
        raise ValueError("unsafe_relative_path")
    if not isinstance(max_file_bytes, int) or max_file_bytes < 1:
        raise ValueError("invalid_file_limit")
    path = root.joinpath(*entry.path.split("/"))
    _check_path_components(root, entry.path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = _open_without_ancestor_links(root, entry.path, flags)
    try:
        # Windows: validate opened HANDLE before any data is read; path-only
        # checks would still permit an external file to be opened in a race.
        _check_windows_open_handle(root, entry.path, descriptor)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or _is_reparse(before) or before.st_nlink > 1
                or (before.st_dev, before.st_ino) != (entry.device, entry.inode)
                or before.st_size != entry.size or before.st_size > max_file_bytes):
            raise ValueError("file_changed_or_unsafe")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(max_file_bytes + 1)
        after = os.fstat(descriptor)
        if (len(data) > max_file_bytes or len(data) != entry.size
                or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)):
            raise ValueError("file_changed_during_read")
    finally:
        os.close(descriptor)
    # A component swapped mid-read must not pass as an in-root code file,
    # even when its final inode identity matched the original scan record.
    _check_path_components(root, entry.path)
    now = path.lstat()
    if (not stat.S_ISREG(now.st_mode) or _is_reparse(now) or now.st_nlink > 1
            or (now.st_dev, now.st_ino, now.st_size)
            != (entry.device, entry.inode, entry.size)):
        raise ValueError("file_changed_or_unsafe")
    if b"\0" in data:
        raise ValueError("binary_file_skipped")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("non_utf8_file_skipped") from exc
    return FileData(
        {"path": entry.path, "language": LANGUAGES.get(Path(entry.path).suffix.casefold(), "other"),
         "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
         "symbols": [], "imports": []},
        text,
    )
