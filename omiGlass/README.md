<!-- This file is auto-generated from docs/doc/hardware/omiGlass.mdx. Do not edit manually. -->
<Frame>
  <img src="https://github.com/user-attachments/assets/848f664b-183e-4df5-8928-f16f00ff144b" alt="omiGlass Front View" style={{ maxWidth: '500px', margin: '0 auto' }} />
</Frame>

## Overview

omiGlass is an open-source smart glasses project that gives you AI capabilities with exceptional battery life.

<CardGroup cols={3}>
  <Card title="6x Battery Life" icon="battery-full">
    Longer lasting than Meta Ray-Bans
  </Card>
  <Card title="ESP32 S3 Sense" icon="microchip">
    Powerful XIAO microcontroller with camera
  </Card>
  <Card title="Fully Open Source" icon="code-branch">
    Hardware, firmware, and software
  </Card>
</CardGroup>

<Info>
Watch the [announcement video](https://x.com/kodjima33/status/1911852469329727811) to see omiGlass in action.
</Info>


## Prerequisites

<CardGroup cols={3}>
  <Card title="Ollama" icon="robot" href="https://github.com/ollama/ollama">
    Local AI model hosting
  </Card>
  <Card title="Arduino IDE" icon="code" href="https://www.arduino.cc/en/software">
    For firmware upload
  </Card>
  <Card title="3D Printer" icon="cube">
    For hardware components
  </Card>
</CardGroup>


## Software Setup

<Steps>
  <Step title="Clone the Repository">
    ```bash
    git clone https://github.com/BasedHardware/omi.git
    cd omi/OmiGlass
    npm install
    ```

    Or with yarn:
    ```bash
    yarn install
    ```
  </Step>
  <Step title="Configure API Keys">
    Copy the template and add your keys:

    ```bash
    cp .env.template .env
    ```

    Edit `.env` and add:
    - [Groq API key](https://console.groq.com/keys)
    - [OpenAI API key](https://platform.openai.com/api-keys)
    - Ollama URL (default: `http://localhost:11434/api/chat`)
  </Step>
  <Step title="Install Ollama Model">
    ```bash
    ollama pull moondream:1.8b-v2-fp16
    ```
  </Step>
  <Step title="Start the Application">
    ```bash
    npm start
    ```

    Or with yarn:
    ```bash
    yarn start
    ```

    <Tip>
    This is an Expo project. Open the localhost link displayed after starting to access the web version.
    </Tip>
  </Step>
</Steps>


## Firmware Installation

<Steps>
  <Step title="Open the Firmware">
    Open the [firmware folder](https://github.com/BasedHardware/omi/tree/main/omiGlass/firmware) and load the `.ino` file in Arduino IDE.

    <Tip>
    Alternatively, follow the [firmware readme](https://github.com/BasedHardware/omi/tree/main/omiGlass/firmware/readme.md) to build using `arduino-cli`.
    </Tip>
  </Step>
  <Step title="Configure Arduino IDE">
    Add the ESP32 board package:

    1. Go to **File → Preferences**
    2. Add to "Additional Boards Manager URLs":
       ```
       https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
       ```
    3. Go to **Tools → Board → Boards Manager**
    4. Search for `esp32` and install the latest version
  </Step>
  <Step title="Select Board and Port">
    1. Select port (likely COM3 or higher) at the top of Arduino IDE
    2. Search for `xiao` in the board selector
    3. Select **XIAO_ESP32S3**
  </Step>
  <Step title="Configure PSRAM">
    Go to **Tools** dropdown and set **PSRAM** to **OPI PSRAM**.

    <Frame>
      <img src="/images/docs/hardware/images/image.png" alt="PSRAM Settings" />
    </Frame>
  </Step>
  <Step title="Upload Firmware">
    Click the Upload button to flash the firmware to your XIAO ESP32S3 board.
  </Step>
</Steps>


## License

This project is licensed under the MIT License.

