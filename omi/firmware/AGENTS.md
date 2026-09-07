# Firmware (Omi CV1) — Agent Guide

Component guide for `omi/firmware/`. General engineering rules: root `AGENTS.md`.

## Release Workflow

Firmware releases are manual via `.github/workflows/firmware_release.yml`:

1. Bump `CONFIG_BT_DIS_FW_REV_STR` in `omi/firmware/omi/omi.conf` first.
2. `gh workflow run firmware_release.yml -f publish=publish -f changelog="..." -f minimum_app_version_code=...` (omit `publish` for a build-only QA run).
3. The workflow builds via Docker (NCS 2.9.0 sysbuild + MCUboot), names the OTA asset `Omi_CV1_OTA_v<ver>.zip` (the "ota" substring is required), and publishes a `Omi_CV1_v<ver>` GitHub Release with the `KEY_VALUE` body that `backend/routers/firmware.py` serves.

Build logic lives in `omi/firmware/scripts/ci/`.

## Formatting

C/C++ files: `clang-format -i <files>` (the repo pre-commit hook covers this).

## Local verification

Run `bash omi/firmware/omi/tests/host/run.sh` from the repository root for the
button edge/deadline controller and SD worker queue/wait contract tests. They
compile production code against a controllable host kernel seam with ASan and
UBSan, requiring a C compiler; the existing checks manifest runs them locally
and in CI. This verifies timing, idle scheduling, and queue wakeup behavior,
not Zephyr integration or physical battery consumption.

The button retains GPIO edge timestamps while the system workqueue is busy,
uses 40 ms debounce, and schedules only active gesture deadlines (300 ms tap,
600 ms release-to-release double window, 3 s hold). A single tap is decided at
300 ms after press unless a second press is underway; release follows after
40 ms. An idle released button has no timer. SD request producers notify a
shared semaphore after publication; the worker checks the connect-flush flag,
priority queue, inactivity flush deadline, then normal writes. Keep all queue
puts routed through `enqueue_sd_request` so neither queue can strand an idle
worker. Power-off write draining and remount sequencing remain owned by
`sd_card.c`.

Use the NCS 2.9.0 sysbuild lane above for target compilation. Hardware validation
must separately measure idle/AAD-sleep current and exercise button gestures,
recording/sync, and SD sleep/wake with buffered audio before release.
