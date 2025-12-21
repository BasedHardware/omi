<!-- This file is auto-generated from docs/doc/developer/sdk/python.mdx. Do not edit manually. -->
## Overview

A pip-installable Python SDK for connecting to Omi wearable devices over Bluetooth, decoding Opus-encoded audio, and transcribing it in real time using Deepgram.

<CardGroup cols={3}>
  <Card title="Bluetooth Connection" icon="bluetooth">
    Connect to any Omi device
  </Card>
  <Card title="Opus Decoding" icon="waveform">
    Decode Opus audio to PCM
  </Card>
  <Card title="Real-time Transcription" icon="microphone">
    Deepgram-powered STT
  </Card>
</CardGroup>


## Quick Start

<Steps>
  <Step title="Set Up Your Environment">
    Get a free API key from [Deepgram](https://deepgram.com):

    ```bash
    export DEEPGRAM_API_KEY=your_actual_deepgram_key
    ```
  </Step>
  <Step title="Find Your Omi Device">
    Scan for nearby Bluetooth devices:

    ```bash
    omi-scan
    ```

    Look for a device named "Omi" and copy its MAC address:

    ```
    0. Omi [7F52EC55-50C9-D1B9-E8D7-19B83217C97D]
    ```
  </Step>
  <Step title="Write Your Code">
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
            print(f"Transcription: {transcript}")
            # Save to file, send to API, etc.

        # Start transcription and device connection
        await asyncio.gather(
            listen_to_omi(OMI_MAC, OMI_CHAR_UUID, handle_audio),
            transcribe(audio_queue, DEEPGRAM_API_KEY, on_transcript=handle_transcript)
        )

    if __name__ == "__main__":
        asyncio.run(main())
    ```
  </Step>
  <Step title="Run the Example">
    ```bash
    python examples/main.py
    ```

    The example will:
    - Connect to your Omi device via Bluetooth
    - Decode incoming Opus audio packets to PCM
    - Transcribe audio in real-time using Deepgram
    - Print transcriptions to the console
  </Step>
</Steps>


## Development

### Local Development Setup

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


## License

MIT License — this is an unofficial SDK built by the community.

