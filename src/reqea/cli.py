"""Local-only REQ Evidence Auditor command-line entry point."""
from __future__ import annotations

import argparse
import json
import sys
from .core.orchestrator import build_audit, render_audit_html
from .core.output import save_artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reqea", description="Offline REQ static-evidence candidate auditor")
    commands = parser.add_subparsers(dest="command", required=True)
    audit_cmd = commands.add_parser("audit", help="Audit a local approved checkout")
    audit_cmd.add_argument("--repo", required=True)
    audit_cmd.add_argument("--requirements", required=True)
    audit_cmd.add_argument("--out", required=True)
    audit_cmd.add_argument("--policy-sha", default="UNVERIFIED")
    audit_cmd.add_argument("--overwrite", action="store_true", help="Explicitly replace existing audit outputs")
    args = parser.parse_args(argv)
    try:
        result = build_audit(args.repo, args.requirements, policy_sha=args.policy_sha)
        fatal = {"required_B_or_C_module_unavailable", "B_contract_or_SHA_mismatch",
                 "C_contract_or_SHA_mismatch", "C_invalid_or_untrusted_status",
                 "C_invalid_finding_status", "C_invalid_warning_contract",
                 "analysis_failed_without_verified_evidence"}
        if fatal.intersection(result.get("warnings", [])):
            print(json.dumps({"status": "UNASSESSED", "reason": "CONTRACT_OR_MODULE_NOT_READY"}), file=sys.stderr)
            return 3
        report = render_audit_html(result)
        info = save_artifacts(result, report, source_root=args.repo, out_dir=args.out, overwrite=args.overwrite)
        print(json.dumps({"status": result["status"], **info}, ensure_ascii=False))
        return 0
    except (ValueError, UnicodeError, FileNotFoundError, PermissionError, FileExistsError, OSError, ImportError) as exc:
        print(json.dumps({"status": "UNASSESSED", "error_type": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
