# REQ Evidence Auditor — SWU-CPAA 병렬 실행 큐 V1
**기준:** 해총 `f633dcf1d3c533d2b674648e4a6515d80b85f05c` / A 최종설계/계약 고정. **P1 총 17개 SWU 후보(A7/B5/C5)**; 실제 소스 감사 후 REQ·작업 크기 재산정 가능하나 REQ 번호/의존성/수용조건·이력 소실 금지. `NOT_STARTED` 17개, `IMPLEMENTED_UNVERIFIED` 0개, 검증 `NOT_RUN`. 이는 **설계상 작업 분모**이며 구현완료율 0% 공식 측정 선언이 아님.

## 소유권 및 파일 충돌 억제
- A만 `src/reqea/**`, `docs/**`, `.github/**`, `pyproject.toml`, `tests/a/**` 작업한다.
- B만 `src/reqea_codegraph/**`, `tests/b/**` 작업한다.
- C만 `src/reqea_evidence/**`, `tests/c/**` 작업한다.
- B/C 작업자가 공통 파일(AGENTS, HANDOFF, STATUS, JSON 계약)을 수정할 때는 자신의 저장소에서만 가능하고 A로 파일 복사 금지. A 계약을 변경하고 싶으면 요청을 발행하고 수정은 통합자가 한다.
- **서로 다른 저장소 / 서로 다른 기준 계약 버전**을 구분한다. 동일 Git commit SHA를 공유할 수 없으므로 기준은 `A contract SHA` + 각 repo 자체 기준 SHA이고, 모듈 코드를 통합할 때 file SHA256·commit 증거를 기록.

## 기능별 SWU
| SWU | REQ | owner | depends_on | 주요 코드 경로 | 수용 가능한 P1 코드 경로 |
|---|---|---|---|---|---|
| A-01 Markdown REQ-ID/수용조건 파서, 중복·불명확 경고 | REQ-003 | A | — | `src/reqea/core/requirements_md.py` | 단일 문서→RequirementManifest; 중복/무효 REQ 오류 분기 |
| A-02 구조화 JSON 요구사항 파서/타입 검증 | REQ-004 | A | — | `src/reqea/core/requirements_json.py` | 유효/무효 JSON→동일 정규화 구조, 악성 입력 거절 |
| A-03 로컬 경로 및 Git SHA provenance 읽기전용 경계 | REQ-005,REQ-006 | A | — | `src/reqea/core/source_ref.py` | source_sha 유효/미확인 구분, 대상 파일 미변경 |
| A-04 고정 계약 버전으로 B/C 분석/매칭 연결 | REQ-007,REQ-030 | A | A-01,A-02,A-03,B-05,C-04 | `src/reqea/core/orchestrator.py` | source_sha/contract 불일치 차단, 결과 반환 |
| A-05 CLI audit 및 안전 산출물 저장 | REQ-002,REQ-008 | A | A-04 | `src/reqea/cli.py,src/reqea/core/output.py` | 로컬 명령→JSON/HTML 파일; 권한 거절 실패 처리 |
| A-06 Tkinter GUI 로컬 파일 선택·진행·결과 | REQ-001,REQ-010 | A | A-05 | `src/reqea/gui/` | GUI→동일 CLI 엔진, 한글/오류 메시지 |
| A-07 GitHub Actions 읽기전용 CLI 실행기 및 P1/P2 표시 | REQ-009,REQ-029 | A | A-05 | `.github/workflows/reqea-audit.yml` | 명시적 workflow_dispatch/read-only checkout, 증거 PASS 남발 금지 |
| B-01 경로·symlink·제외 목록·depth/byte/files 제한 walker | REQ-011,REQ-012 | B | — | `src/reqea_codegraph/walk.py` | 경로이탈·민감 파일 기본 제외, 제한 초과 경고 |
| B-02 파일 메타/언어/SHA256 정규화 | REQ-013 | B | B-01 | `src/reqea_codegraph/files.py` | 같은 내용에 deterministic SHA256/path |
| B-03 Python AST 심볼/라인/임포트 인덱스 | REQ-014 | B | B-02 | `src/reqea_codegraph/python_ast.py` | 코드 실행 없이 함수/클래스/라인 출력 |
| B-04 Python 관계 후보 + JS/TS 제한적 static parser | REQ-015,REQ-016 | B | B-03 | `src/reqea_codegraph/relations.py` | 관계 후보와 동적 해석 미지원 경고 |
| B-05 정적 인덱스 엔트리 build_code_index + file-level 오류 복구 | REQ-017,REQ-018 | B | B-01,B-02,B-03,B-04 | `src/reqea_codegraph/__init__.py` | 계약 JSON, 개별 실패/scan truncate 표시 |
| C-01 REQ-ID·explicit_ref·criteria 정적 후보 상호 연결 | REQ-019,REQ-021 | C | — | `src/reqea_evidence/matcher.py` | 동일 경로/심볼 근거 후보 및 criteria 별 불명확성 |
| C-02 상태 결정기: candidate/review/gap/unassessed | REQ-020,REQ-023 | C | C-01 | `src/reqea_evidence/classify.py` | 미지원/제한 scan 시 false PASS/false GAP 금지 |
| C-03 SHA 불일치·모순 근거 경고 | REQ-022,REQ-027 | C | C-02 | `src/reqea_evidence/provenance.py` | 다른 SHA 근거 합치지 않고 warnings로 처리 |
| C-04 evaluate() + deterministic audit JSON 집계 | REQ-024,REQ-029 | C | C-01,C-02,C-03 | `src/reqea_evidence/__init__.py` | 정렬된 findings, status/summary 일관 |
| C-05 XSS-safe HTML 오프라인 report renderer | REQ-025,REQ-026,REQ-028 | C | C-04 | `src/reqea_evidence/report.py` | untrusted title/path escape, secret/code full text 제외 |

