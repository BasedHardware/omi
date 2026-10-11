# OMI Firmware

The firmware for the OMI consumer version.

## Install

Use https://docs.omi.me/doc/developer/firmware/Compile_firmware as the reference with these specifications.

Note: Open "firmware" folder in your code editor. Don't open the root omi folder (otherwise West wouldn't recognize the project and won't find your board)

- NCS: 2.9.0
- Application: omi
- Board: omi/nrf5340/cpuapp — you can also use the [CMakePresets.json](CMakePresets.json).

 <img width="463" alt="Screenshot 2025-04-20 at 12 48 04" src="https://github.com/user-attachments/assets/5fc17e99-9cdd-4b2a-a438-fc4c6ffed498" />

 <img width="986" alt="Screenshot 2025-04-20 at 12 48 49" src="https://github.com/user-attachments/assets/ccce238d-fa4b-4cbc-af7c-fc7688569b95" />



## CV1 settings reservation (#5400)

The static partition map reserves internal flash `0xf8000`–`0x100000` for
32 KiB of NVS settings, matching `storage_partition` in the board devicetree and
`CONFIG_PM_PARTITION_SIZE_SETTINGS_STORAGE`. The app/primary-app envelope is
`0x10200`–`0xf8000` (927.5 KiB, previously 959.5 KiB); the MCUboot primary and
external secondary slots are both `0xe8000` bytes. External network staging
moves to `0xe8000`–`0x128000`, with the remaining flash starting at `0x128000`.

Run `python3 omi/firmware/omi/tests/check_partition_layout.py` from the repo root
with the backend venv (PyYAML). CI Hygiene and local preflight run the same
`firmware-settings-partition-contract` check. This is a static configuration
guard for [#5400](https://github.com/BasedHardware/omi/issues/5400), not evidence
that a current image links or can upgrade existing devices.

The historical NCS 2.9.0 sysbuild on PR #13855 head `035863dc22` placed dynamic
`littlefs_storage` in internal flash at `0xf2000`–`0xf8000`, reducing the actual
app link region further. `CONFIG_FILE_SYSTEM_LITTLEFS=y` remains enabled; this
PR preserves that setting and does not relocate littlefs. The consumer audio
storage implementation uses the raw SD-sector ring (`lib/core/storage.c`), not
littlefs; the EVT filesystem helper mounts SDMMC as EXT2. Internal littlefs is
therefore an inherited allocation, not a new audio destination. Maintainers
must confirm this placement in the **new** generated partition map/linker output
and decide whether the unused allocation should remain in a separate change.

Before release, build the merged head using NCS 2.9.0 sysbuild, inspect generated
`partitions.yml`, `zephyr.dts`, and the link map, and qualify upgrade/rollback
from the old layout. The 32 KiB app-slot reduction, external staging relocation,
and potential one-time reset of previously overlapped/corrupt settings require
explicit maintainer migration and OTA-headroom sign-off in #5400. No automatic
settings migration or fleet/hardware acceptance is claimed by this change.

## WIP

- Status: running on production, missing some enhancement.

- TODOs:
  - [x] Testing new modules in the omi device (7/9)
    - [x] Mic
    - [x] BLE
    - [x] Buttons
    - [x] LEDs
    - [ ] Wi-Fi (nRF7002 populated; not enabled in current firmware)
    - [x] Motors
    - [x] SPI NOR flash (OTA staging)
    - [ ] IMU
    - [x] Soldered SD NAND (raw-sector audio ring, no filesystem)
  - [x] Add support for MCUBoot
    - [x] Add basic MCUBoot
    - [x] Test with the OMI app (iOS/Android)
    - [x] Test with an on-battery device (without charger)
  - [x] Initialize project, basic main loop with tests and devkit firmware as libs
  - [x] Streaming and transcribing
    - [x] Mic
      - [x] Capturing audio bytes
      - [x] Activating the 2nd mic
    - [x] BLE
    - [x] Encoding (OPUS) and transmitting
    - [x] Fix the audio byte loss issue - currently about 30% https://github.com/BasedHardware/omi/pull/2217#issuecomment-2815077148
      - [x] android, fixed by increasing the BLE connection interval (7ms) - but tbh i don't think this is a good solution since our devkit work fine without tuning the connection interval. 100 rps, 50 bytes each is not a big deal! https://github.com/BasedHardware/omi/pull/2248#issuecomment-2820156590
      - [x] iOS, they doesn't allow increasing the connection interval(CI). the feasible CI on iOS is about 15ms.
  - [x] LEDs
    - [x] Charging
    - [x] BLE connected
    - [x] BLE disconnected
    - [x] Fix the issue: The led during charging + device off ~ green only, does not provide correct feedback. charging still works.
  - [x] Buttons
    - [x] Turn the device on/off(entering the deepsleep mode)
    - [x] Long press (3 s) to power off
    - [x] Test the deepsleep mode's battery draining.
  - [x] SD NAND (2/3)
    - [x] Store audio in a raw-sector ring
    - [x] Transfer via BLE
    - [ ] Transfer via Wi-Fi
  - [x] Haptic
    - [x] Haptic on turning on/off
    - [x] Long press (3 s) to power off
    - [x] Recheck the mass production version, since the current motor is not good https://github.com/BasedHardware/omi/pull/2281#issuecomment-2841105447
  - [x] Battery (1/2)
    - [x] Percentage feedbacks via BLE
    - [ ] Fix in-accurated battery level, especially on charging
  - [x] Charger
