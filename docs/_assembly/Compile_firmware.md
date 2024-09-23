---
layout: default
title: Compiling the device firmware
nav_order: 3
---

# Compile firmware

{: .note }
Important: If you purchased an assembled device please skip this step

If you purchased an unassembled Friend device or built it yourself using our hardware guide, follow the steps below to flash the firmware:

### Want to install a pre-built firmware? Navigate [here](https://docs.omi.me/get_started/Flash_device/) 


## Build your own firmware:

1. Set up nRF Connect by following the tutorial in this video: [https://youtu.be/EAJdOqsL9m8](https://youtu.be/EAJdOqsL9m8)

2. In the nRF Connect Extension inside your VS Code, click "Open an existing application" and open the `firmware` folder from the root of this repo.

   <img src="/images/install_firmware_screenshot_1.png" alt="install_firmware_screenshot_1" width="100%">


3. In the application panel of the extension, click the "Add Build Configuration" icon.

   <img src="/images/addbuild.png" alt="Add Build Configuration" width="200">

4. Choose the board as "xiao_ble_sense" and select the configuration as "prj.conf". Then, click "Build Configuration".

   <img src="/images/build_settings.png" alt="Build Settings" width="400">

5. Once the build succeeds, you will find the `zephyr.uf2` file in the `firmware/build/zephyr` directory.

6. Double-click on the reset button of the device(see on image below) . The device will appear on your computer as a disk. Drag and drop the `zephyr.uf2` file into it.

   > **Note:** On a Mac, you might see an error message after dropping the file, indicating that the process did not complete. This is just a Mac-specific error; the firmware is successfully uploaded.

   <img src="/images/pinout.jpg" alt="Pinout" width="300">

   If you have an assembled device, you can put a stick pin/needle into this whole and double-click 2 times


   <img src="https://github.com/BasedHardware/Omi/assets/43514161/8136f688-8eac-4967-bd95-7aaeaac324cd" alt="whole" width="300">


That's it! You have successfully installed the firmware on your device.

[Next Step: Audio Test →](/assembly/audio_test/){: .btn .btn-purple }
