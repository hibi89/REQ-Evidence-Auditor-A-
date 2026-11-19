# REQ Evidence Auditor V1.1 — 로컬 자동탐색 · GitHub 직접조회 · 변경 자동 재검수

**승인:** 사용자 2026-11-19 KST “그렇게 반영해놔라 최종설계도”. **정본:** docs/FINAL_BLUEPRINT.md §11 및 본 확장 문서. **상태:** P0 설계 승인, 신규 기능 P1 미구현/검증 NOT_RUN. **저장소:** hibi89/REQ-Evidence-Auditor-A- / integration/reqea-p1-20261118.

## 0. 변경 경계와 버전 전략

- 기존 V1.0 REQ-001..030, A/B/C 소유 SWU 17개, 실제 코드 및 frozen reqea.v1 JSON 계약은 수정·축소·재해석하지 않는다.
- 본 문서 신규 REQ-031..040, SWU A-08..A-14(7개)는 **별도의 추가 구현 범위**다. V1.0의 30-REQ 골든 오라클은 기존 docs/FINAL_BLUEPRINT.md를 그대로 파싱한다. 신규 REQ를 기존 문서의 REQ 표 안에 섞어 통과한 CI를 깨지 않는다.
- V1.0 기존 P1 17/17 완료 후보, 신규 P1 0/7 → 통합 후보 17/24 SWU(진행률 퍼센트 임의 산출 금지); 원래 30 REQ 후보 매핑 + 신규 10개 미구현. 공식 가중 구현/검증완료율 UNASSESSED. 기존 P2 5/9 SCOPED_PASS, 3 PARTIAL, 1 NOT_RUN은 V1.0만의 증거이며 V1.1에 전용 금지.

## 1. 제품 최종 사용자 흐름

1. GUI 또는 CLI에서 **① PC 폴더 ② GitHub 저장소 ③ 저장된 프로젝트** 중 하나를 선택. 기본값은 PC. 폴더 접근은 사용자가 선택한 루트만, GitHub 네트워크 접근은 사용자가 URL과 ref를 입력하고 실행할 때만 허용한다.
2. **정본 자동 발견:** 루트 내 AGENTS/REQUIREMENTS/README의 명시적 링크, docs/FINAL_BLUEPRINT.md 및 최종설계로 명시된 문서 후보를 제한 탐색. 상대경로·근거·출처·SHA/미확인·충돌 이유를 보여준다. 중복/불명확/링크 오류일 때 임의로 최신 날짜 문서를 정본 확정하지 않고 사용자 선택 전 STOP.
3. **읽기 전용 검수:** 선택한 정본과 같은 로컬/고정 원격 스냅샷의 코드에 기존 reqea.v1 엔진을 적용한다. audit.json / report.html / manifest.json은 종전 안전 계약을 그대로 따른다. 근거 발견은 CODE_CANDIDATE이지 자동 VERIFIED가 아니다.
4. **변경 감시:** 사용자가 등록 프로젝트에서 명시적으로 [감시 켜기]를 누른 경우만 앱 실행 중 변경 탐지. 안정된 새 지문/commit SHA가 있고 정본이 동일할 때만 재검수, 이전/현재 후보 판정 차이와 오류를 표시. [일시정지][감시 종료][기록 열기] 제공. 기본 OFF, 종료 시 중단. 상시 클라우드/백그라운드 서비스 자동 생성 금지.

## 2. 추가 요구사항 10개 (P1 모두 NOT_STARTED)

