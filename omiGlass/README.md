<!-- This file is auto-generated from docs/doc/hardware/omiGlass.mdx. Do not edit manually. -->
# omiGlass - Open Source Meta Raybans with 6x of their battery

<p align="center">
  <img src="https://github.com/user-attachments/assets/848f664b-183e-4df5-8928-f16f00ff144b" width="45%" />
  <img src="https://github.com/user-attachments/assets/3fa00359-74a0-4f85-a233-f4bf12b1db7b" width="45%" />
</p>




<p align="center">
  <a href="https://x.com/kodjima33/status/1911852469329727811">
    <img src="https://img.youtube.com/vi/QvFjXgLZX7U/maxresdefault.jpg" alt="Watch the video" width="400"/>
  </a>
  <br />
  <a href="https://x.com/kodjima33/status/1911852469329727811">▶️ Watch Video</a>
</p>


## Want a Pre-built Version?

We will ship a limited number of pre-built kits. Get a Dev [kit here](https://omi.me/glass)

## Community

Join the [Based Hardware Discord](https://discord.gg/omi) for setup questions, contribution guide, and more.

## Prerequisites

Before you begin, ensure you have the following installed:

- [Ollama](https://github.com/ollama/ollama) for local AI model hosting
- [Arduino IDE](https://www.arduino.cc/en/software) for firmware upload (if building hardware)
- 3D printer for hardware components (if building your own)

## Getting Started

Follow these steps to set up omiglass:

### Hardware Components

You'll need the following components to build your own omiGlass:

- [Seeed Studio XIAO ESP32 S3 Sense](https://www.amazon.com/dp/B0C69FFVHH/ref=dp_iou_view_item?ie=UTF8&psc=1)
- x6 150mah batteries like [this](https://a.co/d/i17DjOr) or at least like [this](https://a.co/d/bbFdkic) (but you'll need to increase the size of the casing)
- 1x 250mah battery like [this](https://a.co/d/2xheiFC)
- Wires like [these](https://a.co/d/ah98wY0) and hinges
- Note: The current design does not include a switch. See contribution section for more details.

### Software Setup

1. Clone the omiglass repository and install the dependencies:

   ```bash
   git clone https://github.com/BasedHardware/omi.git
   cd omiglass
   npm install
   ```

   You can also use **yarn** to install:

   ```bash
   yarn install
   ```

2. Set up your API keys:

   - Copy the `.env.example` file to create a new `.env` file:
     ```bash
     cp .env.example .env
     ```

   - Edit the `.env` file and add your API keys:
     - Get a Groq API key from [Groq](https://console.groq.com/keys)
     - Get an OpenAI API key from [OpenAI](https://platform.openai.com/api-keys)
     - For Ollama, the default URL is already set (http://localhost:11434/api/chat)

3. Install the required Ollama model:

   ```bash
   ollama pull moondream:1.8b-v2-fp16
   ```

4. Start the application:

   ```bash
   npm start
   ```

   or with yarn:

   ```bash
   yarn start
   ```

   Note: This is an Expo project. Open the localhost link (displayed after starting) to access the web version.

### Hardware Assembly

1. 3D print the glasses mount case using the provided STL files located in the `hardware` folder.

2. Assemble the components as shown:

<p align="center">
  <img src="https://github.com/user-attachments/assets/45ef303b-0f92-43eb-bfad-1b20a86e948c" width="45%" />
  <img src="https://github.com/user-attachments/assets/3fa00359-74a0-4f85-a233-f4bf12b1db7b" width="45%" />
</p>

### Firmware Installation

1. Open the [firmware folder](https://github.com/BasedHardware/omiglass/tree/main/firmware) and open the `.ino` file in the Arduino IDE.

   - If you don't have the Arduino IDE installed, download and install it from the [official website](https://www.arduino.cc/en/software).
   - Alternatively, follow the steps in the [firmware readme](firmware/readme.md) to build using `arduino-cli`

2. Set up the Arduino IDE for the XIAO ESP32S3 board:

   - Add ESP32 board package to your Arduino IDE:
     - Navigate to File > Preferences, and fill "Additional Boards Manager URLs" with:
       `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
     - Navigate to Tools > Board > Boards Manager..., search for `esp32`, and install the latest version.
   - Select your board and port:
     - On top of the Arduino IDE, select the port (likely to be COM3 or higher).
     - Search for `xiao` in the development board on the left and select `XIAO_ESP32S3`.

3. Configure PSRAM settings:
   - Go to the "Tools" dropdown in the Arduino IDE
   - Set "PSRAM:" to "OPI PSRAM"

   ![PSRAM Settings](../docs/images/docs/hardware/images/image.png)


4. Upload the firmware to the XIAO ESP32S3 board.

## How You Can Contribute

### Software
- [ ] Connect glasses with omi app. Currently the glasses only work with web interface

### Hardware
- [ ] Redesign the legs/sides so that it would fit on bigger heads
- [x] Add a switch into design (current design has no switch, requires manual wire connection)

## License

This project is licensed under the MIT License.
