# REQ Evidence Auditor — 최종설계 V1.0 (P0 LOCKED)
**고정일:** 2026-11-18 KST · **정본:** `hibi89/REQ-Evidence-Auditor-A-` · **단계:** P0 설계 확정 / P1 미시작 / P2 잠금
**해총 정책 기준:** `f633dcf1d3c533d2b674648e4a6515d80b85f05c` (`kmong-productization` 확인 HEAD). 이 SHA는 설계 시점 기록이며 P1 매 회차 최신 원격 HEAD와 상위 정책을 다시 확인한다.
**권한:** 사용자 지시: REQ Evidence Auditor를 A/B/C 별도 저장소에서 병렬 개발하고 최종 A로 복사·통합. 기존 REQ Evidence Auditor의 제품 형태는 **Windows 로컬 EXE + CLI + 선택적 GitHub Actions 연계**로 확정. A가 최종 제품 정본/통합 담당. 유료·고객 원본 전송·main 병합·상용 GO 없음.

## 1. 제품 목적·사용 시나리오
프로젝트 최종설계의 REQ-ID/SWU와 **동일 시점·동일 SHA의 실제 소스 파일, 심볼, 호출/의존 관계, 테스트 파일, Git/검사 증거**를 추적하는 오프라인 우선 요구사항 증거 감사 도구.
- 개인 사용자: Windows에서 `REQ Evidence Auditor.exe`를 더블클릭 → **로컬 폴더 선택** → 요구사항 파일 선택 → 분석 → 누락/부분/미평가 후보 확인 → HTML/JSON 저장.
- 개발 GPT: `reqea audit --repo <local-path> --requirements <path> --out <dir>` 실행 → 고정 JSON 결과를 읽어 수정 가능한 SWU 후보 제안. 담당 인간/High가 승인된 요구사항과 실제 코드 검토 후 작업 선정.
- 해총: GitHub Actions에서 **승인된 checkout의 로컬 파일**에 CLI만 실행, 결과 artifact 업로드(민감 파일/소스 본문 제외, 공개 아티팩트 금지). **기본 GitHub API 호출·Git 원격 clone 없음**. 별도 권한·연동은 명시적 승인 후 구현.
- 크몽: 기존 `KMONG-SVC-07` 코드/프로그램 감사의 향후 고급 옵션 후보. **새 판매 SKU 생성 아님 / 미출시**.

## 2. 미구현과 증거의 엄격한 구별
이 도구는 코드 위치/함수/심볼/검사 로그가 있다는 **근거 후보**를 찾지, 실행 성공·동작 완성·보안 안전·고객 수락을 증명하지 않는다.
- 상태: `CODE_CANDIDATE`(정적 근거 발견), `GAP_CANDIDATE`(검색 범위 내 근거 부재), `REVIEW_REQUIRED`(모순/부분/계약 불일치), `UNASSESSED`(파서 미지원·안전 차단·시간 초과).
- `VERIFIED`는 사용자 승인 및 실제 P2 수용 테스트 증거를 갖춘 후 **별도 검증 원장**에서만 사용. P1 스캐너가 자동 확정하지 않는다.
- `0%`, `100%` 표시는 최종설계 가중치/명시적 분모와 실제 구현 증거 없이 금지. 초기 공식 P1/P2 모두 `UNASSESSED`. 발견된 근거 수 = 구현완료율이 아니다.
- 부정확한 자동 코드-REQ 매칭은 **제안**으로 표시, 확신 점수를 인증이나 완료 판정에 사용하지 않는다. 원인과 근거 경로를 표시한다.

## 3. 기술 스택 및 패키징
- Python 3.11, 표준 라이브러리 우선. 코어 `pathlib, json, hashlib, ast, subprocess(git read-only), html, argparse`, GUI `tkinter/ttk`.
- GUI는 Python 코어 호출만 담당(서버 불필요). Windows EXE는 P2 단계에서 PyInstaller로 로컬 패키징 및 설치/종료/한글 경로 실험. GTX1050Ti/16GB 환경, GPU/LLM 필수 아님.
- 실행 위치: local Windows / Linux GitHub-hosted runner. 공통 코어는 OS 의존성이 없어야 한다. 정책적 지침·REQ 파일과 소스는 로컬/선택한 checkout에만 존재.
- 메인 출력 `audit.json`, `report.html`, `manifest.json`(SHA/파서/경고/아티팩트 해시). PDF, 원격 웹앱, 유료 AI 및 라이브 서버는 v1 범위 밖.
- JS/TS: v1에서는 무해한 제한적 문자열/패턴/임포트 인덱스만 `CANDIDATE`, 구조·호출 정확성 미보장 시 `UNASSESSED`. Python은 `ast` 기반 구조 우선.