## CPAA 작업 순서
**첫 웨이브 (독립·동시):** A-01/A-02/A-03, B-01, C-01. C-01은 고정 샘플 스키마로 독립 검증하며 A 코드 호출 금지.
**두 번째:** B-02/B-03, C-02/C-03, A의 입력/로컬 GUI 스캐폴딩은 실제 기능 연결 조건에 맞춰 진행.
**세 번째:** B-04→B-05, C-04→C-05, A-04→A-05→A-06/A-07.
A가 B/C 개발 완료를 기다리느라 READY인 A 코딩을 중단하지 않는다. 각 챗 `ㄱ`는 본인 작업창·repo·branch의 실제 기능 READY 1~6개를 안전 범위에서 작성/국소검사/커밋. 정본 설계를 임의로 조용히 축소하지 않는다.

## 재시도와 상태
SWU별 `status=READY|IN_PROGRESS|IMPLEMENTED_UNVERIFIED|ISOLATED_REDESIGN_PENDING|SOLMAX_BATCH_PENDING|BLOCKED_APPROVAL`; 실패 2회 격리, 방법 전환 2회, 누적 4회 Sol Max 배치. 실제 코드/오류/SHA가 없는 조회·문서 정리·CI 폴링은 시도로 집계하지 않는다. 반드시 다음 READY 계속. 핵심 고위험 문제는 즉시 전문 지원 요청 가능. 모든 `ㄱ` 종료 시 SWU별 경로·정확 SHA·국소 PASS/FAIL/NOT_RUN·다음 READY만 짧게 보고한다.

## V1.1 확장 작업 DAG — A-08..A-14 추가, 기존 17개 SWU 불변 (2026-11-19 KST)

신규 P1 7개 전부 NOT_STARTED; **현 시점 READY**는 A-08 및 A-10이며 다른 작업은 BLOCKED_DEPENDENCY. S/C/I/D/U 상세 수치는 초기 UNASSESSED, 속도 효과 UNMEASURED. Owner A 웹 GPT-6 Sol High, 기존 B/C 코드 직접 변경 금지. **문서·Mock만으로 SWU 완료 처리 금지**.

