# @basedhardware/omi-device (TypeScript)

Shared Omi device BLE constants + packet framing.

- Full BLE stack on React Native: use existing `sdks/react-native` (`OmiConnection`).
- This package is the portable protocol layer for Node/Web/custom transports.

```ts
import { AUDIO_DATA_UUID, stripPacketHeader, OmiDeviceSession } from '@basedhardware/omi-device';
```

For Node BLE connections, install the optional `@stoprocent/noble` dependency and
use `connectAndListen(deviceId, onPacket)`. Its service and characteristic discovery
filters use Noble's lowercase UUID format without dashes; exported protocol UUIDs
retain their standard dashed format.

The local Whisper transcriber's `stop()` closes audio input and queues any buffered
tail. Accepted batches finish in input order, including work already running when
stopped. `stop()` returns immediately, so transcript callbacks can continue afterward.
Empty or failed runner results are skipped without blocking later batches; repeated
stops and PCM appended after stopping do not submit more work.

Run the component's hermetic tests with the repository CI version, Bun 1.3.14:

```sh
bun test sdks/device/typescript
```

The tests include discovery, audio delivery and disconnect through a mocked Noble
adapter, so they require no native BLE dependency or hardware. This suite is selected
by the shared local/CI check manifest when this SDK changes. With the package's
development dependencies installed, `bun run typecheck` from this directory checks
the production TypeScript source.
