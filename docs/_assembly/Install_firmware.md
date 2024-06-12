---
layout: default
title: Install firmware
nav_order: 3
---

# Install firmware

If you purchased an unassembled Friend device or built it yourself using our hardware guide, follow the steps below to flash the firmware:

{: .note }
Important: If you purchased an assembled device please skip this step


SKIP and INSTALL PRE-BUILT FIRMWARE: Looking into the git repository, in the [firmware](https://github.com/BasedHardware/Friend/tree/main/firmware) folder, under the desired version, you'll find pre-built firmwares in the Release folder. For now, the safe bet is to use the pcm firmware, but the goal is to implement opus firmware (please help if you can). To use this firmware, simply download it and skip to step 6. If you would like to build the firmware yourself please follow all the steps below.

1. Set up nRF Connect by following the tutorial in this video: [https://youtu.be/EAJdOqsL9m8](https://youtu.be/EAJdOqsL9m8)

2. In the nRF Connect Extension inside your VS Code, click "Open an existing application" and open the `firmware` folder from the root of this repo.

<img src="/images/install_firmware_screenshot_1.png" alt="install_firmware_screenshot_1" width="100%">


3. In the application panel of the extension, click the "Add Build Configuration" icon.

   <img src="/images/addbuild.png" alt="Add Build Configuration" width="200">

4. Choose the board as "xiao_ble_sense" and select the configuration as "prj.conf". Then, click "Build Configuration".

   <img src="/images/build_settings.png" alt="Build Settings" width="400">

5. Once the build succeeds, you will find the `zephyr.uf2` file in the `firmware/build/zephyr` directory.

6. Double-click on the reset button of the device. The device will appear on your computer as a disk. Drag and drop the `zephyr.uf2` file into it.

   > **Note:** On a Mac, you might see an error message after dropping the file, indicating that the process did not complete. This is just a Mac-specific error; the firmware is successfully uploaded.

   <img src="/images/pinout.jpg" alt="Pinout" width="300">

That's it! You have successfully installed the firmware on your device.

[Next Step: Audio Test →](/assembly/audio_test/){: .btn .btn-purple }
