# REQEA A/B/C 통합·보존 실행 규칙 V1
**최종 통합 repo:** `hibi89/REQ-Evidence-Auditor-A-`. **임시 구현 repo:** B/C. **운영 main 변경/삭제 없음**.

## 브랜치 역할
- A: `design/reqea-final-blueprint-v1` P0 설계 정본, `integration/reqea-p1-20261118` 최종 P1 통합, `feature/reqea-a-core-p1-20261118` A 실제 기능 개발. P1 통합자 A.
- B: `feature/reqea-b-codegraph-p1-20261118` (main은 최초 README 기반).
- C: `feature/reqea-c-evidence-p1-20261118` (main은 최초 README 기반).
- 각 브랜치에서 product code 미구현, P2 NOT_RUN. 다른 작업자를 한 모델이 자동 병렬 실행했다고 기록 금지.

## A 통합 절차 (완료된 실제 모듈 단위)
1. A는 자기 feature 브랜치에서 A 소유 기능 코드를 구현·커밋. 분리된 integration 브랜치로만 기능 반영(정확 SHA 확인 후).
2. B/C는 자신의 기능을 실제 구현해 자기 SWU별 입력→출력 및 핵심 거부 경로에 대한 최소 syntax/smoke를 실행한다. 정확 SHA + file SHA256 목록 + status + KNOWN_GAPS를 HANDOFF에 명시한다.
3. A는 B의 `src/reqea_codegraph/**`와 `tests/b/**`를 **동일 상대 경로**로 복사한다. 그 외 `README/AGENTS/HANDOFF/STATUS/pyproject/.github`는 복사하지 않는다. C도 `src/reqea_evidence/**` + `tests/c/**`만 복사한다.
4. A 통합자는 A 통합 브랜치에서 3개 모듈 import/버전·JSON contract·source_sha·CLI 정상/핵심 실패 smoke를 확인한다. 파일 충돌 외 **API/DB/의존성/버전 불일치**를 따로 검사. 통합 SHA와 각 원본 SHA를 `docs/INTEGRATION_LOG.md`에 기록한다.
5. 수정이 필요하면 A는 기능 모듈 소유자에게 해당 SWU 재작업을 지시하거나 명시적으로 통합 커밋에서 수정하고 이유/소유권을 기록한다. 동일 파일을 여러 GPT가 동시에 쓰지 않는다.
6. P1 전체 REQ의 실코드 후보가 통합된 **정확 A SHA**가 있을 때만 `IMPLEMENTATION_100_CANDIDATE` 판정 검토. 무검증 제품 완성/검증 PASS 금지.
7. P2 Sol Max 전체 검사/수정, 독립 보안·기술 감사, Astra Max GUI/UX 검토, High 최종 인수는 별도. B/C는 소스 및 Git 이력 백업·비교·사용자 별도 삭제 GO가 있을 때까지 절대 삭제하지 않는다.

## 레포지토리 단위 병렬 실험 측정
동일 명세 기반 단독 구현 기준시간이 없다면 가속 배수 `UNMEASURED`. 기록: 시작/종료 KST, 작업자/모델(확인된 경우), 코드 유효 SWU 수, 재작업, 통합 오류, total elapsed, 사용자 지시 횟수. 제품 P1 완료시간이 최우선 목표. 작업 문서 건수는 완료 지표에서 제외.

## 이력과 사용자 승인
사용자의 사전 승인 없는 main merge·public/private 변경·권한 확대·실서비스 연동·클라우드 전송·유료 호출·레포지토리 삭제 금지. 공개 레포에는 고객 소스/비밀/라이선스 불명 제3자 코드를 복사하지 않는다.
