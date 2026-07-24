# Omi Device STT Engines (parity contract)

All device SDKs expose the same three transcription backends. Each is **optional / feature-gated**.

| Engine | Mode | Config | Default |
|--------|------|--------|---------|
| `deepgram` | streaming WS | `DEEPGRAM_API_KEY` | Python default |
| `whisper` | local / file or frames | model path or injected runner | Swift default (`ggml-tiny.en`) |
| `parakeet` | streaming WS (`/v3/stream`) | `HOSTED_PARAKEET_API_URL` (http→ws) | hosted Omi Parakeet |

## Common interface (logical)

```
start(pcm16le_mono_16khz chunks) -> transcript events
stop()
```

PCM contract matches BLE decode: **16-bit LE mono @ 16 kHz**.

## Feature gates by language

| Lang | BLE gate | Deepgram | Whisper | Parakeet |
|------|----------|----------|---------|----------|
| Python | always (bleak dep) | default extra | optional `whisper` extra | optional `parakeet` |
| Swift | always (CoreBluetooth) | compile `OMI_STT_DEEPGRAM` / always-on client | default SwiftWhisper | always-on client |
| React Native | peer `react-native-ble-plx` | always-on JS WS | optional injected `WhisperRunner` | always-on JS WS |
| TypeScript device | optional `BleTransport` | optional | optional runner | optional |
| Go | build tag `ble` | default net | build tag `whisper` | default net |
| Rust | feature `ble` | feature `stt-deepgram` | feature `stt-whisper` | feature `stt-parakeet` |
| Dart | optional BLE package later | always-on | optional runner | always-on |
| C++ | `OMI_DEVICE_BLE` | `OMI_STT_DEEPGRAM` | `OMI_STT_WHISPER` | `OMI_STT_PARAKEET` |

## Parakeet wire format

- Base: `HOSTED_PARAKEET_API_URL` e.g. `https://parakeet.example`
- WS: replace http→ws, append `/v3/stream?sample_rate=16000`
- Wait for JSON `{"type":"ready"}`
- Send raw PCM bytes; send string `finalize` to end
