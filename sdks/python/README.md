<!-- This file is auto-generated from docs/doc/developer/sdk/python.mdx. Do not edit manually. -->
# 🎧 Omi Python SDK 

A pip-installable Python SDK for connecting to **Omi wearable devices** over **Bluetooth**, decoding **Opus-encoded audio**, and transcribing it in **real time using Deepgram**.

## 📦 Installation

### Prerequisites
The Omi SDK requires the Opus audio codec library to be installed on your system:

**macOS:**
```bash
brew install opus
```

**Ubuntu/Debian:**
```bash
sudo apt-get install libopus0 libopus-dev
```

**CentOS/RHEL/Fedora:**
```bash
sudo yum install opus opus-devel  # CentOS/RHEL
sudo dnf install opus opus-devel  # Fedora
```

### Option 1: Install from PyPI (when published)
```bash
pip install omi-sdk
```

### Option 2: Install from source
```bash
git clone https://github.com/BasedHardware/omi.git
cd omi/sdks/python
pip install -e .
```

## 🚀 Quick Start

### 1. Set up your environment
```bash
# Get a free API key from https://deepgram.com
export DEEPGRAM_API_KEY=your_actual_deepgram_key
```

### 2. Find your Omi device
```bash
# Scan for nearby Bluetooth devices
omi-scan
```

Look for a device named "Omi" and copy its MAC address:
```
0. Omi [7F52EC55-50C9-D1B9-E8D7-19B83217C97D]
```

### 3. Use in your Python code
```python
import asyncio
import os
from omi import listen_to_omi, OmiOpusDecoder, transcribe
from asyncio import Queue

# Configuration
OMI_MAC = "YOUR_OMI_MAC_ADDRESS_HERE"  # From omi-scan
OMI_CHAR_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"  # Standard Omi audio UUID
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

async def main():
    audio_queue = Queue()
    decoder = OmiOpusDecoder()
    
    def handle_audio(sender, data):
        pcm_data = decoder.decode_packet(data)
        if pcm_data:
            audio_queue.put_nowait(pcm_data)
    
    def handle_transcript(transcript):
        # Custom transcript handling
        print(f"🎤 {transcript}")
        # Save to file, send to API, etc.
    
    # Start transcription and device connection
    await asyncio.gather(
        listen_to_omi(OMI_MAC, OMI_CHAR_UUID, handle_audio),
        transcribe(audio_queue, DEEPGRAM_API_KEY, on_transcript=handle_transcript)
    )

if __name__ == "__main__":
    asyncio.run(main())
```

### 4. Run the example

The included example demonstrates connecting to an Omi device and real-time transcription:

```bash
# 1. Set your Deepgram API key
export DEEPGRAM_API_KEY=your_actual_deepgram_key

# 2. Find your Omi device MAC address
omi-scan

# 3. Update examples/main.py with your device's MAC address
# Edit line 10: OMI_MAC = "YOUR_DEVICE_MAC_HERE"

# 4. Run the example
python examples/main.py
```

The example will:
- Connect to your Omi device via Bluetooth
- Decode incoming Opus audio packets to PCM
- Transcribe audio in real-time using Deepgram
- Print transcriptions to the console

## 📚 API Reference

### Core Functions
- `omi.print_devices()` - Scan for Bluetooth devices
- `omi.listen_to_omi(mac, uuid, handler)` - Connect to Omi device
- `omi.OmiOpusDecoder()` - Decode Opus audio to PCM
- `omi.transcribe(queue, api_key)` - Real-time transcription

### Command Line Tools
- `omi-scan` - Scan for nearby Bluetooth devices

## 🔧 Development

### Local development setup
```bash
git clone https://github.com/BasedHardware/omi.git
cd omi/sdks/python

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in editable mode
pip install -e .

# Install dev dependencies
pip install -e ".[dev]"
```

## 🧩 Troubleshooting

- **Opus library error**: Make sure Opus audio codec is installed (see Prerequisites section)
- **Bluetooth permission errors on macOS**: Go to System Preferences → Privacy & Security → Bluetooth and grant access to Terminal and Python
- **Python version**: Requires Python 3.10+
- **Omi device**: Make sure device is powered on and nearby
- **WebSocket issues**: SDK uses `websockets>=11.0`

## 📄 License

MIT License — this is an unofficial SDK built by the community, not affiliated with Omi.

## 🙌 Credits

Built by the Omi community using Omi hardware and Deepgram's transcription engine.
