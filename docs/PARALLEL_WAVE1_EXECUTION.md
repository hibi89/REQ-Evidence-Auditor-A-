# REQEA — 1차 병렬 개발 시작 지시 (A 통합 정본)
**실행 기준:** A design SHA `e58e14ee4ef84dfc226d657cfe45b1d40cfb9ba9` · contract `reqea.v1` 동일 blob `b39d8307662206472f2165b4bce3c0e10e2b62b6`.
**다음 작업은 실코딩 P1**이다. 이 준비 작업에서 제품 소스 구현은 0건, 브라우저/검증은 NOT_RUN.

## A (통합 책임자 겸 코어 개발자)
- Repo: `hibi89/REQ-Evidence-Auditor-A-` / `feature/reqea-a-core-p1-20261118`, 기준 SHA `e58e14ee4ef84dfc226d657cfe45b1d40cfb9ba9`.
- 첫 SAFE READY: A-01 요구사항 MD 파서, A-02 JSON 파서, A-03 SHA/경로 안전. 구현 파일 `src/reqea/**`, `tests/a/**`.
- 이후 A-04가 B-05와 C-04에 의존하므로 **대기 중에도 독립 A READY를 계속 수행**, 구현 완료를 문서로 대체하지 않는다.
- 통합 브랜치 `integration/reqea-p1-20261118`는 위 설계에서 분기. A code branch 기능 변경은 안전한 순차 통합, B/C는 허용된 모듈/테스트 파일만 복사.

## B (독립 정적 분석)
- Repo: `hibi89/REQ-Evidence-Auditor-B-` / `feature/reqea-b-codegraph-p1-20261118`, 기준 `8f40de5cc6265917c457f279469f4e2d064d0a10`.
- 첫 READY B-01 read-only bounded safe walker → B-02 hash → B-03 Python AST → B-04 import/call 후보·JS/TS 제한 → B-05 build_code_index contract.
- `src/reqea_codegraph/**` `tests/b/**` 전용. 위험 경로/비밀파일 기본 차단. target 코드 자체 import/실행 금지.

## C (독립 근거·리포트)
- Repo: `hibi89/REQ-Evidence-Auditor-C-` / `feature/reqea-c-evidence-p1-20261118`, 기준 `b5d6b4eaabc95340cfa1ac6cdd80201bfc122773`.
- 첫 READY C-01 명시적 REQ↔소스 evidence candidate 매칭 → C-02 분류 → C-03 SHA 불일치 경고 → C-04 evaluate → C-05 HTML escaping 보고.
- `src/reqea_evidence/**` `tests/c/**` 전용. 정적 증거와 P2 PASS 혼동 금지.

## 각 웹 GPT 채팅 시작 단문
A 담당: "REQEA A `feature/reqea-a-core-p1-20261118` 최종설계/AGENTS/SWU 확인하고 A-01부터 실제 P1 코딩하라. `ㄱ`."
B 담당: "REQEA B `feature/reqea-b-codegraph-p1-20261118` A 계약 SHA 확인하고 B-01부터 실제 P1 코딩하라. `ㄱ`."
C 담당: "REQEA C `feature/reqea-c-evidence-p1-20261118` A 계약 SHA 확인하고 C-01부터 실제 P1 코딩하라. `ㄱ`."

세 명의 GPT 채팅은 사용자가 각각 실행한다. A 한 채팅이 B/C 추론을 동시에 수행했다고 주장하지 않는다. 작업자별 코드 경합이 없도록 새 SWU는 자신 소유 영역에서만 수행한다.

## A 통합자 수락 조건
1. B/C 실제 commit/파일 SHA256 및 소스 코드 확보(빈 repo나 README만 복사 금지).
2. A의 `integration` 브랜치에서 모듈 디렉터리만 복사; 코드/규격 충돌 발견 시 명시적 담당·원인·수정.
3. 정상·핵심 오류 경로 최소 syntax/smoke 필수; 전체 검증은 P2 큐.
4. 통합 SHA와 원본 B/C SHA를 `docs/INTEGRATION_LOG.md`에 기록. 해당 파일은 실제 통합 시에만 생성.
5. B/C 삭제는 전수 파일/히스토리 백업과 사용자 별도 GO 후로 보류.

**구현완성률 목표는 P1의 실제 기능 100% 후보; 17 SWU 설계만으로 공식률은 UNASSESSED.** 속도 개선은 실측 전 UNMEASURED.
