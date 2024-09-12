---
layout: default
title: Flashing FRIEND Firmware
nav_order: 3
---

# Flashing FRIEND Firmware

{: .note }
This guide will walk you through the process of flashing the latest firmware onto your FRIEND device. 

## Downloading the Firmware

1. Go to the [FRIEND GitHub repository](https://github.com/BasedHardware/Omi/releases) and navigate to the "Releases" section.
2. Find the latest firmware release and download the corresponding `.uf2` file.

## Putting FRIEND into DFU Mode

1. **Locate the DFU Button:** Find the small pin-sized button on the FRIEND device's circuit board (refer to the image below if needed).
2. **Prepare a Pin:** Use a small pin or similar thin tool that can press the tiny button.
3. **Press the DFU Button Twice:** Using the pin, quickly press the DFU button twice in succession.
4. **Check for Recognition:** After pressing the button twice, your computer should recognize a new drive.
5. **Verify the Drive Name:** Look for a drive named "/Volumes/XIAO-SENSE" on your computer. This indicates that the FRIEND device has successfully entered DFU mode.

   <img src="/images/dfu-dev-kit-reset-button.png" alt="DFU Button Location" width="300"> 
   

## Flashing the Firmware

1. Locate the `.uf2` firmware file you downloaded earlier.
2. Drag and drop the `.uf2` file onto the "XIAO-SENSE" drive.
3. The device will automatically eject itself once the flashing process is complete.

## Congratulations!

You have successfully flashed the latest firmware onto your FRIEND device. You can now proceed with [testing the audio](/assembly/audio_test/).