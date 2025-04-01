# Omi Python SDK Documentation

## Overview

The Omi Python SDK provides a set of tools for interacting with Omi devices. It offers features such as real-time BLE connection, Opus audio decoding, live transcription, and more.

## Installation

To install the Omi Python SDK, use the following command:

```bash
pip install omi-sdk
```

## Usage

### Connecting to an Omi Device

```python
from omi_sdk import OmiDevice

# Initialize the Omi device
omi_device = OmiDevice()

# Connect to the device
omi_device.connect()
```

### Streaming Audio

```python
# Stream audio from the device
audio_stream = omi_device.stream_audio()

# Process the audio stream
for audio_chunk in audio_stream:
    # Process the audio chunk
    pass
```

### Live Transcription

```python
# Enable live transcription
omi_device.enable_transcription()

# Get transcribed text
transcribed_text = omi_device.get_transcription()
```

## API Reference

For a detailed API reference, please refer to the [official documentation](https://docs.omi.me/docs/developer/sdk/python).

## Troubleshooting

- **Connection Issues**: Ensure that the Omi device is powered on and within range.
- **Audio Streaming Problems**: Check the device's audio settings and ensure that the audio stream is enabled.

## License

This project is licensed under the MIT License.

## Credits

Special thanks to the Omi development team for their contributions.
