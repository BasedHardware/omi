# @basedhardware/omi-device (TypeScript)

Shared Omi device BLE constants + packet framing.

`scanForDevices(timeoutMs)` collects advertisements for the requested interval
after scanning starts, then removes its listener and stops scanning. An empty
scan returns `[]`; no advertisement is required to finish the scan.
Binding-level scan pauses are resumed while the adapter remains powered on,
without resetting that interval. A failed resume rejects the scan and cleans up
its subscriptions. Cleanup waits for an in-flight resume before stopping.

Run the hermetic SDK suite with `bun test sdks/device/typescript` from the
repository root. Bluetooth adapter behavior is mocked; these tests do not
establish physical-device compatibility.

- Full BLE stack on React Native: use existing `sdks/react-native` (`OmiConnection`).
- This package is the portable protocol layer for Node/Web/custom transports.

```ts
import { AUDIO_DATA_UUID, stripPacketHeader, OmiDeviceSession } from '@basedhardware/omi-device';
```
