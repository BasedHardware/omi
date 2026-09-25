# Local test results

Run on 2026-09-25 with **Flutter 3.44.5 / Dart 3.12.2** (the version pinned in `.github/workflows/mobile-app-checks.yml`),
against BasedHardware/omi `main` at `771fe017`.

| Check | Result |
|---|---|
| `flutter analyze` — components in a standalone package | No issues |
| `flutter test flutter/test/` — 7 widget tests (ring logo: sizes, animation on/off, Reduce Motion, semantics; controls: Pause/End widths ≥ 44 pt, Resume, no-pause devices) | All passed |
| Components copied into `app/lib/ui/components/` and analyzed with the app's own `analysis_options.yaml` | No issues |
| `.github/scripts/check_mobile_ux_contract.py --report` on both files (INV-UI-3) | Clean |

Not done here: running the full app on an iPhone / Android device, and the app's visual-audit tool. Do those per
screen PR (see `START_HERE.md` rule 6).
