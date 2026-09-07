# @basedhardware/omi-device (TypeScript)

Shared Omi device BLE constants + packet framing.

- Full BLE stack on React Native: use existing `sdks/react-native` (`OmiConnection`).
- This package is the portable protocol layer for Node/Web/custom transports.

```ts
import { AUDIO_DATA_UUID, stripPacketHeader, OmiDeviceSession } from '@basedhardware/omi-device';
```

For the local Whisper transcriber, `stop()` stops accepting new audio and
flushes any buffered tail. Transcription already in progress still delivers its
result through `onTranscript`, so callbacks may occur after `stop()` returns.

Run `bun test` in this directory for the SDK's hardware-free unit tests. The same
suite runs through the repository's shared preflight manifest locally and in CI.
