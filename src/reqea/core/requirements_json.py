"""Strict JSON requirement reader for the frozen reqea.v1 manifest contract."""
from __future__ import annotations

import json
import re
from pathlib import PurePosixPath

SCHEMA_VERSION = "reqea.v1"
_ID = re.compile(r"REQ-\d{3}\Z")
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")


def _relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value or ":" in value:
        raise ValueError("unsafe document or reference path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("unsafe document or reference path")
    return path.as_posix()


def _sha(value: object) -> str:
    if value == "UNVERIFIED":
        return value
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError("invalid source_sha or policy_sha")
    return value.lower()


def _str(value: object, name: str, size: int, *, required: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value or len(value) > size or (required and not value.strip()):
        raise ValueError(f"invalid {name}")
    return value.strip()


def parse_json_requirements(
    text: str, *, source_document: str, source_sha: str = "UNVERIFIED",
    policy_sha: str = "UNVERIFIED"
) -> dict:
    if not isinstance(text, str) or len(text.encode("utf-8")) > 2_000_000 or "\x00" in text:
        raise ValueError("invalid or oversized JSON requirements")
    doc = _relative_path(source_document)
    sha, policy = _sha(source_sha), _sha(policy_sha)

    def no_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        data = json.loads(text, object_pairs_hook=no_duplicates,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON number")))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid JSON requirements") from exc
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        if data.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
            raise ValueError("unsupported requirement schema_version")
        rows = data.get("requirements")
    else:
        raise ValueError("JSON requirements must be an object or list")
    if not isinstance(rows, list) or not rows or len(rows) > 2000:
        raise ValueError("requirements must be nonempty bounded array")
    records: list[dict] = []
    seen: set[str] = set()
    warnings: list[str] = []
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("requirement entry must be object")
        rid = item.get("req_id")
        if not isinstance(rid, str) or not _ID.fullmatch(rid) or rid in seen:
            raise ValueError("invalid or duplicate req_id")
        seen.add(rid)
        title = _str(item.get("title"), "title", 512, required=True)
        description = _str(item.get("description", ""), "description", 8192)
        criteria = item.get("acceptance_criteria", [])
        refs = item.get("explicit_refs", [])
        if not isinstance(criteria, list) or len(criteria) > 40 or not isinstance(refs, list) or len(refs) > 100:
            raise ValueError("invalid acceptance_criteria or explicit_refs")
        normalized_criteria = [_str(c, "acceptance criterion", 2048, required=True) for c in criteria]
        normalized_refs = sorted({_relative_path(r) for r in refs})
        if not normalized_criteria:
            warnings.append(f"{rid}:missing_acceptance_criteria")
        if "source_document" in item and item["source_document"] != doc:
            raise ValueError("conflicting requirement source_document")
        records.append({"req_id": rid, "title": title, "description": description,
                        "acceptance_criteria": normalized_criteria,
                        "explicit_refs": normalized_refs, "source_document": doc})
    return {"schema_version": SCHEMA_VERSION, "source_sha": sha, "policy_sha": policy,
            "requirements": sorted(records, key=lambda r: r["req_id"]),
            "warnings": sorted(set(warnings))}
