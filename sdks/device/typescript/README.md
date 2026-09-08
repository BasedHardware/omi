# @basedhardware/omi-device (TypeScript)

Shared Omi device BLE constants + packet framing.

- Full BLE stack on React Native: use existing `sdks/react-native` (`OmiConnection`).
- This package is the portable protocol layer for Node/Web/custom transports.

```ts
import { AUDIO_DATA_UUID, stripPacketHeader, OmiDeviceSession } from '@basedhardware/omi-device';
```

### Release ble resources when audio setup fails

Failed BLE setup cleans up the acquired peripheral and audio listener. The returned disconnect operation is idempotent, including concurrent calls. Run `bun test` for the hardware-free suite and `bunx tsc --noEmit` for type checking; BLE tests are also selected by repository preflight.
