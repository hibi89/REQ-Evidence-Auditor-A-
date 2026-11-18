# REQ Evidence Auditor A — P2 independent-review handoff (2026-11-18 KST)

## Decision: SELF_P2_SCOPED_DONE → INDEPENDENT_REVIEW_READY, NOT product VERIFIED
A author-side P2 automation, synthetic recovery, cross-platform package, static Bandit, read-only checkout, and offline Chromium checks were executed. Repeating the same author-side test matrix is not a prerequisite for beginning independent review. This is **a workflow handoff**, not acceptance of previously unexecuted gates.

- Authoritative product: \`hibi89/REQ-Evidence-Auditor-A-\`
- Integration branch: \`integration/reqea-p1-20261118\` (**never \`main\` without separate owner GO**)
- Exact tested code+tests SHA: \`49b4a207706bfc84a77fc638dcd6a04bf2628323\`
- The prior functional guard code was introduced at \`32f133cb1ab8203edae7c264bf4de6977612a9f0\`.
- [Actions evidence 44267405032](https://github.com/hibi89/REQ-Evidence-Auditor-A-/actions/runs/44267405032): SUCCESS **6/6 jobs** at tested SHA; Windows Server 2025 **56/56 tests PASS**, Ubuntu 24.04 **53 PASS / 3 SKIP**, unsigned CLI/GUI EXE CI build and synthetic GUI callbacks, wheel, Bandit, Chromium file://, zero-mutation public checkout PASS.
- P1 source candidates **17/17 SWU**, requirements mapped **30/30 REQ**. Official *weighted* implementation/verification rates both **UNASSESSED**; not 100% acceptance.
- P2 9-gate *unweighted reference states*: P2-03 and P2-06 scoped PASS (2); P2-01/02/04/05/07/08 PARTIAL_PASS (6); P2-09 NOT_RUN (1). None may be promoted to full acceptance without relevant independent evidence.

## Reviewer 1 — Codex technical/security (MODEL_UNVERIFIED until actually launched)
**Goal:** independent P2 review of immutable source baseline, defects repaired and retested; do not treat author-side CI as an independent audit.

**Instructions to paste into a Codex review session:**

> REQ Evidence Auditor A의 독립 P2 기술·보안 검수자다. \`hibi89/REQ-Evidence-Auditor-A-\`의 \`integration/reqea-p1-20261118\`에서 먼저 원격 HEAD와 기준 구현 SHA \`49b4a207706bfc84a77fc638dcd6a04bf2628323\`를 확인하고 \`AGENTS.md\`, \`docs/FINAL_BLUEPRINT.md\`, 고정 \`docs/CONTRACT_V1.md\`, \`docs/P2_VERIFICATION_REPORT_20261118.md\` 및 실제 A/B/C 소스를 독립 점검하라. 소스 import/실행·네트워크 전송·고객 원본 업로드 없이 합성 로컬 자료로 탐색 경계, symlink/junction/hardlink, cwd/UNC, race/TOCTOU, 중단된 결과물 3종, \`--overwrite\` 잠금 소유권·다중 writer, 잘못된 JSON/REQ, 숨김 secret·HTML escaping·CSP·Git SHA provenance·무허가 VERIFIED를 공격적으로 검증하라. P2-01/02/05/08과 30 REQ 계약을 근거별 PASS/FAIL/NOT_RUN으로 구분하라. 결함은 보호된 별도 작업 브랜치에서 실제 수정·국소 재검증·SHA와 함께 보고하되, 원본/권한/고객 자료/외부 전송·main 병합·배포·출시 변경은 사용자 GO 없이 수행하지 말라. 검수 모델/실행/증거가 없으면 NOT_RUN, 스스로 작성한 변경에 대한 자기 확인은 독립 재검수로 오인하지 말라.

**Priority risk:** crash/power-loss group atomicity NOT_PROVEN; external lock deletion/directory replacement race NOT_PROVEN. Existing code intentionally fails closed on an abandoned \`.reqea-transaction.lock\` or \`.reqea-*\` remnants. Never remove/recover these automatically; do not accept destructive "fix" that erases original output or recovery backups.

## Reviewer 2 — Astra independent GUI/UX (MODEL_UNVERIFIED until actually launched)
**Goal:** Windows desktop app usability and visible functionality, not a static screenshot-only approval.

**Instructions to paste into Astra review session:**

> REQ Evidence Auditor A의 독립 Astra UI/UX 검수자다. 원격 \`hibi89/REQ-Evidence-Auditor-A-@integration/reqea-p1-20261118\`에서 \`docs/FINAL_BLUEPRINT.md\`의 Windows 로컬 EXE/CLI 제품 계약과 \`src/reqea/gui/app.py\` 코드를 확인하라. \`docs/P2_INDEPENDENT_AUDIT_HANDOFF_20261118.md\`의 정확 코드 기준과 기존 Windows Server 합성 검사를 읽되, 실제 Windows 11 UI 실기기 검사가 없는 상태를 PASS로 꾸미지 말라. 폴더·REQ 선택, 분석 진행/취소·오류, 결과 확인/다시 실행, 긴 한글 경로·Windows scaling/DPI, 키보드 탐색/접근성·레이아웃·오프라인 안전성을 검사하라. 실제 UI 실행·시각 증거·수정 SHA를 남기고, 실행 환경이 없으면 Windows 11 검증을 NOT_RUN으로 유지하라. 권한 확대, 고객 데이터 외부 전송, 공개 EXE 업로드, main/Production/판매는 금지한다.

## Separate owner/environment gates — do not attribute to Codex/Astra automatically
1. **Real Windows 11 portable EXE GUI, install/launch/close/relaunch and Korean/long path** (P2-04): requires an actual Windows 11 session, local synthetic input and UI evidence; Windows Server 2025 runner is not equivalent. Work may assist only with an actually accessible suitable environment. Status NOT_RUN.
2. **Real manual \`workflow_dispatch\`** (P2-07): connector does not offer a dispatch action. Running a push-triggered CI is not this acceptance; test only on approved public checkout, with read-only token, zero private artifacts. Status NOT_RUN.
3. **Owner final High acceptance and any merge/release/paid registration:** no independent audit evidence yet; status HOLD / NOT_RUN. Do not auto-approve by passage of time.

## Handoff acceptance accounting
- Current phase: \`INDEPENDENT_REVIEW_READY\` for A-owned author-side scoped P2. This is **not** \`VERIFIED\` and does not reduce approved final design or P2 acceptance gates.
- The next action is **start Codex independent security/technical review and Astra independent GUI/UX review**; coordinate non-conflicting refs before integrating any proposed changes. Only explicit test evidence may upgrade status.
- Keep \`docs/P2_VERIFICATION_REPORT_20261118.md\`, \`docs/P2_VERIFICATION_QUEUE.md\`, and \`HANDOFF.md\` as historical evidence; avoid duplicative author-side CI runs unless source changes require them.
- No change to repo \`main\`, Production, B/C repo history, public customer artifacts, permissions, signing or release.
