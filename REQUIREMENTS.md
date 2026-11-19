# REQUIREMENTS — REQ Evidence Auditor
REQ-001..REQ-030 are frozen in [docs/FINAL_BLUEPRINT.md](docs/FINAL_BLUEPRINT.md#5-요구사항-명세-req-id-고정-구현-전-파괴적-범위축소-불가).
The full input/output JSON and constraints are [docs/CONTRACT_V1.md](docs/CONTRACT_V1.md).
SWU candidates 17 (A7/B5/C5) and exact REQ mappings: [docs/SWU_DAG.md](docs/SWU_DAG.md).
P1 code candidate 17/17 SWUs (100% count only), with all REQ-001..REQ-030 mapped; official weighted P1 rate UNASSESSED. P2 NOT_RUN; official verification rate UNASSESSED. B/C worker-owned module paths must remain isolated. No owner-approved scope reduction.

## V1.1 추가 승인 요구사항 (2026-11-19 KST)

기존 **REQ-001..REQ-030 frozen reqea.v1** 불변. 신규 **REQ-031..REQ-040 (10개)**: 소스 모드·로컬 후보·정본 충돌·GitHub URL/ref 안전성·공개 저장소 읽기 전용 pinned snapshot·provenance·로컬/원격 opt-in 감시·변경 diff·비밀/원본 보존. 수용조건 전체는 docs/FINAL_BLUEPRINT_V11_SOURCE_DISCOVERY_WATCH.md §2.

기존 V1.0 P1 17/17 SWU 코드 후보/30 REQ 매핑; 신규 V1.1 P1 **0/7 A-08..A-14**(REQ 0/10 구현 후보); 통합 **17/24 SWU 후보, 30/40 REQ 범위별 매핑 후보**. 기능 완성 퍼센트와 공식 가중 구현·검증률 UNASSESSED. V1.1 코드/검증 NOT_RUN. 기존 V1.0 P2 5/9 SCOPED_PASS(55.6% 무가중 참고), 3 PARTIAL, 1 NOT_RUN. V1.1 수용 테스트 V11-P2-01..05 별도 NOT_RUN.

## 2026-11-19 — V1.1 actual P1 status at code SHA `f311b36af9f3901fd4b7c938e1572da4a1a5f176`

V1.1 newly implemented candidate SWUs **A-08,A-09,A-10,A-11,A-12,A-13 (6/7)**; A-14 READY. REQ-032..038 have code candidates; REQ-031 PARTIAL (registered/GitHub GUI selection outstanding), REQ-039/040 NOT_STARTED. V1.0 17/17 candidates preserved, integration **23/24 SWU code candidates**; official weighted implementation and verification UNASSESSED. [CI 44480697806](https://github.com/hibi89/REQ-Evidence-Auditor-A-/actions/runs/44480697806) SUCCESS 6/6 synthetic. New V11-P2-01..05 NOT_RUN; public live GitHub fetching and monitoring NOT_RUN. No verified user data, main merge or release.
## 2026-11-19 KST — V1.1 P1 후보 7/7, 전체 24/24
- 최신 코드 SHA 5ebb1ae16c032e35a5444ae13d653c36ae1f56cc, Actions #44483359171 6/6 SUCCESS(96 PASS/5 SKIP Ubuntu; 98 PASS/3 SKIP Windows Server 2025). A-14 실제 GUI·CLI registered/public GitHub 선택, opt-in 감시, bounded REQ status/evidence/criteria diff, 사용자 승인 결과 폴더의 append-only history, CLI 프로젝트 등록/조회/해제 구현. 기존 A/B/C frozen reqea.v1 보존.
- REQ-001..040 P1 기능 코드 후보 매핑. 공식 가중 구현률/검증률 UNASSESSED. V11-P2-01..05 전체 NOT_RUN; 기존 V1.0 P2 5/9 SCOPED_PASS/3 PARTIAL/1 NOT_RUN. 실제 공개 GitHub 네트워크, Windows11 실GUI, 실제 workflow_dispatch 및 독립 Codex/Astra 감사 미실행. 배포·main·Production·권한/Secrets·고객자료 업로드 HOLD.
