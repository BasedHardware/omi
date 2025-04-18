# OMI2 Firmware

The firmware for the omi consumer version. 

## Install

Use https://docs.omi.me/docs/developer/firmware/Compile_firmware as the reference with these specifications.

- NCS: 2.9.0
- Application: omi2
- Board: omi2/nrf5340/cpuapp, you could also use the [CMakePresets.json](CMakePresets.json).

## WIP

- Status: DEV

- TODOs:
  - [x] Testing new modules in omi2 device
    - [x] Mic
    - [x] BLE
    - [x] Buttons
    - [x] Leds
    - [ ] Wifi, partialy
    - [ ] Motors
  - [x] Add support MCUBoot
    - [x] Add the basic MCUBoot
    - [ ] Testing with the omi app (iOS/Android)
  - [ ] Init project, basic main loop with tests and the devkit firwmare as libs
  - [x] Streaming and transcripting
    - [x] Mic
    - [x] BLE
    - [x] Encoding(OPUS) and Transmiting
    - [ ] Fix the audio byte loss issue, about 30%
  - [ ] Leds
  - [ ] Buttons
  - [ ] SD Card
    - [ ] Storing files
    - [ ] Transfering via BLE
    - [ ] Transfering via Wifi
  - [ ] Haptic
  - [ ] Battery
  - [ ] Charger
  - [ ] Update the omi devkit firmware deps to compatible with new NCS 2.9.0

