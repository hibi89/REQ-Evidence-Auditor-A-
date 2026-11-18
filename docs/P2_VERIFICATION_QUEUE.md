# P2 검증 큐 — P1 완료 후보 이후 실행
**현재 (2026-11-18 KST):** P2 자체 합성·Linux/Windows CI 검증 일부 `PASS/PARTIAL_PASS` (Run 44258446968); 독립 Codex/Astra·Windows 11 실환경·실제 workflow_dispatch는 `NOT_RUN`. 공식 가중 검증완료율 `UNASSESSED`. 상세 증거: [P2 verification report](P2_VERIFICATION_REPORT_20261118.md).
| ID | 관련 REQ | 테스트 목표 | 위험 | 증거 조건 |
|---|---|---|---|---|
| P2-01 | 003-005,019-024 | 합성 REQ 30개/누락 10개/오탐·부분 구현 독립 정답셋 | 오판정 | fixture SHA, 기대/실제 차이 |
| P2-02 | 006,011-013,017,028 | symlink, 경로 이탈, hardlink, env, 비밀 문자열, 파일 권한, UNC | 원본/비밀 | 파일 변경 0, 리포트 유출 0 |
| P2-03 | 002,007,018,024,030 | CLI 전체 인자/예외/JSON 계약/멀티 OS | 통합 | Windows+Linux 빌드/테스트 |
| P2-04 | 001,008,010 | GUI Windows 11/EXE/한글·장기경로/중단/재실행 | 배포 | 실 Windows 화면·로그 |
| P2-05 | 014-016,020-023 | Python AST, JS/TS 제한, 다른 SHA, truncated scan | 정확성 | false PASS 0, Unknown 경로 명확 |
| P2-06 | 025-028 | HTML XSS/JS 문자열/절대경로/리포트 개인정보 | 보안 | 로컬 무스크립트 및 escape |
| P2-07 | 009,029 | GitHub Actions workflow_dispatch, 최소권한, 무고객 데이터 artifact | 공급망 | 승인 checkout + job evidence |
| P2-08 | 전체 | 전체 CI, build, recovery, negative, static security, integration | 종합 | Codex Sol Max 독립 검증 PASS |
| P2-09 | 전체 | Astra Max UI/UX 독립 감사, High 전수 인수 | UI/고유 계약 | 실제 검수 수행 증거 |
기존 자동화/보안 게이트는 생략하거나 비활성화하지 않는다. P1 실제 실행에 위험이 발생하는 변화는 P2까지 무작정 미루지 말고 즉시 HOLD.