## 4. 고정 아키텍처 (독립 복사 가능한 세 모듈)
```text
A  src/reqea/                manifest loader + path policy + local CLI + Tk GUI + orchestrator
B  src/reqea_codegraph/      read-only source index (files/symbols/import/call candidates)
C  src/reqea_evidence/       REQ ↔ evidence candidate matching + safe HTML/JSON reporter

User local project + REQ file
        ├── A: manifest normalization & source snapshot
        ├── B: static index, diagnostics, bounded traversal
        └── C: deterministic correlation of A + B results
                ↓
           A: audit.json/report.html + optional GUI
```
- **A**: 원본 최종설계/P0, 전체 CLI/GUI/Actions 어댑터, 최종 통합. 직접 소유 파일 `src/reqea/**`, `tests/a/**`, `docs/**`.
- **B**: 코드·의존성 인덱스 단독. 소유 `src/reqea_codegraph/**`, `tests/b/**`; A의 `src/reqea/**` 수정 금지. A가 완료 후 동일 경로를 통째로 복사.
- **C**: 매칭·근거/보고서 단독. 소유 `src/reqea_evidence/**`, `tests/c/**`; A/B 원본 수정 금지. A가 완료 후 동일 경로 복사.
- B/C가 A 모듈 import를 전제로 하지 않는다. 모든 교환은 `docs/CONTRACT_V1.md`의 JSON 데이터/함수 시그니처에 한정. B↔C 직접 의존 없음.
- `pyproject.toml`과 상위 런처·공통 정책은 A 단독 관리. B/C 자기 저장소에서 로컬 테스트용 설치 스크립트를 작성하더라도 A로 해당 파일 복사 금지.

