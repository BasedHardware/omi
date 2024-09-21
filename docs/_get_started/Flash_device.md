---
layout: default
title: Update FRIEND Firmware
nav_order: 3
---
# Video Tutorial
For a visual walkthrough of the flashing process, watch the [Updating Your FRIEND](https://github.com/BasedHardware/omi/blob/main/docs/images/updating_your_friend.mov) video.

# Flashing FRIEND Firmware`   

{: .note }
This guide will walk you through the process of flashing the latest firmware onto your FRIEND device.

## Downloading the Firmware

1. Go to the [FRIEND GitHub repository](https://github.com/BasedHardware/Omi) and navigate to the " FRIEND > firmware" section.
2. Find the latest firmware release and bootloader, then download the corresponding `.uf2` files.

Or download these files
   - **Bootloader:** [bootloader0.9.0.uf2](https://github.com/BasedHardware/omi/releases/download/v1.0.3-firmware/update-xiao_nrf52840_ble_sense_bootloader-0.9.0_nosd.uf2)
   -  **Firmware:** [firmware1.0.4.uf2](https://github.com/BasedHardware/omi/releases/download/v1.0.4-firmware/friend-xiao_nrf52840_ble_sense-1.0.4.uf2)

## Putting FRIEND into DFU Mode

1. **Locate the DFU Button:** Find the small pin-sized button on the FRIEND device's circuit board (refer to the image below if needed).
2. **Prepare a Pin:** Use a small pin or similar thin tool to press the tiny button.
3. **Press the DFU Button Twice:** Using the pin, quickly press the DFU button twice in succession.
4. **Check for Recognition:** After pressing the button twice, your computer should recognize a new drive.
5. **Verify the Drive Name:** Look for a drive named `/Volumes/XIAO-SENSE` on your computer. This indicates that the FRIEND device has successfully entered DFU mode.

   <img src="/images/dfu_dev_kit_reset_button.png" alt="DFU Button Location" width="300">

## Flashing the Firmware

1. Locate the `.uf2` files you downloaded earlier.
2. Drag and drop the bootloader `.uf2` file onto the `/Volumes/XIAO-SENSE` drive:
   - **Bootloader:** [bootloader0.9.0.uf2](https://github.com/BasedHardware/omi/releases/download/v1.0.3-firmware/update-xiao_nrf52840_ble_sense_bootloader-0.9.0_nosd.uf2)
3. The device will automatically eject itself once the bootloader flashing process is complete.
4. After the device forcibly ejects, set the FRIEND device back into DFU mode by double-tapping the reset button.
5. Drag and drop the FRIEND firmware file onto the `/Volumes/XIAO-SENSE` drive:
   - **Firmware:** [firmware1.0.4.uf2](https://github.com/BasedHardware/omi/releases/download/v1.0.4-firmware/friend-xiao_nrf52840_ble_sense-1.0.4.uf2)

## Congratulations!

You have successfully flashed the latest firmware onto your FRIEND device. You can now download the FRIEND companion app to fully utilize your device:

- **Google Play Store:** [Download the FRIEND app from Google Play](https://play.google.com/store/apps/details?id=com.friend.ios).
- **Apple App Store:** [Download the FRIEND app from the App Store](https://apps.apple.com/us/app/friend-ai-wearable/id6502156163).

Once you've installed the app, follow the in-app instructions to connect your FRIEND device and start exploring its features.

i just added this video to the repo docs/images/updating_your_friend.mov add it to this
