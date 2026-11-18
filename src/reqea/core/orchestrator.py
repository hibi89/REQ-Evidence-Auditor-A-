"""Frozen reqea.v1 A→B→C orchestration with fail-closed integration gates."""
from __future__ import annotations

from importlib import import_module
from pathlib import Path
from .requirements_md import parse_markdown_requirements
from .requirements_json import parse_json_requirements
from .source_ref import inspect_local_source

VERSION = "reqea.v1"
TOOL_VERSION = "0.1.0-p1"
_ALLOWED = {"CODE_CANDIDATE", "GAP_CANDIDATE", "REVIEW_REQUIRED", "UNASSESSED"}


def _unassessed(sha: str, warnings: list[str], policy_sha: str) -> dict:
    return {"schema_version": VERSION, "source_sha": sha, "policy_sha": policy_sha,
            "tool_version": TOOL_VERSION, "status": "UNASSESSED", "findings": [],
            "summary": {"code_candidates": 0, "gap_candidates": 0, "review_required": 0, "unassessed": 0},
            "warnings": sorted(set(warnings)), "verification_status": "NOT_RUN"}


def build_audit(root: str, requirements: str, *, policy_sha: str = "UNVERIFIED") -> dict:
    """Read local REQ, build bounded index and candidate findings (never PASS)."""
    if policy_sha != "UNVERIFIED" and (len(policy_sha) != 40 or any(c not in "0123456789abcdefABCDEF" for c in policy_sha)):
        raise ValueError("invalid policy SHA")
    policy_sha = policy_sha.lower() if policy_sha != "UNVERIFIED" else policy_sha
    source = inspect_local_source(root, requirements)
    sha = source["source_sha"]
    ext = Path(source["requirements_path"]).suffix.lower()
    if ext not in (".md", ".markdown", ".json"):
        raise ValueError("unsupported requirements extension")
    # Already bounded in source_ref; consume with a strict size cap.
    with open(source["requirements_path"], "rb") as stream:
        raw = stream.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("requirements too large")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("requirements must be UTF-8") from exc
    parser = parse_json_requirements if ext == ".json" else parse_markdown_requirements
    manifest = parser(text, source_document=source["source_document"],
                      source_sha=sha, policy_sha=policy_sha)
    warnings = list(source["warnings"]) + list(manifest["warnings"])
    if policy_sha == "UNVERIFIED":
        manifest.pop("policy_sha", None)  # C requires a valid pinned SHA when present
        warnings.append("policy_sha_unverified")
    try:
        indexer = import_module("reqea_codegraph").build_code_index
        evidence = import_module("reqea_evidence").evaluate
    except (ImportError, AttributeError):
        return _unassessed(sha, warnings + ["required_B_or_C_module_unavailable"], policy_sha)
    options = {"source_sha": sha, "max_files": 10000, "max_file_bytes": 2_000_000,
               "max_total_bytes": 50_000_000, "max_depth": 32}
    try:
        code_index = indexer(source["root"], options)
        if not isinstance(code_index, dict) or code_index.get("schema_version") != VERSION or code_index.get("source_sha") != sha:
            return _unassessed(sha, warnings + ["B_contract_or_SHA_mismatch"], policy_sha)
        result = evidence(manifest, code_index, {"source_sha": sha, "policy_sha": policy_sha})
        if not isinstance(result, dict) or result.get("schema_version") != VERSION or result.get("source_sha") != sha:
            return _unassessed(sha, warnings + ["C_contract_or_SHA_mismatch"], policy_sha)
        if result.get("status") not in _ALLOWED or not isinstance(result.get("findings"), list):
            return _unassessed(sha, warnings + ["C_invalid_or_untrusted_status"], policy_sha)
        if any(not isinstance(f, dict) or f.get("status") not in _ALLOWED for f in result["findings"]):
            return _unassessed(sha, warnings + ["C_invalid_finding_status"], policy_sha)
    except (ValueError, TypeError, KeyError, OSError):
        return _unassessed(sha, warnings + ["analysis_failed_without_verified_evidence"], policy_sha)
    if not isinstance(result.get("warnings", []), list) or any(not isinstance(w, str) for w in result.get("warnings", [])):
        return _unassessed(sha, warnings + ["C_invalid_warning_contract"], policy_sha)
    result["warnings"] = sorted(set(result.get("warnings", []) + warnings))
    result["policy_sha"] = policy_sha
    result["tool_version"] = TOOL_VERSION
    result["verification_status"] = "NOT_RUN"
    return result


def render_audit_html(audit: dict) -> str:
    if audit.get("status") == "UNASSESSED" and "required_B_or_C_module_unavailable" in audit.get("warnings", []):
        raise ValueError("report unavailable: B/C modules not integrated")
    renderer = import_module("reqea_evidence").render_html
    html = renderer(audit)
    if not isinstance(html, str):
        raise ValueError("invalid HTML renderer output")
    return html
