# OMI2 Firmware

The firmware for the OMI consumer version.

## Install

Use https://docs.omi.me/docs/developer/firmware/Compile_firmware as the reference with these specifications.

- NCS: 2.9.0
- Application: omi2
- Board: omi2/nrf5340/cpuapp — you can also use the [CMakePresets.json](CMakePresets.json).

 <img width="543" alt="Screenshot 2025-04-18 at 18 11 48" src="https://github.com/user-attachments/assets/2c5a642f-af66-46d2-8a56-e3a6e28034c6" />

## WIP

- Status: DEV

- TODOs:
  - [x] Testing new modules in the omi2 device
    - [x] Mic
    - [x] BLE
    - [x] Buttons
    - [x] LEDs
    - [ ] Wi-Fi, partially
    - [ ] Motors
  - [x] Add support for MCUBoot
    - [x] Add basic MCUBoot
    - [ ] Test with the OMI app (iOS/Android)
  - [x] Initialize project, basic main loop with tests and devkit firmware as libs
  - [x] Streaming and transcribing
    - [x] Mic
    - [x] BLE
    - [x] Encoding (OPUS) and transmitting
    - [ ] Fix the audio byte loss issue — currently about 30%
  - [ ] LEDs
  - [ ] Buttons
  - [ ] SD Card
    - [ ] Store files
    - [ ] Transfer via BLE
    - [ ] Transfer via Wi-Fi
  - [ ] Haptic
  - [ ] Battery
  - [ ] Charger
  - [ ] Update the OMI devkit firmware dependencies to be compatible with NCS 2.9.0
