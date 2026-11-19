# REQUIREMENTS — REQ Evidence Auditor
REQ-001..REQ-030 are frozen in [docs/FINAL_BLUEPRINT.md](docs/FINAL_BLUEPRINT.md#5-요구사항-명세-req-id-고정-구현-전-파괴적-범위축소-불가).
The full input/output JSON and constraints are [docs/CONTRACT_V1.md](docs/CONTRACT_V1.md).
SWU candidates 17 (A7/B5/C5) and exact REQ mappings: [docs/SWU_DAG.md](docs/SWU_DAG.md).
P1 code candidate 17/17 SWUs (100% count only), with all REQ-001..REQ-030 mapped; official weighted P1 rate UNASSESSED. P2 NOT_RUN; official verification rate UNASSESSED. B/C worker-owned module paths must remain isolated. No owner-approved scope reduction.

## V1.1 추가 승인 요구사항 (2026-11-19 KST)

기존 **REQ-001..REQ-030 frozen reqea.v1** 불변. 신규 **REQ-031..REQ-040 (10개)**: 소스 모드·로컬 후보·정본 충돌·GitHub URL/ref 안전성·공개 저장소 읽기 전용 pinned snapshot·provenance·로컬/원격 opt-in 감시·변경 diff·비밀/원본 보존. 수용조건 전체는 docs/FINAL_BLUEPRINT_V11_SOURCE_DISCOVERY_WATCH.md §2.

기존 V1.0 P1 17/17 SWU 코드 후보/30 REQ 매핑; 신규 V1.1 P1 **0/7 A-08..A-14**(REQ 0/10 구현 후보); 통합 **17/24 SWU 후보, 30/40 REQ 범위별 매핑 후보**. 기능 완성 퍼센트와 공식 가중 구현·검증률 UNASSESSED. V1.1 코드/검증 NOT_RUN. 기존 V1.0 P2 5/9 SCOPED_PASS(55.6% 무가중 참고), 3 PARTIAL, 1 NOT_RUN. V1.1 수용 테스트 V11-P2-01..05 별도 NOT_RUN.