## 5. 요구사항 명세 (REQ-ID 고정; 구현 전 파괴적 범위축소 불가)
| ID | 요구사항 / 핵심 수용 조건 | Owner |
|---|---|---|
| REQ-001 | Windows GUI에서 로컬 프로젝트 폴더·REQ 파일 선택, 분석 버튼, 진행/오류 표시 | A |
| REQ-002 | CLI audit 호출, 유효/무효 입력 명확 exit code, 도움말, JSON/HTML 산출 경로 | A |
| REQ-003 | Markdown 표/제목의 유일한 REQ-ID, 제목, 설명, acceptance criteria 파싱 및 누락 경고 | A |
| REQ-004 | 구조화 JSON 요구사항 입력·형식 검사 및 유효한 REQ-ID 중복 감지 | A |
| REQ-005 | 최종설계 파일/스냅샷/기준 커밋 SHA/정확 경로 기록 및 미확인 SHA 명시 | A |
| REQ-006 | 읽기 전용 소스/REQ 접근; 사용자 프로젝트 파일 변경·생성·실행 없음 | A |
| REQ-007 | CLI에서 B/C JSON 계약을 연결, 모듈 부재/불일치 시 정직한 UNASSESSED | A |
| REQ-008 | 프로젝트별 결과 파일 폴더 생성·JSON 원자 저장·기존 결과 덮어쓰기 승인 제어 | A |
| REQ-009 | GitHub Actions에서 수동 허용 checkout의 CLI 검증 (최소 read-only permission) | A |
| REQ-010 | UTF-8/한글 경로/Windows 긴 경로와 부분 파일 권한 실패의 원인 표시 | A |
| REQ-011 | 깊이·크기·파일수 제한을 두고 허용 폴더에서만 안전한 읽기 전용 탐색 | B |
| REQ-012 | 심볼릭링크·경로 이탈·바이너리·숨김 비밀/환경 파일 기본 제외 | B |
| REQ-013 | 파일 SHA256·상대 경로·언어/확장자·파일 크기·검사 경고 기록 | B |
| REQ-014 | Python AST에서 함수/클래스/메서드/정의 위치/임포트 인덱스 | B |
| REQ-015 | Python import/call 및 상대 경로의 관계 후보를 엣지로 표현 | B |
| REQ-016 | JS/TS는 허용된 정적 패턴만 인덱싱, 정적 해석 불가를 명시 | B |
| REQ-017 | 삭제/수정/코드 import/코드 실행 없이 파일별 분석 실패를 격리 | B |
| REQ-018 | deterministic `build_code_index(root, options)` 호출 가능, 계약 JSON 출력 | B |
| REQ-019 | req_id ↔ 파일/심볼/테스트의 명시적 참조/근접 후보를 추적 | C |
| REQ-020 | 주관적인 근거 분류/검증 상태를 엄격히 분리하여 누락 과장 금지 | C |
| REQ-021 | 사전 정의된 acceptance criteria 항목별 발견/미발견/불확실 근거 목록 | C |
| REQ-022 | 같은 SHA의 검증 근거만 연결, 서로 다른 시점 근거 혼용 경고 | C |
| REQ-023 | 지원 범위 밖 요구사항을 UNASSESSED로 안전히 분류 | C |
| REQ-024 | 정렬/해시가 고정된 deterministic JSON audit finding 생성 | C |
| REQ-025 | 사용자 제공 경로/문구를 HTML escape하여 오프라인 리포트 생성 | C |
| REQ-026 | 리포트에서 source file/line, REQ-ID, 검출 이유, 불확실성, 다음 검토단계 제시 | C |
| REQ-027 | 부정/모순 증거 후보 및 부족한 소스 범위를 별도 경고로 보고 | C |
| REQ-028 | 원본 비밀키/코드 전문/개인정보를 기본 report에 출력하지 않음 | C |
| REQ-029 | P1/P2 상태·PASS/FAIL/NOT_RUN을 분리 표기하고 근거 없는 자동 PASS 차단 | A+C |
| REQ-030 | 모든 결과에서 입력 SHA/정책 버전/계약 버전/경고를 함께 제시 | A+B+C |

상기 30 REQ는 최종설계의 기능 분모이지, 현재 완료 SWU/실제 기능 구현률을 뜻하지 않는다. 수용 조건의 세부 테스트는 아래 SWU 파일과 P2 검증 계약에 고정한다.

## 6. 안전 모델 / 데이터 거버넌스
- 실행 대상 **Python/JS/TS 소스 import, eval, exec, npm install, 사용자 테스트 자동 실행 금지**. AST 파싱·텍스트 읽기만. 사용자 코드 실행은 별도 격리·동의·P2 승인 후 별개 기능.
- 루트 외부로 향하는 symlink/hardlink/UNC·숨김 민감 파일·`.git`, `.env*`, SSH 키, credentials, node_modules, venv, build, dist 등 기본 제외. 리포트에는 키 값·파일 전문을 기록하지 않는다.
- 요구사항과 코드가 서로 다른 commit인 경우 교차 시점 증거를 VERIFIED로 사용하지 않는다. 아카이브 추적 시 baseline_sha, scan_sha, scan_time, tool_version, limit warnings, test provenance를 남긴다.
- 한 번에 읽을 파일 수/최대 바이트/총 바이트/탐색 깊이/결과 크기를 제한하고 초과 시 fail closed 또는 제한 내 `UNASSESSED`. 무한 순환·비정상 JSON 폭탄·불신 입력에 대해 bounded 처리.
- 리포트 출력은 사용자 승인 로컬 `--out` 위치에만 기록. 검사 대상 하위에 출력하는 경우 원본 변경으로 취급하므로 기본 거절. 네트워크/외부 SaaS 전송 OFF. GitHub Actions 사용은 *이미 GitHub에 게시된 승인된 저장소*에만.
- 감사 도구 자체를 코드 보안 인증기, 취약점 스캐너, 법적 적합성 인증기로 판매하지 않는다.
- 공개 GitHub에 고객 소스, 비밀, 로그, `.env`, 샘플 개인정보를 게시하지 않는다.

