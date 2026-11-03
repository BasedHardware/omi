# Firmware (Omi CV1) — Agent Guide

Component guide for `omi/firmware/`. General engineering rules: root `AGENTS.md`.

## Release Workflow

First bump `CONFIG_BT_DIS_FW_REV_STR` in `omi/omi.conf`.
Releases run manually through `.github/workflows/firmware_release.yml`; omit
`publish` for build-only QA. Commands, build logic and the OTA/backend contract:
[scripts/ci/README.md](scripts/ci/README.md).

## Mute / pause persistence (issue #5054)

Pause/mute is stored in NVS under the settings key `muted` and exposed on settings
characteristic `19b10015-e8f2-537e-4f6c-d104768a1214` (feature bit
`OMI_FEATURE_CAPTURE_MUTE`, bit 10). `19b10014` / bit 9 is device-name (#13704).
The pendant is the source of truth: disconnect must not resume capture; the
pusher drops TX and offline storage while muted. Offline double-tap toggles
mute when there is no BLE connection. The app writes this characteristic on
pause/unpause and reads it on reconnect.

## Formatting

C/C++ files: `clang-format -i <files>` (the repo pre-commit hook covers this).

## Application recovery

CV1 safe-mode behavior, host/simulator commands, retained-RAM qualification and
jig fault-injection options live in [docs/safe-mode.md](docs/safe-mode.md).