| SWU | REQ | depends_on | allowed_paths | 실기능 및 핵심 실패 경로 | 초기 상태 |
|---|---|---|---|---|---|
| A-08 | REQ-031, REQ-032 | A-03,A-06 | src/reqea/core/discovery.py; src/reqea/gui/app.py; tests/a/** | GUI/CLI 선택 루트→bounded 후보 탐색→목록, symlink/권한오류 STOP | READY |
| A-09 | REQ-033 | A-08 | src/reqea/core/discovery.py; src/reqea/core/selector.py; src/reqea/gui/app.py; tests/a/** | AGENTS/README/표준 경로 정본 근거/중복 탐지→사용자 선택/AMBIGUOUS 거부 | BLOCKED_DEPENDENCY |
| A-10 | REQ-034, REQ-035 | A-03 | src/reqea/core/github_source.py; src/reqea/core/snapshot.py; src/reqea/cli.py; tests/a/** | URL+ref 검사→공개 HTTPS exact commit pin→안전 임시 snapshot, 호스트/redirect·비밀·limit 차단 | READY |
| A-11 | REQ-036 | A-09,A-10,A-04 | src/reqea/core/snapshot.py; src/reqea/core/orchestrator.py; src/reqea/cli.py; tests/a/** | source SHA 검증/UNVERIFIED→기존 A/B/C 분석 호출→보수적 provenance 출력·ref 변경 차단 | BLOCKED_DEPENDENCY |
| A-12 | REQ-037 | A-08,A-09,A-11 | src/reqea/core/watch.py; src/reqea/core/discovery.py; tests/a/** | 로컬 opt-in ON/OFF→안정 fingerprint→변경분만 같은 엔진 재분석, stop/잠김/중복 | BLOCKED_DEPENDENCY |
| A-13 | REQ-038 | A-10,A-11 | src/reqea/core/watch.py; src/reqea/core/github_source.py; tests/a/** | GitHub 선택 ref 15분+ SHA polling→변경 감지 재검수, rate limit/backoff/offline stop | BLOCKED_DEPENDENCY |
| A-14 | REQ-039, REQ-040 | A-09,A-11,A-12,A-13 | src/reqea/core/history.py; src/reqea/core/output.py; src/reqea/gui/app.py; src/reqea/cli.py; tests/a/** | SHA/REQ 상태 diff·로컬 히스토리·UI 표시와 출력·원본 불변/보안·오류/복구 | BLOCKED_DEPENDENCY |

임계 DAG: A-08 → A-09 → A-11 → A-12 → A-14, 병렬 독립 A-10 → A-11 → A-13 → A-14. 사용자 승인 범위는 **공개 GitHub 읽기 전용 설계**뿐. 비공개 인증·토큰/권한 변경·원본 외부 전송은 BLOCKED_APPROVAL. V1.1 P2 V11-P2-01..05 전부 NOT_RUN. 기존 17 SWU의 REQ/수용·실패·SHA 보존.

## V1.1 SWU implementation evidence update — 2026-11-19 KST

- Exact code SHA `f311b36af9f3901fd4b7c938e1572da4a1a5f176` / [CI 44480697806](https://github.com/hibi89/REQ-Evidence-Auditor-A-/actions/runs/44480697806) 6/6 SUCCESS.
- **IMPLEMENTED_UNVERIFIED:** A-08 (bounded local discovery + GUI/CLI), A-09 (explicit SHA-bound canonical selection), A-10 (public GitHub pinned read-only snapshot/CLI discovery), A-11 (selected snapshot to A/B/C audit-source CLI), A-12 (explicit foreground local stable fingerprint/debounce watch API), A-13 (explicit foreground public GitHub SHA polling/backoff watch API). These are P1 code candidates, not an independent or actual public network run.
- **READY:** A-14 (REQ-039/040 history/diff, registered-project/GitHub GUI selection, Start/Stop watch UI, persisted local-only delta reports). REQ-031 partial until A-14 UI; V11-P2-01..05 NOT_RUN.
- Baseline 17 SWU candidates + 6 newly implemented candidates = 23/24 code-candidate count, official weighted implementation UNASSESSED. No fake P2 verified completion. Respect allowed_paths and retained A/B/C contract. No unapproved main/Production/credential/customer source changes.

