# @basedhardware/omi-device (TypeScript)

Shared Omi device BLE constants + packet framing.

- Full BLE stack on React Native: use existing `sdks/react-native` (`OmiConnection`).
- This package is the portable protocol layer for Node/Web/custom transports.

```ts
import { AUDIO_DATA_UUID, stripPacketHeader, OmiDeviceSession } from '@basedhardware/omi-device';
```
