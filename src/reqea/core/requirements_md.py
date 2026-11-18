"""Read untrusted Markdown requirement manifests without executing embedded content."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

SCHEMA_VERSION = "reqea.v1"
_ID = re.compile(r"^REQ-\d{3}$")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(REQ-\d{3})(?:\s*[-:—]\s*|\s+)?(.*)$")
_ANY_ID = re.compile(r"\bREQ-[A-Za-z0-9-]+\b")
_REF = re.compile(r"(?<![\w/])((?:src|tests|docs|\.github)/[A-Za-z0-9_./-]+\.[A-Za-z0-9_+-]+)")
_CRITERIA = re.compile(r"^(?:\*\*)?(?:acceptance(?:\s+criteria)?|수용\s*조건|수용\s*기준)(?:\*\*)?\s*[:：-]?\s*(.*)$", re.I)
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")


def _relpath(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value or ":" in value:
        raise ValueError("unsafe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("unsafe relative path")
    return path.as_posix()


def _sha(value: str) -> str:
    if value == "UNVERIFIED":
        return value
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError("source_sha/policy_sha must be 40-hex or UNVERIFIED")
    return value.lower()


def _refs(text: str) -> list[str]:
    results: set[str] = set()
    for match in _REF.finditer(text):
        try:
            results.add(_relpath(match.group(1).rstrip(".,;:")))
        except ValueError:
            continue
    return sorted(results)


def parse_markdown_requirements(
    text: str, *, source_document: str, source_sha: str = "UNVERIFIED",
    policy_sha: str = "UNVERIFIED"
) -> dict:
    """Parse Markdown headers and conventional REQ tables to reqea.v1."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > 2_000_000 or "\x00" in text:
        raise ValueError("invalid or oversized Markdown requirements")
    document = _relpath(source_document)
    sha, policy = _sha(source_sha), _sha(policy_sha)
    records: list[dict] = []
    warnings: list[str] = []
    seen: set[str] = set()
    current: dict | None = None
    in_criteria = False
    in_fence = False

    def add(req_id: str, title: str, description: str = "", criteria: list[str] | None = None) -> dict:
        if not _ID.fullmatch(req_id) or req_id in seen:
            raise ValueError(f"invalid or duplicate requirement ID: {req_id}")
        seen.add(req_id)
        record = {"req_id": req_id, "title": title.strip(), "description": description.strip(),
                  "acceptance_criteria": list(criteria or []), "explicit_refs": [],
                  "source_document": document}
        if not record["title"]:
            warnings.append(f"{req_id}:missing_title")
        records.append(record)
        return record

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(chr(96)*3) or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = _HEADING.match(line)
        if heading:
            current = add(heading.group(1), heading.group(2))
            in_criteria = False
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if cells and _ID.fullmatch(cells[0]):
                if len(cells) < 2:
                    raise ValueError("malformed REQ table row")
                title = cells[1]
                description = cells[2] if len(cells) > 2 else ""
                criteria = [v.strip() for v in re.split(r"<br\s*/?>|\s*;\s*", cells[3], flags=re.I) if v.strip()] if len(cells) > 3 else []
                current = add(cells[0], title, description, criteria)
                in_criteria = False
            continue
        if current is None:
            continue
        match = _CRITERIA.match(stripped)
        if match:
            in_criteria = True
            if match.group(1).strip():
                current["acceptance_criteria"].append(match.group(1).strip())
            continue
        bullet = re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)(.+)", stripped)
        if in_criteria and bullet:
            current["acceptance_criteria"].append(bullet.group(1).strip())
        elif stripped and not stripped.startswith("#"):
            current["description"] += ("\n" if current["description"] else "") + stripped

    if not records:
        raise ValueError("no recognizable REQ headings or rows")
    for record in records:
        if not record["acceptance_criteria"]:
            warnings.append(f"{record['req_id']}:missing_acceptance_criteria")
        record["explicit_refs"] = _refs("\n".join([record["description"], *record["acceptance_criteria"]]))
    for value in sorted(set(_ANY_ID.findall(text)) - seen):
        if not _ID.fullmatch(value):
            warnings.append(f"unsupported_req_id:{value}")
    return {"schema_version": SCHEMA_VERSION, "source_sha": sha, "policy_sha": policy,
            "requirements": sorted(records, key=lambda r: r["req_id"]),
            "warnings": sorted(set(warnings))}
