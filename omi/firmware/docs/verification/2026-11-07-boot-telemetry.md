# CV1 3.0.23 RC: SD bus and boot telemetry validation

Measured 2026-11-06 20:39:52 UTC. Repository: `BasedHardware/omi`; branch:
`fw/cv1-release-candidate`; supplied baseline: `370f9c0f3c5`.
Implementation commit: `7a7a6aaa9dde51c980c8c4e1431dbe8bf4ef30c1`. Follow-up changes are documentation only.
The commits are local and unpushed. Validation ran on the macOS host inside
admitted `omi-heavy` sessions; no GCP tier was used.

## Behavior and wire contract

SAFE initializes only `sdhc0`, its MMC child, then attempts `disk_access_init("SDMMC")`
before the secondary-slot NOR check. It feeds the watchdog between one-shot calls,
counts returned errors and continues recovery. The injected driver-hang device is
excluded. No SD ring mount or recording-sector access is added.

`19B10041` remains 25 bytes, version 1. `19B10042` becomes 96 bytes, version 2:
the original 16-byte prefix keeps its offsets, followed by an 80-byte boot record.
The added record contains boot/reset/fatal/safe-entry state, update outcome,
previous/current firmware and header versions, pending-upload indications and
saturating NOR/SD health counters. Long reads cache a snapshot per connection.
The exact offsets and persistence contract live in [gatt-map.md](../gatt-map.md).

The retained record fills the existing 64-byte reservation without changing its
address or any partition/linker configuration. Its new magic invalidates old
records; durable SAFE can still reload from the existing settings key.

## Host verification

| Command or check | Result |
| --- | --- |
| `make -C omi/firmware/tests` | Passed: production state machine, watchdog, boot telemetry codec/classification/persistence, saturation/throttling, SD/NOR seams, legacy packet, geometry, build guards and startup parser |
| `make -C omi/firmware/omi/tests run` | Passed: custody, SD card and storage harnesses; zero failures |
| `python3 omi/firmware/omi/tests/run_host_regressions.py --output <fresh-scratch-directory>` | Passed: codec, diagnostics boundary/packet tests, coherent-cache stress and EATT negative compile under UBSan |
| `clang-format --dry-run --Werror` on changed C/header files | Passed with clang-format 18.1.8; pre-commit also formatted staged firmware files |
| `make preflight` | Passed all 41 selected checks against `origin/main` at `8053ede5c6d3` |
| `git diff --check` | Passed |

## Limits and remaining target qualification

- No nRF image build, image-size/link verification, flashing or jig run was performed.
  The code uses NCS 2.9 / Zephyr 3.7-lineage application APIs. SD driver latency,
  watchdog timing and the extended retained record still need target qualification.
  A wedged SD driver falls back to the hardware watchdog; returned errors continue SAFE.
- Identity uses the DIS string plus MCUboot header semantic version, without an
  image hash. Rebuilds sharing both identities, including identical reinstallations,
  cannot be distinguished. Missing headers produce unknown when strings match.
- Pending means the existing accepted app-upload completion callback fired; it
  does not prove a secondary-slot swap/trailer was armed. No extra NOR query is added.
- Last fatal reuses the retained presence indicator; it is not a fatal reason code.
- Dirty health counters checkpoint at most every ten minutes in normal mode;
  uncheckpointed increments can be lost on reset/power loss. Backend failure can
  prevent persistence. SAFE preserves the bounded backend-bypass behavior.

## Files changed from the supplied baseline

- `omi/firmware/docs/gatt-map.md`
- `omi/firmware/docs/safe-mode.md`
- `omi/firmware/docs/verification/2026-11-07-boot-telemetry.md`
- `omi/firmware/omi/CMakeLists.txt`
- `omi/firmware/omi/sim/CMakeLists.txt`
- `omi/firmware/omi/src/boot_telemetry.c`
- `omi/firmware/omi/src/boot_telemetry.h`
- `omi/firmware/omi/src/boot_telemetry_logic.c`
- `omi/firmware/omi/src/diagnostics_packet.c`
- `omi/firmware/omi/src/lib/core/transport.c`
- `omi/firmware/omi/src/lib/evt/spi_flash.c`
- `omi/firmware/omi/src/main.c`
- `omi/firmware/omi/src/recovery_diagnostics.h`
- `omi/firmware/omi/src/safe_mode.c`
- `omi/firmware/omi/src/safe_mode.h`
- `omi/firmware/omi/src/safe_mode_devices.c`
- `omi/firmware/omi/src/sd_card.c`
- `omi/firmware/omi/tests/host/diagnostics_cache_regression.c`
- `omi/firmware/omi/tests/test_sd_card.c`
- `omi/firmware/tests/Makefile`
- `omi/firmware/tests/stubs/zephyr/dfu/mcuboot.h`
- `omi/firmware/tests/stubs/zephyr/storage/flash_map.h`
- `omi/firmware/tests/test_boot_telemetry.c`
- `omi/firmware/tests/test_rc_integration.py`
- `omi/firmware/tests/test_safe_mode.c`
- `omi/firmware/tools/cv1/ble_central/Logic.swift`
