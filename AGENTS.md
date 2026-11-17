# AGENTS — REQ Evidence Auditor A (최종설계·통합 정본)

CURRENT_MISSION = REQ Evidence Auditor, A = P0 canonical design + P1 local GUI/CLI/core implementation + final B/C code integration. 다른 제품·Repository Provisioner 작업으로 이동 금지.

Owner: hibi89 / A canonical repo: https://github.com/hibi89/REQ-Evidence-Auditor-A-. Parallel: B=https://github.com/hibi89/REQ-Evidence-Auditor-B-, C=https://github.com/hibi89/REQ-Evidence-Auditor-C-.
Central policy authority: https://github.com/hibi89/hackathon-command-center-2026/blob/kmong-productization/docs/strategy/OWNER_DEV_EXECUTION_CANONICAL_20261116.md §0J and .../GPT6_HIGH_STANDARD_WORK_UNIT_20261117.md §0E. Last verified central SHA `f633dcf1d3c533d2b674648e4a6515d80b85f05c`; ALWAYS refresh remote HEAD per new execution. Current user instruction > product-specific safety/final blueprint > central policy > code evidence > old status.

Read order: current repo/branch/HEAD → AGENTS → HANDOFF → STATUS → REQUIREMENTS → docs/FINAL_BLUEPRINT.md → docs/CONTRACT_V1.md → docs/SWU_DAG.md → real source. Do not treat document presence as implementation.

A owns `src/reqea/**`, `tests/a/**`, `docs/**`, `pyproject.toml`, `.github/**`; B/C code only integrated from owned `src/reqea_codegraph/**` and `src/reqea_evidence/**`. Shared JSON contract reqea.v1 is LOCKED; no unilateral change. A integration branch is NOT main.

Use SWU-CPAA+SWU-WE actual functionality, 1–6 safe READY SWUs per `ㄱ` when possible, real caller→callee + failure paths, minimum syntax/type/smoke; 2+2 isolation and conditional Sol Max. P1 implementation code only; P2 full CI/browser/security/Windows/independent audit deferred. High retains design/accountability until verified future transition. 3 web GPT chats are human started, not automatically spawned.

NO paid calls, customer files outside machine, source import/execution, dangerous DB operations, secrets, permission changes, force push, main merge, Production, release or B/C deletion without explicit owner GO. Do not publish raw customer code, paths or secrets to public GitHub. Progress: exact SHA, SWUs, real paths/tests/P1 candidates, P2 NOT_RUN, unresolved issues; official rates UNASSESSED if no approved weights.
