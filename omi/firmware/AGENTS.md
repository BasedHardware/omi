# Firmware (Omi CV1) — Agent Guide

Component guide for `omi/firmware/`. General engineering rules: root `AGENTS.md`.

## Release Workflow

Firmware releases are manual via `.github/workflows/firmware_release.yml`:

1. Bump `CONFIG_BT_DIS_FW_REV_STR` in `omi/firmware/omi/omi.conf` first.
2. `gh workflow run firmware_release.yml -f publish=publish -f changelog="..." -f minimum_app_version_code=...` (omit `publish` for a build-only QA run).
3. The workflow builds via Docker (NCS 2.9.0 sysbuild + MCUboot), names the OTA asset `Omi_CV1_OTA_v<ver>.zip` (the "ota" substring is required), and publishes a `Omi_CV1_v<ver>` GitHub Release with the `KEY_VALUE` body that `backend/routers/firmware.py` serves.

Build logic lives in `omi/firmware/scripts/ci/`.

## Mute / pause persistence (issue #5054)

Pause/mute is stored in NVS under the settings key `muted` and exposed on settings
characteristic `19b10014-e8f2-537e-4f6c-d104768a1214` (feature bit
`OMI_FEATURE_CAPTURE_MUTE`).
The pendant is the source of truth: disconnect must not resume capture; the
pusher drops TX and offline storage while muted. Offline double-tap toggles
mute when there is no BLE connection. The app writes this characteristic on
pause/unpause and reads it on reconnect.

## Formatting

C/C++ files: `clang-format -i <files>` (the repo pre-commit hook covers this).
