"""Conservative, bounded local requirements discovery within an explicitly selected root.

Returns *candidates*, never executes or imports target code and never certifies
a requirements file as authoritative. All source content remains in memory.
"""
from __future__ import annotations

import re
from pathlib import Path

from reqea_codegraph.files import read_file
from reqea_codegraph.walk import scan_tree
from .requirements_json import parse_json_requirements
from .requirements_md import parse_markdown_requirements

MAX_FILES = 750
MAX_BYTES = 8_000_000
MAX_DEPTH = 5
MAX_DOC_BYTES = 256_000
_DENIED = frozenset({"secret", "secrets", "credentials", "private", ".git",
                      ".ssh", ".aws", "node_modules", "venv", "env", "dist", "build"})
_KNOWN = frozenset({"requirements.md", "requirements.markdown", "requirements.json",
                    "final_blueprint.md", "final_blueprint.markdown", "final_design.md",
                    "final_spec.md"})
_REFS = re.compile(r"(?<![\w/])((?:docs/|design/)[A-Za-z0-9_./+\-]{1,180}\.(?:md|markdown|json))", re.I)
_REQ_ROW = re.compile(r"(?m)^(?:\s{0,3}#{1,6}\s+REQ-\d{3}\b|\|\s*REQ-\d{3}\s*\|)")


def _allowed_path(relative: str) -> bool:
    parts = relative.replace("\\", "/").split("/")
    return bool(parts) and all(
        part not in ("", ".", "..")
        and not part.startswith(".")
        and part.casefold() not in _DENIED
        and not part.casefold().startswith((".env", "secret", "credential"))
        for part in parts
    )


def _interesting(relative: str, linked: set[str]) -> bool:
    if not _allowed_path(relative):
        return False
    name = relative.rsplit("/", 1)[-1].casefold()
    if relative.casefold() in {ref.casefold() for ref in linked}:
        return True
    return (name in _KNOWN or name.startswith("final_blueprint")
            or name.startswith("final_design") or name.startswith("최종설계")
            or name.startswith("requirements_")) and name.endswith((".md", ".markdown", ".json"))


def discover_local_requirements(root: str) -> dict:
    """Return safe root-relative candidates and conservative ambiguity diagnostics.

    An oversized/incomplete walk or an unreadable candidate prevents selection.
    README/AGENTS content is used ONLY to extract in-root reference strings.
    """
    if not isinstance(root, str) or not root or not Path(root).is_absolute():
        raise ValueError("explicit absolute project root required")
    scan = scan_tree(root, {"max_files": MAX_FILES, "max_file_bytes": MAX_DOC_BYTES,
                            "max_total_bytes": MAX_BYTES, "max_depth": MAX_DEPTH})
    root_path = scan.root
    indexed = {f.path: f for f in scan.files}
    linked: set[str] = set()
    warnings: set[str] = set()
    blocked = bool(scan.truncated or scan.warning_limited)
    if blocked:
        warnings.add("INCOMPLETE_DISCOVERY_SCOPE")
    if any("link_skipped:" in w for w in scan.warnings):
        warnings.add("UNSAFE_ENTRIES_SKIPPED")

    for path in ("AGENTS.md", "README.md", "REQUIREMENTS.md"):
        entry = indexed.get(path)
        if entry is None:
            continue
        try:
            doc = read_file(root_path, entry, MAX_DOC_BYTES)
        except (OSError, ValueError):
            blocked = True
            warnings.add("REFERENCE_DOCUMENT_UNREADABLE")
            continue
        for match in _REFS.finditer(doc.text):
            ref = match.group(1)
            if _allowed_path(ref) and ref in indexed:
                linked.add(ref)

    candidates: list[dict] = []
    for relative, entry in sorted(indexed.items()):
        if not _interesting(relative, linked):
            continue
        try:
            doc = read_file(root_path, entry, MAX_DOC_BYTES)
            # A README pointer to a requirements file is not itself a REQ manifest.
            if relative.endswith((".md", ".markdown")) and not _REQ_ROW.search(doc.text):
                continue
            if relative.casefold().endswith(".json"):
                parsed = parse_json_requirements(doc.text, source_document=relative)
            else:
                parsed = parse_markdown_requirements(doc.text, source_document=relative)
            if not parsed.get("requirements"):
                continue
        except (OSError, UnicodeError, ValueError):
            blocked = True
            warnings.add("CANDIDATE_UNREADABLE_OR_INVALID")
            continue
        candidates.append({
            "path": relative,
            "sha256": doc.record["sha256"],
            "req_count": len(parsed["requirements"]),
            "reason": "EXPLICIT_DOCUMENT_REFERENCE" if relative in linked else "STANDARD_DOCUMENT_NAME",
        })
        if len(candidates) > 32:
            blocked = True
            warnings.add("TOO_MANY_CANDIDATES")
            break

    status = ("BLOCKED" if blocked else "NO_CANDIDATE" if not candidates
              else "SINGLE_CANDIDATE" if len(candidates) == 1 else "AMBIGUOUS")
    return {"status": status, "root": str(root_path), "candidates": candidates,
            "warnings": sorted(warnings), "scanned_files": len(scan.files)}
