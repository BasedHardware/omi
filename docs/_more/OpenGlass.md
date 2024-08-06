---
layout: default
title: Open Glass
nav_order: 3
---

# OpenGlass - Open Source Smart Glasses

Turn any glasses into hackable smart glasses with less than $25 of off-the-shelf components. Record your life, remember people you meet, identify objects, translate text, and more.

![OpenGlass](https://github.com/BasedHardware/OpenGlass/assets/43514161/2fdc9d9d-2206-455c-ba60-10dbd6fb3dfb)

## Video Demo

[![OpenGlass Demo](https://img.youtube.com/vi/DsM_-c2e1ew/0.jpg)](https://youtu.be/DsM_-c2e1ew)

## Want a Pre-built Version?

We will ship a limited number of pre-built kits. Fill out the [interest form](https://basedhardware.com/openglass) to get notified.

## Community

Join the [Based Hardware Discord](https://discord.com/invite/ZutWMTJnwA) for setup questions, contribution guide, and more.

## Getting Started

Follow these steps to set up OpenGlass:

### Hardware

1. Gather the required components:

   - [Seeed Studio XIAO ESP32 S3 Sense](https://www.amazon.com/dp/B0C69FFVHH/ref=dp_iou_view_item?ie=UTF8&psc=1)
   - [EEMB LP502030 3.7v 250mAH battery](https://www.amazon.com/EEMB-Battery-Rechargeable-Lithium-Connector/dp/B08VRZTHDL)
   - [3D printed glasses mount case](https://storage.googleapis.com/scott-misc/openglass_case.stl)

2. 3D print the glasses mount case using the provided STL file.

3. Open the [firmware folder](https://github.com/BasedHardware/openglass/tree/main/firmware) and open the `.ino` file in the Arduino IDE.

   - If you don't have the Arduino IDE installed, download and install it from the [official website](https://www.arduino.cc/en/software).
   - Alternatively, follow the steps in the [firmware readme](firmware/readme.md) to build using `arduino-cli`

4. Follow the software preparation steps to set up the Arduino IDE for the XIAO ESP32S3 board:

   - Add ESP32 board package to your Arduino IDE:
     - Navigate to File > Preferences, and fill "Additional Boards Manager URLs" with the URL: `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
     - Navigate to Tools > Board > Boards Manager..., type the keyword `esp32` in the search box, select the latest version of `esp32`, and install it.
   - Select your board and port:
     - On top of the Arduino IDE, select the port (likely to be COM3 or higher).
     - Search for `xiao` in the development board on the left and select `XIAO_ESP32S3`.

5. Before you flash go to the "Tools" drop down in the Arduino IDE and make sure you set "PSRAM:" to be "PSRAM: "OPI PSRAM"

![Like this](image.png)

6. Upload the firmware to the XIAO ESP32S3 board.

### Software

1. Clone the OpenGlass repository and install the dependencies:

   ```
   git clone https://github.com/BasedHardware/openglass.git
   cd openglass
   npm install
   ```

   You can also use **yarn** to install, by doing

   ```
   yarn install
   ```

2. Add API keys for Groq and OpenAI in the `keys.ts` file located at [https://github.com/BasedHardware/OpenGlass/blob/main/sources/keys.ts](https://github.com/BasedHardware/OpenGlass/blob/main/sources/keys.ts).

3. For Ollama, self-host the REST API from the repository at [https://github.com/ollama/ollama](https://github.com/ollama/ollama) and add the URL to the `keys.ts` file. The URL should be http://localhost:11434/api/chat
4. go to terminal and type "ollama pull moondream:1.8b-v2-fp16"

5. Start the application:

   ```
   npm start
   ```

   If using **yarn** start the application with

   ```
   yarn start
   ```

   Note: This is an Expo project. For now, open the localhost link (this will appear after completing step 5) to access the web version.

## License

This project is licensed under the MIT License.
