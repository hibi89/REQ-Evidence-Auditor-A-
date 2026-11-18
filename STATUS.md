# STATUS — REQ Evidence Auditor A / P2

**2026-11-18 KST — current P2 verified-code SHA `d08eb924c59d73ea287e28c18c24bb23abdf122d`**  
Branch `integration/reqea-p1-20261118`; fixed API `reqea.v1`; all 30 frozen REQ mapped.

- **P1 implementation candidate:** **17/17** (SWU count 100% candidate only; not independent verification). Official weighted P1 rate **UNASSESSED**.
- **P2 latest actual CI:** [Run 44260061253](https://github.com/hibi89/REQ-Evidence-Auditor-A-/actions/runs/44260061253) **5/5 PASS** at exact source `d08eb924c59d73ea287e28c18c24bb23abdf122d`. Linux 42 PASS + 3 Windows-only SKIP; Windows 45/45 PASS. Wheel, Windows unsigned CLI+GUI EXE build, CLI EXE synthetic Unicode path audit, Tk GUI synthetic event loop, Bandit medium/high, read-only public checkout scan with 0 modifications: **PASS**.
- **P2 gate-state reference:** 1/9 PASS for executed scope (11.1% unweighted count), 7/9 PARTIAL_PASS, 1/9 NOT_RUN. **Official verification rate UNASSESSED; independent VERIFIED NOT_ESTABLISHED.**
- **This wave:** added 9 symlink/hardlink/permission/UNC/junction/long-path tests, fixed `src/reqea/core/source_ref.py` to refuse hardlinked selected REQ files. Detailed tests, defects and SHA in `docs/P2_VERIFICATION_REPORT_20261118.md`.
- **Outstanding:** Windows 11 real-device GUI/EXE UX/endurance; broader TOCTOU and recovery; real manual workflow_dispatch; independent Codex Sol Max technical/security audit; independent Astra Max UI/UX; High final acceptance. All **NOT_RUN/HOLD**.
- **Restrictions preserved:** no main merge, Production, release, external customer original transmission, EXE upload, permission changes or force push. Subsequent report-only commit changes HEAD but not tested source.
