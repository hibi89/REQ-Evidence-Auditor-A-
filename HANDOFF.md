# HANDOFF — REQEA A P1 code candidate to P2
Date: 2026-11-18 15:44 KST. Owner: A integration lead. Product `hibi89/REQ-Evidence-Auditor-A-`, branch `integration/reqea-p1-20261118`.

## Gate and exact source
- P0 final design SHA `e58e14ee4ef84dfc226d657cfe45b1d40cfb9ba9`, fixed contract `reqea.v1` blob `b39d8307662206472f2165b4bce3c0e10e2b62b6`.
- Source+smoke integration commit `7e8b9ef88ebbc68d995b4dc470668ac7fd3bcdaf`, P1 code-candidate 17/17 (A 7, B 5, C 5); official weighted implementation `UNASSESSED`. This HANDOFF and updated queue are committed afterward; use branch HEAD for final integration ref.
- A local feature SHA `07d1ba30ee85b7b50355d69a075ab0a12e4e05fc`. B source SHA `ff7741477727a42adb9a8db09019ebb1159834bf`. C source SHA `7a3c760ea36f0fbb5fcfdf41aadfb5aa976c7f60`.
- B/C code and tests copied into A integration **only after exact source SHA and 13/13 SHA256 match**, see `docs/INTEGRATION_LOG.md`; B/C repos/commit history not deleted.
- [P1 synthetic smoke Run 44252969444](https://github.com/hibi89/REQ-Evidence-Auditor-A-/actions/runs/44252969444): **PASS**; compileall and 3/3 synthetic integration unittests plus CLI/HTML/JSON smoke. B and C independently reported local 3/3 and 15/15. No customer/real repository content tested.
- A files: `src/reqea/**`, `pyproject.toml`, `.github/workflows/reqea-audit.yml`. B: `src/reqea_codegraph/**`, `tests/b/**`; C: `src/reqea_evidence/**`, `tests/c/**`; A integration test: `tests/integration/test_p1_smoke.py`.
- Unverified: Windows tkinter GUI live launch and Windows EXE build; manual read-only workflow_dispatch; P2 integration/negative security/TOCTOU/race/symlink/big-input regressions; independent technical/security and Astra UI audits. `P2 NOT_RUN`, `VERIFIED`/release `HOLD`.
- Remaining P1 READY: none in agreed 17-SWU DAG, unless user changes scope or P2 discovers defects.
- Next: user supplies planned separate verification prompt. No main merge, release, permissions, data transfer, B/C deletion.
- Time: A start 15:08:51, B 15:07→15:19, C 15:08:52→15:25:43, integration smoke merge 15:41:06 KST. Serial-vs-parallel speed `UNMEASURED`; no inferred acceleration multiplier.
