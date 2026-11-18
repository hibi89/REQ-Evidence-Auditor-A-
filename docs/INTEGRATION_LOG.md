# REQEA — A/B/C P1 선별 통합 원장 (2026-11-18 KST)
- A design: `e58e14ee4ef84dfc226d657cfe45b1d40cfb9ba9`; frozen contract blob: `b39d8307662206472f2165b4bce3c0e10e2b62b6` (`reqea.v1`).
- A feature source: `07d1ba30ee85b7b50355d69a075ab0a12e4e05fc`; A first merge: `b3ca3eeb367b85d5709b0b862a075d1c2a8d211c`.
- B source original (use exact code commit, not later documentation HEAD): `ff7741477727a42adb9a8db09019ebb1159834bf`; last file copied commit `ab6878ae6608c48d36887e985c11505a292bd5b4`.
- C source original: `7a3c760ea36f0fbb5fcfdf41aadfb5aa976c7f60`; last file copied commit `d423fea91668affd691c399918e3f16b06954501`.
- A integrated source and synthetic smoke merge `7e8b9ef88ebbc68d995b4dc470668ac7fd3bcdaf`; resulting later state-only commit HEAD should be checked in GitHub.
- Only B `src/reqea_codegraph/**`, `tests/b/**` and C `src/reqea_evidence/**`, `tests/c/**` copied, with **B 6/6 + C 7/7 SHA256 verified** from exact code commits. No common docs/AGENTS/STATUS/README/packaging copied.
- P1 synthetic GitHub Actions [Run 44252969444](https://github.com/hibi89/REQ-Evidence-Auditor-A-/actions/runs/44252969444) on PR #2 `c0092ad6f87cf219b4f927ae9f1fb075b7150043`: Python 3.11 compileall PASS, **3/3** integration unittest PASS, local CLI/HTML/JSON smoke PASS. P2 full validation/Windows/independent audits NOT_RUN.

## Preserved original file SHA256
| Owner | Path | SHA256 |
|---|---|---|
| B | `src/reqea_codegraph/__init__.py` | `27aeadd93113d6ae7530a947b1dcfa8f1f9b6b1e84cdc1361565bee191e7d9ad` |
| B | `src/reqea_codegraph/files.py` | `707bd82d468fbae7926e496f7494cf5014ac2d66f4313b0a780dbf615beb858b` |
| B | `src/reqea_codegraph/python_ast.py` | `527fc6c28346be19b3392c0947499abbc269309e4151569ab59a13684e6288b5` |
| B | `src/reqea_codegraph/relations.py` | `3fec0661c98c8cc932fb3e5956f584f77af598c2893e88d1fa3f85703e5a4957` |
| B | `src/reqea_codegraph/walk.py` | `8c3784ffc3f49b106830c7d1a98ce79e539675f07d42d1286928482e5afdd157` |
| B | `tests/b/test_codegraph.py` | `e0509f73e02902ca57e922a0494c03cb054dc3fbf3b550f1ba34ab4e0c6ff2b6` |
| C | `src/reqea_evidence/__init__.py` | `081724509d1f989bc3ab85572774c7987de54f51ada49bf97ec749843047b6dd` |
| C | `src/reqea_evidence/classify.py` | `5541fdc905212b7b531da83c742049de6099688543bea394013643c0ca2bf5c3` |
| C | `src/reqea_evidence/matcher.py` | `7981117ba0f729b9311c8f6843cfc882b8b2ef7a42d37d0d03051aef6591f186` |
| C | `src/reqea_evidence/provenance.py` | `4057e30e0ea8277c12adfcd10939e92358e57478ff27edabba65fac5a8e12981` |
| C | `src/reqea_evidence/report.py` | `0728905e84894808020235c3b515465fc43f713582f538e79887490357c9796f` |
| C | `tests/c/test_evidence.py` | `2c57e7bbfcff8f3c683038b656577ef32be89528d434da9c0326b318a8f75872` |
| C | `tests/c/test_units.py` | `3f460735258ed0e25309f3f6a8f6867a712d7d774f13cae6269fe601290badc8` |

## Timing and outstanding gates
- A began 15:08:51; B began 15:07 and ended 15:19; C began 15:08:52 and ended 15:25:43; B first A copy 15:28:57; C final A copy 15:30:36; synthetic run completed ~15:39:50; PR #2 integrated 15:41:06 KST.
- A elapsed until PR #2 merge: **32m15s**. Serial reference time absent, parallel speed multiplier `UNMEASURED`.
- **P1 code candidate 17/17**, `IMPLEMENTED_UNVERIFIED`; official weighted implementation `UNASSESSED`. P2 independent verification `NOT_RUN`, official verification `UNASSESSED`.
- Do not merge main, deploy, publish customer artifacts, change permissions, run unapproved source, or delete B/C. P2 separate prompt required.