| ID | 수용조건 (정상 및 핵심 오류 경로) | owner |
|---|---|---|
| REQ-031 | local/github/registered 선택 GUI+CLI; 잘못된 모드·값 거절; 원격 및 감시 기본 OFF | A |
| REQ-032 | 사용자 선택 로컬 루트 내부에서만 bounded 설계/REQ 후보 탐색; symlink/junction/숨김 민감파일·비밀·root 탈출 거절 | A |
| REQ-033 | AGENTS/README 참조와 공식 경로를 후보·근거로 표시; 복수/모호/중복 REQ·SHA 충돌은 사용자 확정 전 AMBIGUOUS/STOP | A |
| REQ-034 | https://github.com/OWNER/REPO URL과 **별도 branch/tag/SHA** 필드 검증; 토큰 URL·SSH·IP/localhost·SSRF·redirect·임의 호스트 차단 | A |
| REQ-035 | 승인된 공개 저장소만 read-only HTTPS 조회; 선택한 ref를 exact commit SHA로 pin, 임시 격리 스냅샷의 파일수·깊이·바이트·시간·요청량 제한 및 unsafe archive/link 거절 | A |
| REQ-036 | 원격 SHA/파일 blob/tree·스냅샷 출처 검증 실패, ref 이동, 다른 시점 혼합 시 UNVERIFIED/UNASSESSED; 기존 reqea.v1 audit를 거짓 인증하지 않음 | A |
| REQ-037 | opt-in 로컬 변경 감시, 파일지문·디바운스·최소 주기, 이동/삭제/잠김/재시작·동시쓰기 실패 안전 분기, 동일 내용 재실행 방지 | A |
| REQ-038 | opt-in GitHub 지정 repo/ref만 15분 이상 간격 SHA 폴링, 새 커밋에만 분석; 403/429·오프라인·삭제·한도 응답 backoff/stop | A |
| REQ-039 | 두 고정 스냅샷의 REQ별 candidate 상태·범위·근거 diff 및 로컬 히스토리, 중복/원본 불변; 상태 차이를 기능 PASS나 구현완료율로 자동 승격 금지 | A |
| REQ-040 | 소스/비밀/고객파일 본문·토큰 외부 전송 0, root 외 입력 접근 0, 출력만 승인 폴더, 자동 삭제·기존 백업 파괴/원격 쓰기·권한 변경 0 | A |

## 3. 정본 탐색 세부 규칙

- 명시적 사용자 파일이 있으면 우선 사용. 없으면 AGENTS·REQUIREMENTS의 명시적 문서 링크, docs/FINAL_BLUEPRINT.md, README 참조, 최종설계류 파일명 순서로 **검색 후보 제시**. 검색 순서는 지시 권한이 아니다. 후보 2개 이상 충돌, 상대경로 탈출, REQ-ID 중복/부재, 접근 실패 시 분석/감시 시작 금지.
- 로컬 루트는 선택한 단일 프로젝트로 제한하며 드라이브 전체 자동 검색 없음. 비밀·숨김·.git/.env/SSH/credentials/venv/node_modules 및 symlink/hardlink/reparse 제외. 깊이·개수·크기·총 바이트 제한과 UTF-8/한글 긴 경로 오류 표시.
- 명세가 변경되거나 ref가 달라졌다면 이전 정본을 묵시적으로 교체하지 않고 사람 확인을 요구. 문서 본문에 포함된 외부 링크/명령을 시스템 지시로 실행하거나 따라가지 않는다.

## 4. GitHub 읽기 전용 원격 어댑터

- 공개 GitHub HTTPS만 V1.1 초기 범위. 사용자가 URL과 ref를 명시 선택하고 분석 버튼을 눌러야 요청. private 저장소·OAuth·GitHub App 설치·토큰 관리·권한/Secrets 변경은 추가 승인과 별도 안전 설계 전 **BLOCKED_APPROVAL**.
- 브랜치에 slash가 있어도 URL /tree/... 문자열을 임의로 파싱하지 않고 ref를 별도 입력받는다. 비워두면 응답에서 실제 기본 브랜치를 확인한다. 정확한 40-hex commit을 받으면 해당 SHA로 pin하고 파일은 고정 snapshot에만 적재.
- GitHub HTTPS API/다운로드 응답 호스트 allowlist, TLS, safe redirect, 파일/응답 byte cap, timeout, recursive depth cap, 요청수 cap, 403/404/429/RateLimit 처리. zip-slip, symlink, submodule, LFS hook, 비정상 경로, 중복/대소문자 충돌 등 거절. 사용자가 제공한 소스 내부 script/hooks/package install 등을 **실행하지 않는다**.
- 외부 공개 코드 다운로드는 사용자 승인 범위 내 독해 전용이며 사용자 PC 로컬 원본을 외부로 보내는 동작은 없다. 토큰/URL 비밀/절대 경로/소스 본문은 결과물이나 GitHub artifact로 게시하지 않는다.
- GitHub에서 조회한 commit SHA와 로컬 스냅샷 파일의 완전한 Git blob/tree 무결성이 검증되지 않으면 표시용 upstream SHA만 기록하고 기존 reqea.v1의 source_sha는 **UNVERIFIED**로 유지; false VERIFIED 금지. v1 JSON 변경 없이 확장 전용 출처 메타(예: provenance.json)를 승인 로컬 폴더에만 기록할 수 있다. 새 계약 필드가 필요하면 독립 CONTRACT_CHANGE_REQUEST/버전업 선행.

