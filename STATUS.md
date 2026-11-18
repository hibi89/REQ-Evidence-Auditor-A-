# STATUS — REQ Evidence Auditor A / P2

**2026-11-18 KST · latest verified test/source SHA `49b4a207706bfc84a77fc638dcd6a04bf2628323` (run 44267405032); historical runs retained below**
- Repo `hibi89/REQ-Evidence-Auditor-A-`, branch `integration/reqea-p1-20261118`. Frozen contract `reqea.v1`; A/B/C P1 **17/17 source code candidates** and 30/30 REQ mapped; official implementation weighted rate **UNASSESSED**.
- P2 [Actions 44263874334](https://github.com/hibi89/REQ-Evidence-Auditor-A-/actions/runs/44263874334) **6/6 jobs PASS**. Windows Python3.11 **51/51 PASS**, Ubuntu **48 PASS + 3 OS SKIP**; wheel on both OS PASS. Windows unsigned CLI/GUI EXE build, CLI executable Unicode-path synthetic audit, GUI Tk synthetic event-loop PASS. Bandit medium/high, 30-REQ checkout with zero Git changes, and headless Chromium offline HTML script/CSP/privacy/no network **PASS**.
- Security and recovery fixes: explicit `--overwrite` checks target links/reparse points, backs up prior inode, rolls back an injected second-file write failure, preserves backup if restoration also fails. **Crash atomicity/hostile races not proven**.
- **P2 9-gate reference count: 2 PASS for tested scope (22.2% unweighted), 6 PARTIAL_PASS, 1 NOT_RUN. Official verification rate UNASSESSED, independent VERIFIED NOT_ESTABLISHED.**
- Remaining P2: real Windows 11 GUI/EXE manual use, full crash/recovery/race coverage, actual manual workflow_dispatch, independent Codex technical/security and Astra UI/UX audits, High acceptance. Main/Production/release HOLD.
- Exact CI job IDs, source SHA and limitations: `docs/P2_VERIFICATION_REPORT_20261118.md`. A documentation-only commit after `c36ba2ec0e14214f2637c57ce716c31b3756a2c9` is not a new verified product-source SHA.
- No customer data export, privilege change, release, unsigned EXE publication or main merge.

## P2 current verification addition — 2026-11-18 KST
- New exact verified product source `32f133cb1ab8203edae7c264bf4de6977612a9f0`; [Actions 44266186783](https://github.com/hibi89/REQ-Evidence-Auditor-A-/actions/runs/44266186783) SUCCESS **6/6**: Windows Server CI 54 PASS; Linux 51 PASS + 3 OS SKIP. Three added interrupted-lock/recovery-blocker tests passed on both runner OSes.
- `src/reqea/core/output.py`: cooperative concurrent writes and interrupted/stale lock or backup detected and blocked. Original data preserved in synthetic exception tests. **Crash atomicity, hostile external race, automatic restart recovery remain NOT_RUN.**
- P2 reference counts remain 2/9 scoped PASS, 6/9 PARTIAL, 1/9 NOT_RUN; official weighted verification **UNASSESSED**. 17/17 P1 code candidates; official implementation weighted UNASSESSED. Real Windows 11 manual GUI, manual dispatch, independent Codex/Astra and final acceptance NOT_RUN, release/main HOLD.

## 2026-11-18 additional P2 subprocess evidence
- New test-only source SHA `49b4a207706bfc84a77fc638dcd6a04bf2628323`: [Actions 44267405032](https://github.com/hibi89/REQ-Evidence-Auditor-A-/actions/runs/44267405032) **SUCCESS 6/6**; Windows Server 2025 **56 PASS**, Ubuntu **53 PASS / 3 SKIP**. Actual separate processes verified post-`os._exit` fail-closed recovery lock in new/overwrite modes and cooperating simultaneous writer exclusion. Synthetic local data only.
- P2 gate distribution **2 scoped PASS / 6 PARTIAL_PASS / 1 NOT_RUN**; official weighted P2 **UNASSESSED**, not 100%. Real power-loss atomicity, hostile directory swap, full restart recovery, Windows 11 user GUI, actual manual workflow_dispatch, independent Codex/Astra and High acceptance NOT_RUN. Main/production/release HOLD. P1 remains 17/17 source candidates, official weighted P1 UNASSESSED.
