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

## Android C++ counterpart

The Android target now contains a registered legacy React Native module backed by JNI and the portable C++ boundary:

- `android/app/src/main/java/com/rnruntime/OmiNativeModule.kt` registers `NativeModules.OmiNative`.
- `android/app/src/main/cpp/jni_bridge.cpp` forwards packet normalization and capability queries into `cpp/src/omi_native_boundary.cpp`.
- `android/app/src/main/cpp/CMakeLists.txt` links the boundary for all APK ABIs.
- `MainApplication.kt` manually registers the package.
- Verified: `./gradlew clean assembleDebug` passed; APK contains `libomi_native.so` for arm64-v8a, armeabi-v7a, x86, and x86_64; JNI symbols are present.

The Android module deliberately rejects hardware-only operations with `NATIVE_ADAPTER_UNAVAILABLE` until Bluetooth/audio/camera/background implementations are added. It does not claim device parity.

## iOS C++ counterpart

The iOS target now contains the smallest legacy React Native bridge for the portable C ABI:

- `ios/RnRuntime/OmiCppBoundary.mm` exports `NativeModules.OmiCppBoundary.normalizePacket(rawData)` and `getNativeCapabilities()`.
- `ios/RnRuntime.xcodeproj/project.pbxproj` compiles the Objective-C++ file and the shared `../../cpp/src/omi_native_boundary.cpp` implementation, with `../../cpp/include` in the target header search path.
- `src/omiCppBoundary.ts` is an intentionally separate wrapper; it does not replace the broader `omiNative` host adapter until the full capability contract exists.
- Verified: `pod install --repo-update` and `xcodebuild -workspace ios/RnRuntime.xcworkspace -scheme RnRuntime -sdk iphonesimulator -configuration Debug build CODE_SIGNING_ALLOWED=NO` both pass. The `fmt` pod is forced to C++17 because Xcode Beta's C++20 consteval implementation rejects fmt 11's bundled compile-time format calls.
- `__tests__/omiCppBoundary.test.ts` verifies the JS forwarding contract with a Jest mock; it is not native runtime proof.

After installing the Ruby/CocoaPods prerequisites, the target build command is:

```sh
bundle exec pod install
xcodebuild -project ios/RnRuntime.xcodeproj -scheme RnRuntime -sdk iphonesimulator -configuration Debug build CODE_SIGNING_ALLOWED=NO
```

## Evidence boundary

Proven now:

- TypeScript UI renders the capability cockpit.
- UI actions select `NativeModules.OmiNative` when registered and otherwise use the explicit host adapter.
- Every listed contract is exercised by `__tests__/omiNative.test.ts`.
- The Android `OmiNative` package is registered and its JNI library is linked into a real debug APK.
- Android APK includes the JNI library for four ABIs and exports the expected JNI symbols.
- React Native lint, Jest, TypeScript, and Android debug APK build pass.
- The existing C++ packet boundary builds and passes its CTest.

Not proven yet:

- BLE/audio/camera/background behavior on physical hardware; Android returns explicit unavailable errors for those paths.
- A runtime-loaded iOS module in a physical app process. `OmiCppBoundary` is compiled and linked in the simulator build; physical-device execution still requires a signed install and runtime exercise.
- Watch, glasses, or phone-call behavior without corresponding hardware and permissions.

The app deliberately labels the fallback as `HOST ADAPTER` so the spike cannot be mistaken for device parity.
