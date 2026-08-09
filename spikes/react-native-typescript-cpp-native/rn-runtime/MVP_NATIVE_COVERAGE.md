# Omi native MVP coverage

This is a spike artifact, not production Omi integration.

## Source inventory

The capability inventory was taken from the original Flutter platform boundary at:

```text
/Users/undivisible/workspace/omi/upstream-keep-clean/app/lib/pigeon_interfaces.dart
```

The original app also contains platform implementations for Bluetooth, audio, notifications, Wi-Fi, phone calls, camera/glasses, permissions, and background lifecycle under the upstream app tree.

## RN MVP contract

`rn-runtime/src/omiNative.ts` defines the TypeScript-first native seam and a deterministic host adapter.

| Capability | Contract coverage | Runtime evidence |
|---|---:|---|
| Bluetooth state and permissions | yes | host adapter test |
| BLE scan / stop / connect / disconnect | yes | host adapter test |
| GATT read / write / subscribe / unsubscribe | yes | host adapter test |
| RSSI streaming / battery history / diagnostics | yes | host adapter test |
| Stream and batch capture lifecycle | yes | host adapter test |
| Microphone and audio route | yes | host adapter test |
| Phone-call controls | yes | host adapter test |
| Notification-on-kill service | yes | host adapter test |
| Wi-Fi network status | yes | host adapter test |
| Background mode | yes | host adapter test |
| Watch status | yes | host adapter test |
| Camera status / photo capture | yes | host adapter test |

## Evidence boundary

Proven now:

- TypeScript UI renders the capability cockpit.
- UI actions update through the typed native seam.
- Every listed contract is exercised by `__tests__/omiNative.test.ts`.
- React Native lint, Jest, TypeScript, and Android debug APK build pass.
- The existing C++ packet boundary builds and passes its CTest.

Not proven yet:

- A real `NativeModules.OmiNative` implementation on Android or iOS.
- C++ execution inside the RN process; current C++ proof is host CTest only.
- BLE/audio/camera/background behavior on physical hardware.
- Watch, glasses, or phone-call behavior without corresponding hardware and permissions.

The app deliberately labels the fallback as `HOST ADAPTER` so the spike cannot be mistaken for device parity.
