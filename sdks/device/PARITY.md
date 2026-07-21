# Device SDK parity matrix

| Capability | Python | Swift | React Native | TS device | Go | Rust | Dart | C++ |
|------------|--------|-------|--------------|-----------|----|------|------|-----|
| BLE UUIDs / packet strip | yes | yes | yes | yes | yes | yes | yes | yes |
| Full BLE scan/connect | yes (bleak) | yes (CoreBluetooth) | yes (ble-plx) | transport inject | feature/build-tag | feature `ble` | yes (flutter_blue_plus) | macro `OMI_DEVICE_BLE` |
| STT Deepgram | yes | yes | yes | yes | yes | feature `stt-deepgram` | yes* | URL helper |
| STT Whisper | optional extra / runner | yes (SwiftWhisper) | injected runner | injected runner | injected runner | feature `stt-whisper` | injected runner | macro |
| STT Parakeet `/v3/stream` | yes | yes | yes | yes | yes | feature `stt-parakeet` | yes | URL helper |
| Opus decode | yes (opuslib) | yes | platform | n/a | n/a | n/a | n/a | n/a |

\* Dart Deepgram URL is constructed; some platforms need a WS client that can send `Authorization` headers.

PCM contract for all STT engines: **16-bit LE mono @ 16 kHz**.
