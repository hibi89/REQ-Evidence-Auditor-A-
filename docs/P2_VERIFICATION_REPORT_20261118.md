# REQEA P2 verification evidence — 2026-11-18 KST

## Scope and immutable evidence
- Repo: `hibi89/REQ-Evidence-Auditor-A-`, integration branch `integration/reqea-p1-20261118` (never main).
- **Exact P2 source/workflow SHA tested:** `d6f3c29bde20ad5f121d58e7c26bf2ec1e148bcd`.
- **GitHub Actions run:** https://github.com/hibi89/REQ-Evidence-Auditor-A-/actions/runs/44258446968 — **SUCCESS**; 5/5 GitHub Actions jobs passed.
- Jobs: Linux `134645682544`, Windows `134645682069`, read-only checkout `134645923563`, Bandit security `134645923616`, Windows EXE+Tk `134645923568`.
- All tests use synthetic inputs or this already-public A integration checkout. No customer source/secret/external artifact upload, no main, Production, publishing, release, or privileges changed.
- Frozen contract `reqea.v1`; 17/17 planned SWUs remain P1 `IMPLEMENTED_UNVERIFIED` candidates, 30/30 planned REQ mapped. **Official weighted implementation: UNASSESSED; official acceptance/verification rate: UNASSESSED**; do not infer verification from source SWU counts.

## Executed exact-SHA checks
- Python 3.11 compileall `src tests` **PASS** on `ubuntu-24.04` and `windows-2025` (Windows Server CI runner, **not Windows 11 user machine**).
- Per-OS B tests **4/4 PASS**, C tests **17/17 PASS**, integrated A+B+C tests **3/3 PASS**, dedicated P2 tests **12/12 Windows PASS**, **11 PASS / 1 Windows-only SKIP Linux**. Aggregate test invocations: Windows **36/36 PASS**; Linux **35 PASS, 1 SKIP**.
- Installable wheel `req-evidence-auditor` **PASS** on Linux and Windows.
- Synthetic oracle: 30 REQ found, 20 explicit static file candidates + 10 missing explicit references classified as GAP_CANDIDATE; **no VERIFIED**; fixed blueprint itself parses 30 REQ rows with acceptance criteria.
- Static negative checks: duplicate REQ/JSON keys, missing refs, source/requirements symlinks, Windows junction outputs, scan truncation, read-only file SHA unaffected, confidential literal not reproduced in JSON/HTML, HTML CSP/escape, no-overwrite and source-tree output refusal.
- Windows onefile **unsigned** `reqea-cli.exe` and `reqea-gui.exe` built locally on GitHub Windows runner **PASS**; CLI EXE `--help` and synthetic Unicode-path full audit JSON/HTML/manifest **PASS**. GUI Tk window/event-loop/callback on **Windows Server CI** with synthetic input, auto-generated JSON/HTML **PASS**. No screenshot/manual Windows 11 UI/UX/EXE install or signing acceptance.
- Read-only A GitHub Actions checkout: scanned existing public `docs/FINAL_BLUEPRINT.md` with all 30 REQ **PASS**; zero checkout mutations, output only in runner temp, no upload **PASS**. Real manual `workflow_dispatch` event of `reqea-audit.yml` is **NOT_RUN**.
- Bandit 1.8.6 `python -m bandit -q -r src -ll` medium/high static issues: **exit 0 / PASS**. This is an automated scan, **not** exhaustive threat modeling or independent Codex security audit.

## P2 category-by-category acceptance separation
| Gate | This-session evidence | Gate status |
|---|---|---|
| P2-01 candidate precision | 30-row blueprint, 20/10 synthetic oracle, negative REQ match cases | PARTIAL_PASS; independent gold set/coverage NOT_RUN |
| P2-02 file/secret safety | symlink, junction, secret leak, no-clobber, source unchanged | PARTIAL_PASS; full Windows UNC/hardlink/permission/race matrix NOT_RUN |
| P2-03 CLI, JSON, OS | Linux+Windows Python+wheel+CLI errors, exact SHA | PASS for executed matrix; unsupported OS permutations NOT_RUN |
| P2-04 Windows GUI/EXE | Windows Server CI EXE builds, CLI binary, headless Tk callbacks | PARTIAL_PASS; Windows 11 real GUI/screenshot/UX/long path/endurance NOT_RUN |
| P2-05 static accuracy | Python AST, JS/TS conservative scan, SHA/truncation unit tests | PARTIAL_PASS; expansive independent false-positive corpus NOT_RUN |
| P2-06 HTML/privacy | synthetic XSS/CSP/criterion omission, secret literal absent | PARTIAL_PASS; real browser UI/security regression NOT_RUN |
| P2-07 Actions | exact checkout read-only audit zero mutation and minimum declared contents:read | PARTIAL_PASS; real manual workflow_dispatch NOT_RUN |
| P2-08 full tests/security | 5/5 CI jobs, cross-platform synthetic tests, wheel, Bandit | PARTIAL_PASS; independent Codex review, adversarial recovery/race/security audit NOT_RUN |
| P2-09 UI/final signoff | None | NOT_RUN; Astra independent UX and High final acceptance pending |

P2 source fixes included Windows symlink-path alias false rejection, Windows `DirEntry.stat()` 0/0 device/inode corrected via `os.lstat` with open-file identity retained, Windows CRLF test fixture corrected, and Windows junction/reparse ancestors rejected for local input/output. No P2 scope reductions.

## Outstanding governance / release
- Independent **Codex Sol Max** technical/security review and defect revalidation: **NOT_RUN** (not represented as performed by the same author).
- Independent **Astra Max** UX review: **NOT_RUN**.
- Windows **11** visual/manual GUI and installed/portable EXE lifecycle, advanced TOCTOU/UNC/race/long-path tests: **NOT_RUN**.
- Optional manual `workflow_dispatch` (in `.github/workflows/reqea-audit.yml`): **NOT_RUN**; no production/public artifact uploads authorized.
- Formal High final acceptance/user commercial GO, release, registration and main merge: **HOLD**.
- P2 verification completion remains **PARTIAL / official UNASSESSED**, not 100%; no approved weighted denominator or independent acceptance signoffs. Product P1 count remains 17/17 code candidates, not independently VERIFIED.
