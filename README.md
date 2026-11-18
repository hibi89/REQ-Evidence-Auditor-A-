# REQ Evidence Auditor — A (canonical product)

**Purpose:** offline-first Windows GUI + CLI + opt-in GitHub Actions REQ-to-code-evidence auditor. The static findings are *candidates*, never certified implementation, functional or security PASS.

**State:** P0 blueprint locked; P1 A+B+C integrated 17/17 SWU code candidates (100% SWU count only, IMPLEMENTED_UNVERIFIED); P2 NOT_RUN; official weighted implementation/verification rates UNASSESSED; commercial release HOLD. See STATUS.md and docs/INTEGRATION_LOG.md for exact source SHAs and verification limits.

- [Final blueprint](docs/FINAL_BLUEPRINT.md)
- [Frozen A/B/C interface](docs/CONTRACT_V1.md)
- [SWU-CPAA parallel queue](docs/SWU_DAG.md)
- [B/C source-copy integration protocol](docs/INTEGRATION_RUNBOOK.md)
- [P2 deferred verification queue](docs/P2_VERIFICATION_QUEUE.md)

Work areas: [A](https://github.com/hibi89/REQ-Evidence-Auditor-A-), [B](https://github.com/hibi89/REQ-Evidence-Auditor-B-), [C](https://github.com/hibi89/REQ-Evidence-Auditor-C-). **A is the only final combined product.** Exact GitHub repository names include their trailing hyphen; do not rename without separate approval. All three are public; never commit private/customer source or secrets. This design branch is not main.
