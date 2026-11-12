# Firmware (Omi CV1) — Agent Guide

General rules: root `AGENTS.md`.

Human on-ramp: the visual guide at `docs/doc/hardware/how-the-pendant-works.mdx`, with source in `omi/hardware/consumer/explainer/`. If you change capture routing, LED states, AAD, or storage behavior, update the matching card in `pendant-guide.src.html` and rebuild.

## Release Workflow

First bump `CONFIG_BT_DIS_FW_REV_STR` in `omi/omi.conf`.
Releases run manually through `.github/workflows/firmware_release.yml`; omit
`publish` for build-only QA. Commands, build logic and the OTA/backend contract:
[scripts/ci/README.md](scripts/ci/README.md). Follow [the CV1 release runbook](docs/cv1-release-safety.md): build-only QA first,
then promote its exact artifacts with `qa_run_id`, `qa_run_attempt` and the
bench-reported `tested_signed_sha256` from the same main SHA.
New releases start at 1%; David expands by editing the release body. Versions
3.0.90–3.0.99 require the explicit emergency-revert input.

Capture mute (`19B10015`, NVS key `muted`, feature bit 10) and its pendant-owned
semantics are specified in [docs/gatt-map.md](docs/gatt-map.md).

MCUboot build and safe SWD: [docs/cv1-bootloader.md](docs/cv1-bootloader.md).

## Formatting

C/C++ files: `clang-format -i <files>` (the repo pre-commit hook covers this).

## Application recovery

CV1 safe-mode behavior, host/simulator commands, retained-RAM qualification and
jig fault-injection options live in [docs/safe-mode.md](docs/safe-mode.md).