## 5. 감시·차이 분석 동작

- 로컬 변경은 허용 파일의 안전한 상대경로+내용 SHA256 지문(스캔 범위 포함)으로 확인. 디바운스(기본 5초) 후 최소 30초 이상의 주기에서 안정 스냅샷만 분석. 동일 fingerprint·작업 중복은 skip. 잠김·rename/삭제·symlink·한도 초과 시 STOP/경고 및 기존 리포트 보존.
- GitHub 감시는 사용자가 선택한 owner/repo/ref만 검사; 기본 주기 **15분 이상**, ETag/commit SHA 동등하면 작업 0, 403/429·secondary limit 또는 Retry-After 수신 시 백오프, offline·인증 필요·ref 삭제면 상태 명시 후 중지. 다른 저장소/브랜치를 임의 발견·전수 감시하지 않는다.
- 감시 중 정본이 달라지거나 선택/해시 근거가 불충분하면 REVIEW_REQUIRED로 일시정지. 앱 종료 즉시 감시 종료. OS 서비스/작업 스케줄러/Actions 예약/이메일·모바일 알림은 자동 생성하지 않음.
- 이전/새 report의 REQ별 CODE_CANDIDATE/GAP_CANDIDATE/REVIEW_REQUIRED/UNASSESSED 변경 + 출처 commit/fingerprint + scan 범위·오류 표시. 임의 100%·PASS/VERIFIED 금지. 보고서 기록은 승인된 프로젝트 외부 결과 폴더의 scan-ID별 안전 저장, 덮어쓰기/동시쓰기 보호·고유 SHA, 자동 삭제 금지.

## 6. 호출자→피호출자 구조 / 기존 A·B·C 계약 보존

~~~text
GUI/CLI → A source_mode + registry → A local_discovery | A github_readonly
  → A canonical_selector [AMBIGUOUS -> STOP]
  → A safe local snapshot / remote pinned snapshot
  → V1 A build_audit → B build_code_index → C evaluate/render_html
  → A existing safe output + A extension provenance / compare_history

Watch ON → A local_fingerprint | A github_ref_poll
  → stable approved snapshot → same V1 engine
  → A compare reports → UI + local-only history
~~~

- A 신규 코드 예상: src/reqea/core/discovery.py, selector.py, github_source.py, snapshot.py, watch.py, history.py; src/reqea/gui/app.py; src/reqea/cli.py; tests/a/**. B/C 모듈 구조·계약 무변경. UI '대시보드만' 만들지 않고 입력→정본 선택→실제 분석 결과 경로를 수직 연결.
- 새 CLI 경로/하위 명령 이름은 P1에서 구현·안전 검사로 고정. 기존 python -m reqea.cli audit --repo ... --requirements ... --out ... 를 호환 유지.

## 7. V1.1 고유 검증 (V1.0 P2와 별개, 현재 모두 NOT_RUN)

| Gate | 검증범위 | 상태 |
|---|---|---|
| V11-P2-01 | 로컬 후보 탐색/중복/비밀 파일/경로 공격/한글·긴 경로/정본 충돌 | NOT_RUN |
| V11-P2-02 | 공개 GitHub URL 공격·SSRF·redirect·SHA pin·검증된 blob/다운로드 실패/rate limit/원본불변 | NOT_RUN |
| V11-P2-03 | 로컬/원격 변경 감지·중복 방지·stop·백오프·경합·복구 | NOT_RUN |
| V11-P2-04 | REQ diff와 히스토리·출처·reqea.v1 호환·비밀/고객 원본 미유출 | NOT_RUN |
| V11-P2-05 | Windows 11 실제 GUI/EXE 및 독립 Codex 보안·Astra UX 감사/High 인수 | NOT_RUN |

**진행 순서:** docs/SWU_DAG.md의 신규 A-08..A-14 DAG. P1 최초 READY A-08(로컬 탐색), A-10(GitHub 허용 URL/안전 수집). A-09 정본선택, A-11 provenance 접합, A-12/13 감시, A-14 UI/CLI diff·출력 수직 통합. 무료/로컬·읽기 전용 기본, 기존 기능 축소·main merge·Production·출시·고객 데이터 외부 전송·권한 변경은 별도 사용자 GO.
