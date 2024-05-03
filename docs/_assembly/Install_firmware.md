---
layout: default
title: Install firmware
nav_order: 3
---

# Install firmware

If you purchased an unassembled Friend device or built it yourself using our hardware guide, follow the steps below to flash the firmware:

{: .note }
Important: If you purchased an assembled device please skip this step


We have uploaded a build of the firmware in `firmware/Release`, that will always contain the most up to date build of the firmware. To use this firmware please download it and follow step 6 below. If you would like to build the firmware yourself please follow all the steps below.

1. Set up nRF Connect by following the tutorial in this video: [https://youtu.be/EAJdOqsL9m8](https://youtu.be/EAJdOqsL9m8)

2. In the nRF Connect Extension inside your VS Code, click "Open an existing application" and open the `firmware` folder from the root of this repo.

<img src="https://basedhardware.github.io/Friend/images/install_firmware_screenshot_1.png" alt="install_firmware_screenshot_1" width="100%">


3. In the application panel of the extension, click the "Add Build Configuration" icon.

   <img src="https://basedhardware.github.io/Friend/images/addbuild.png" alt="Add Build Configuration" width="200">

4. Choose the board as "xiao_ble_sense" and select the configuration as "prj.conf". Then, click "Build Configuration".

   <img src="https://basedhardware.github.io/Friend/images/build_settings.png" alt="Build Settings" width="400">

5. Once the build succeeds, you will find the `zephyr.uf2` file in the `firmware/build/zephyr` directory.

6. Double-click on the reset button of the device. The device will appear on your computer as a disk. Drag and drop the `zephyr.uf2` file into it.

   > **Note:** On a Mac, you might see an error message after dropping the file, indicating that the process did not complete. This is just a Mac-specific error; the firmware is successfully uploaded.

   <img src="https://basedhardware.github.io/Friend/images/pinout.jpg" alt="Pinout" width="300">

That's it! You have successfully installed the firmware on your device.

[Next Step: Audio Test →](https://basedhardware.github.io/Friend/assembly/audio_test/){: .btn .btn-purple }
