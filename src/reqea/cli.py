"""Local-only REQ Evidence Auditor command-line entry point."""
from __future__ import annotations

import argparse
import json
import sys
from .core.orchestrator import build_audit, render_audit_html
from .core.output import save_artifacts
from .core.discovery import discover_local_requirements
from .core.selector import select_requirements
from contextlib import nullcontext
from .core.snapshot import public_github_snapshot
from .core.history import compare_audits, save_delta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reqea", description="Offline REQ static-evidence candidate auditor")
    commands = parser.add_subparsers(dest="command", required=True)
    audit_cmd = commands.add_parser("audit", help="Audit a local approved checkout")
    audit_cmd.add_argument("--repo", required=True)
    audit_cmd.add_argument("--requirements", required=True)
    audit_cmd.add_argument("--out", required=True)
    audit_cmd.add_argument("--policy-sha", default="UNVERIFIED")
    audit_cmd.add_argument("--overwrite", action="store_true", help="Explicitly replace existing audit outputs")
    discover_cmd = commands.add_parser("discover", help="Read-only local or public-GitHub document discovery")
    source = discover_cmd.add_mutually_exclusive_group(required=True)
    source.add_argument("--repo", help="Explicit local repository root")
    source.add_argument("--github-url", help="Public https://github.com/OWNER/REPO")
    discover_cmd.add_argument("--ref", help="GitHub branch, tag or exact commit (not for local)")

    source_audit = commands.add_parser(
        "audit-source", help="Audit a selected local or pinned public GitHub snapshot")
    source_input = source_audit.add_mutually_exclusive_group(required=True)
    source_input.add_argument("--repo", help="Explicit approved local root")
    source_input.add_argument("--github-url", help="Approved public GitHub URL")
    source_audit.add_argument("--ref", help="GitHub ref (not valid with --repo)")
    source_audit.add_argument("--requirements", help="Root-relative discovered document; mandatory if ambiguous")
    source_audit.add_argument("--out", required=True, help="Approved local output folder outside the source")
    source_audit.add_argument("--policy-sha", default="UNVERIFIED")
    source_audit.add_argument("--overwrite", action="store_true")

    compare = commands.add_parser("compare", help="Compare two locally supplied reqea.v1 audit JSON files")
    compare.add_argument("--before", required=True, help="Explicit prior audit.json")
    compare.add_argument("--after", required=True, help="Explicit current audit.json")
    compare.add_argument("--out", required=True, help="Approved local output folder")
    compare.add_argument("--source-root", help="Optional root to enforce output outside scanned source")

    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            from pathlib import Path
            from .core.output import _check_no_symlinks
            def read_report(path: str) -> dict:
                selected = Path(path).absolute()
                _check_no_symlinks(selected)
                if not selected.is_file() or selected.stat().st_size > 2_000_000:
                    raise ValueError("audit JSON missing or oversized")
                return json.loads(selected.read_text(encoding="utf-8"))
            delta = compare_audits(read_report(args.before), read_report(args.after))
            stored = save_delta(delta, out_dir=args.out, source_root=args.source_root)
            print(json.dumps({"status": "CANDIDATE_DIFF_ONLY",
                              "changed_count": delta["changed_count"],
                              "verification_status": "NOT_RUN", **stored},
                             ensure_ascii=False))
            return 0
        if args.command == "audit-source":
            if args.repo and args.ref is not None:
                raise ValueError("--ref is only valid for --github-url")
            context = (nullcontext({"root": args.repo, "source_sha": "UNVERIFIED"})
                       if args.repo else public_github_snapshot(args.github_url, args.ref))
            with context as snapshot:
                found = discover_local_requirements(snapshot["root"])
                selected = select_requirements(found, args.requirements)
                audit = build_audit(snapshot["root"], selected["requirements_path"],
                                    policy_sha=args.policy_sha)
                fatal = {"required_B_or_C_module_unavailable", "B_contract_or_SHA_mismatch",
                         "C_contract_or_SHA_mismatch", "C_invalid_or_untrusted_status",
                         "C_invalid_finding_status", "C_invalid_warning_contract",
                         "analysis_failed_without_verified_evidence"}
                if fatal.intersection(audit.get("warnings", [])):
                    print(json.dumps({"status": "UNASSESSED", "reason": "CONTRACT_OR_MODULE_NOT_READY"}),
                          file=sys.stderr)
                    return 3
                html = render_audit_html(audit)
                saved = save_artifacts(audit, html, source_root=snapshot["root"],
                                       out_dir=args.out, overwrite=args.overwrite)
                meta = {"status": audit["status"], **saved,
                        "canonical_document": selected["relative_path"],
                        "canonical_sha256": selected["sha256"],
                        "verification_status": "NOT_RUN"}
                if args.github_url:
                    # A GitHub API pinned commit is NOT proof of a complete,
                    # Git-clean local worktree. Do not attach it as reqea.v1 source_sha.
                    meta.update({"remote": "public_github",
                                 "repository": snapshot["owner"] + "/" + snapshot["repository"],
                                 "pinned_commit_sha": snapshot["commit_sha"],
                                 "pinned_tree_sha": snapshot["tree_sha"],
                                 "source_sha": "UNVERIFIED"})
                else:
                    meta["remote"] = "none"
                print(json.dumps(meta, ensure_ascii=False, sort_keys=True))
                return 0
        if args.command == "discover":
            if args.repo:
                if args.ref is not None:
                    raise ValueError("--ref requires --github-url")
                found = discover_local_requirements(args.repo)
                summary = {"mode": "local", "status": found["status"],
                           "candidates": found["candidates"], "warnings": found["warnings"],
                           "verification_status": "NOT_RUN"}
            else:
                with public_github_snapshot(args.github_url, args.ref) as snapshot:
                    found = discover_local_requirements(snapshot["root"])
                    summary = {"mode": "github", "status": found["status"],
                               "repository": snapshot["owner"] + "/" + snapshot["repository"],
                               "commit_sha": snapshot["commit_sha"],
                               "source_sha": "UNVERIFIED",
                               "files": snapshot["file_count"],
                               "candidates": found["candidates"], "warnings": found["warnings"],
                               "verification_status": "NOT_RUN"}
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
            return 0 if summary["status"] in ("SINGLE_CANDIDATE", "AMBIGUOUS") else 2
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
