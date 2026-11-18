# REQ Evidence Auditor — A (canonical product)

**Purpose:** offline-first Windows GUI + CLI + opt-in GitHub Actions REQ-to-code-evidence auditor. The static findings are *candidates*, never certified implementation, functional or security PASS.

**State:** P0 blueprint locked; P1 A+B+C integrated 17/17 SWU code candidates (100% SWU count only, IMPLEMENTED_UNVERIFIED); P2 NOT_RUN; official weighted implementation/verification rates UNASSESSED; commercial release HOLD. See STATUS.md and docs/INTEGRATION_LOG.md for exact source SHAs and verification limits.

- [Final blueprint](docs/FINAL_BLUEPRINT.md)
- [Frozen A/B/C interface](docs/CONTRACT_V1.md)
- [SWU-CPAA parallel queue](docs/SWU_DAG.md)
- [B/C source-copy integration protocol](docs/INTEGRATION_RUNBOOK.md)
- [P2 deferred verification queue](docs/P2_VERIFICATION_QUEUE.md)

Work areas: [A](https://github.com/hibi89/REQ-Evidence-Auditor-A-), [B](https://github.com/hibi89/REQ-Evidence-Auditor-B-), [C](https://github.com/hibi89/REQ-Evidence-Auditor-C-). **A is the only final combined product.** Exact GitHub repository names include their trailing hyphen; do not rename without separate approval. All three are public; never commit private/customer source or secrets. This design branch is not main.

**P2 execution evidence (2026-11-18):** Linux/Windows synthetic and wheel checks, Bandit static security, Windows CLI/GUI unsigned EXE build, CLI binary and Tk callback passed in [run 44258446968](https://github.com/hibi89/REQ-Evidence-Auditor-A-/actions/runs/44258446968). This is *not* Windows 11 real-user or independent sign-off. See [P2 report](docs/P2_VERIFICATION_REPORT_20261118.md); release HOLD.

**P2 latest automated evidence:** [Run 44263874334](https://github.com/hibi89/REQ-Evidence-Auditor-A-/actions/runs/44263874334) on source `c36ba2ec0e14214f2637c57ce716c31b3756a2c9` passed 6/6 jobs (Windows 51/51, Linux 48 PASS/3 SKIP), including Windows unsigned EXE synthetic runtime, Bandit security, read-only audit, and offline Chromium CSP/privacy smoke. Partial P2 only; independent/Windows 11 manual verification not performed. [Current detailed report](docs/P2_VERIFICATION_REPORT_20261118.md).
