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
  - [x] Testing new modules in the omi device (5/6)
    - [x] Mic
    - [x] BLE
    - [x] Buttons
    - [x] LEDs
    - [ ] Wi-Fi, partially
    - [x] Motors
  - [x] Add support for MCUBoot (2/3)
    - [x] Add basic MCUBoot
    - [x] Test with the OMI app (iOS/Android)
    - [ ] Test with an on-battery device (without charger)
  - [x] Initialize project, basic main loop with tests and devkit firmware as libs
  - [x] Streaming and transcribing (3/4)
    - [x] Mic
    - [x] BLE
    - [x] Encoding (OPUS) and transmitting
    - [x] Fix the audio byte loss issue - currently about 30% https://github.com/BasedHardware/omi/pull/2217#issuecomment-2815077148 
      - [x] android, fixed by increasing the BLE connnection interval (7ms) - but tbh i don't think this is a good solution since our devkit work fine without tunning the connection interval. 100 rps, 50 bytes each is not a big deal! https://github.com/BasedHardware/omi/pull/2248#issuecomment-2820156590 
      - [x] iOS, they doesn't allow increasing the connnection interval(CI). the feasible CI on iOS is about 15ms.
  - [x] LEDs (3/4)
    - [x] Charging
    - [x] BLE connected
    - [x] BLE disconnected
    - [ ] Fix the issue: The led during charging + device off ~ green only, does not provide correct feedback. charging still works.
  - [x] Buttons (2/3)
    - [x] Turn the device on/off(entering the deepsleep mode)
    - [x] Long press to chat with omi
    - [ ] Test the deepsleep mode's battery draining.
  - [ ] SD Card
    - [ ] Store files
    - [ ] Transfer via BLE
    - [ ] Transfer via Wi-Fi
  - [x] Haptic (2/3)
    - [x] Haptic on turning on/off
    - [x] Long press to chat with omi
    - [ ] Need to recheck the mass production version, since the current motoris not good https://github.com/BasedHardware/omi/pull/2281#issuecomment-2841105447
  - [x] Battery (1/2)
    - [x] Percentage feedbacks via BLE
    - [ ] Fix in-accurated battery level, especially on charging
  - [x] Charger
  - [ ] Update the OMI devkit firmware dependencies to be compatible with NCS 2.9.0
