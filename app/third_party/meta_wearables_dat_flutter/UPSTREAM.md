# Upstream provenance

- Source: https://github.com/iSee-Labs/meta-wearables-dat-flutter
- Base commit: `f13cf7e2bfbbc25bdbd42ca4972be1834c724624`
- Upstream version: `0.7.1`
- License: MIT; see `LICENSE` and `NOTICE`.

The vendored tree contains 45 files. Compared byte-for-byte with the base
commit above, 30 files are unchanged, 15 modified files are listed below, and
there are no vendor-only files.

## Omi changes

- `ios/meta_wearables_dat_flutter/Package.swift`
- `ios/meta_wearables_dat_flutter/Sources/meta_wearables_dat_flutter/BackgroundStreamingController.swift`
- `ios/meta_wearables_dat_flutter/Sources/meta_wearables_dat_flutter/MetaMockDeviceManager.swift`
- `ios/meta_wearables_dat_flutter/Sources/meta_wearables_dat_flutter/MetaSessionManager.swift`
- `ios/meta_wearables_dat_flutter/Sources/meta_wearables_dat_flutter/MetaWearablesDatPlugin.swift`
- `android/src/main/kotlin/com/iseelabs/meta_wearables_dat_flutter/MetaWearablesDatPlugin.kt`
- `lib/meta_wearables_dat_flutter.dart`
- `lib/src/meta_wearables_dat_method_channel.dart`
- `lib/src/meta_wearables_dat_platform_interface.dart`
- `lib/src/models/dat_error.dart`
- `lib/src/models/device_info.dart`
- `lib/src/models/display/display_components.dart`
- `lib/src/models/frame_data.dart`
- `lib/src/models/session_state.dart`
- `test/meta_wearables_dat_flutter_test.dart`

The changes add Omi's link-state mapping, latest-frame JPEG capture, firmware
and DAT-app update commands, production-safe mock handling, background HFP
audio behavior, and matching Dart/platform tests. Official Meta iOS and
Android DAT SDK binaries remain build-time dependencies; they are not copied
into this directory.

## Why vendored

Omi's required native and Dart API changes are not present in upstream 0.7.1.
Keeping the pinned source in-tree makes that delta reviewable and prevents a
mutable Git dependency from changing device, camera, or background behavior.
Replace this copy with a pinned package/tag after the required APIs land
upstream.

## Verification

```bash
git clone https://github.com/iSee-Labs/meta-wearables-dat-flutter.git /tmp/meta-wearables-dat-flutter
git -C /tmp/meta-wearables-dat-flutter checkout f13cf7e2bfbbc25bdbd42ca4972be1834c724624
diff -ru /tmp/meta-wearables-dat-flutter app/third_party/meta_wearables_dat_flutter
```
