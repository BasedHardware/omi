# OMI Firmware

The firmware for the OMI consumer version.

## Install

Use https://docs.omi.me/docs/developer/firmware/Compile_firmware as the reference with these specifications.

Note: Open "firmware" folder in your code editor. Don't open the root omi folder (otherwise West wouldn't recognize the project and won't find your board)

- NCS: 2.9.0
- Application: omi
- Board: omi/nrf5340/cpuapp — you can also use the [CMakePresets.json](CMakePresets.json).

 <img width="463" alt="Screenshot 2025-04-20 at 12 48 04" src="https://github.com/user-attachments/assets/5fc17e99-9cdd-4b2a-a438-fc4c6ffed498" />

 <img width="986" alt="Screenshot 2025-04-20 at 12 48 49" src="https://github.com/user-attachments/assets/ccce238d-fa4b-4cbc-af7c-fc7688569b95" />



## WIP

- Status: DEV

- TODOs:
  - [x] Testing new modules in the omi device
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
