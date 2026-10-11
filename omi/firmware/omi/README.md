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



## Software VAD qualification (#7206)

`CONFIG_OMI_ENABLE_VAD_GATE=n` intentionally stages the software gate and its
500 ms pre-roll without enabling them in the default CV1 image. Enablement is
tracked in [#7206](https://github.com/BasedHardware/omi/issues/7206); it requires
a maintainer decision after CV1 capture, power, and codec/BLE backpressure tests.
The issue should remain open until that qualification and enablement decision.
Since the software gate overwrites older quiet frames without a durable drain,
shipping enablement must also satisfy the newer
[INV-CAP-1 retention contract](../../../product/invariants/pendant-audio-retention.md).
A successful soak alone does not establish retention compliance.

Default-off does **not** mean unchanged power behavior: with hardware T5838 AAD
enabled, `aad_track_silence()` now skips mic-off sleep while BLE is connected.
This protects conversation openings but increases connected-idle power relative
to sleeping. Offline AAD remains enabled and cannot recover audio captured while
the mic was off. The connected-idle battery tradeoff needs maintainer sign-off.

Run `bash omi/firmware/omi/tests/software_vad/run_test.sh` from the repository
root. The `firmware-software-vad-tests` manifest check runs this suite in local
preflight and CI Hygiene. It executes production ring replay, wake passthrough,
and emit-failure behavior. Full-ring onset replays at most five 100 ms blocks
**including** the triggering live block, oldest first, without a duplicate live
emit. Host tests verify that bound; hardware still must establish whether the
codec and BLE queues sustain the burst, with no onset clipping or queue loss.
No host result establishes battery life, firmware build success, or CV1 soak.

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