## 7. P1 구현 후보 / P2 검증 / 독립 인수
**P1:** A/B/C의 모든 REQ에 필요한 실제 동작 경로(입력→분석→보고), 핵심 실패 경로, GUI·CLI·Actions 소스/상태 연결을 구현하고 동일 A 통합 HEAD에 복사. 각 SWU는 caller↔callee 포함 단일 수직 기능. 필수 최소 syntax/type/smoke 및 고위험 경로 즉시 안전검사만. 전체 CI/E2E/Windows/실기기 회귀/전수 보안은 P2 별도 큐. **코드 작성/설계 문서만으로 구현률 100% 금지**.
**P2:** Sol Max 승인된 검증 담당이 범위별 CI, 설치/Windows exe, 권한/원본 불변, 악성 경로·HTML 주입·Unicode·큰 파일·절전/중단, UTF-8, 누락/오탐, 서로 다른 commit, 비유효 JSON, GUI end-to-end, 테스트 artifact·회귀·복구를 통합 수행·결함 수정·재검증. 이후 독립 기술/보안 감사, Astra Max UI/UX 독립 검수(필요한 코드/보안 관찰 병행), High 최종 인수, 사용자 출시 GO.
**측정:** P1 `완료 후보 SWU/전체 SWU`는 P1 분모용 보조량이며 정식 가중치 합의 전 임의 퍼센트 불가. P2 `PASS acceptance/총 acceptance`는 실제 실행 증거로만 계산. 신규 구조의 속도 개선 `UNMEASURED`.

## 8. 결과물 디렉터리 (A에만 최종 집합)
```text
README.md
AGENTS.md
HANDOFF.md
STATUS.md
REQUIREMENTS.md
docs/FINAL_BLUEPRINT.md
docs/CONTRACT_V1.md
docs/SWU_DAG.md
docs/INTEGRATION_RUNBOOK.md
docs/P2_VERIFICATION_QUEUE.md
src/reqea/{__init__.py,cli.py,core/,gui/}
src/reqea_codegraph/{__init__.py,...}   # B에서 그대로 복사
src/reqea_evidence/{__init__.py,...}    # C에서 그대로 복사
tests/{a/,b/,c/,integration/}
.github/workflows/reqea-audit.yml       # P1 소스, 승인 체크아웃에만 작동
```
구현 순서/전송 규칙은 `docs/SWU_DAG.md`와 `docs/INTEGRATION_RUNBOOK.md`. 계약 명세는 `docs/CONTRACT_V1.md`가 유일한 정본.

## 9. 사용자 사용성과 상용화 경계
- 사용자가 PC에서 서버를 켜거나 유료 LLM을 호출할 필요 없는 로컬 EXE 우선.
- GitHub 연결은 선택. 모바일에서는 해총에 `REQEA 최근 보고 읽고 누락 항목 알려줘`라고 할 수 있도록 GitHub Actions가 생성한 JSON/HTML 아티팩트 참조 설계; 현재 기능 구현/동작 아님.
- 연구 출처: arXiv SatisFix (`2611.16289`), Time-Consistent Hierarchical Code Graphs (`2611.17388`), GitHub Graphify 아이디어. **논문 저자 코드·제3자 도구를 그대로 복제/포함하지 않고 독립 구현**. LICENSE/종속물/상업 사용권 미확인 상태에서는 재배포 금지.
- 임시 B/C 레포는 최종 통합 후에도 **소스·Commit SHA·테스트 이력·백업 확인 전 삭제 금지**, 사용자 삭제 승인 필수. A를 최종 정본으로 유지하되 C/B 삭제 완료를 P1 완료의 조건으로 삼지 않는다.

## 10. 설계 변경 통제
REQ-ID, 소유권, 기본 출력과 보안 게이트 변경은 최종설계 개정 + 사용자 승인 필요. 각 GPT는 자기 브랜치에 구현하고 변경된 외부 계약이 필요하면 `CONTRACT_CHANGE_REQUEST`를 기록해 A의 결정·버전업 후에만 적용. 실험 중 분석기·근거 추적 능력이 제한되면 `UNASSESSED`로 처리하고 기능을 조용히 삭제하지 않는다.
