# Omi4Meta Reconstruction Progress

Recreated from transcript summaries, not original diffs.

## Current state

- Source copied from `/Users/Moni11811/omi-main` to `/Users/Moni11811/OMI4META`.
- Meta DAT dependency added: `meta_wearables_dat_flutter: ^0.7.1`.
- iOS DAT minimum raised to iOS 17.
- iOS `Info.plist` has `MWDAT`, `omimeta://`, `fb-viewapp`, background modes, Bonjour, and external accessory protocol.
- `DeviceType.metaWearables` added.
- `MetaWearablesService` added over `MetaWearablesDat` registration, devices, camera permission, diagnostics, and preview stream APIs.
- On-device Apple STT buffer lowered from 5s to 500ms.
- iOS 26 `SpeechAnalyzer` / `SpeechTranscriber` path added with legacy `SFSpeechURLRecognitionRequest` fallback.

## Proof

- Red test first: `test/unit/omi4meta_reconstruction_contract_test.dart`.
- Green now: `flutter test test/unit/omi4meta_reconstruction_contract_test.dart`.
- `plutil -lint ios/Runner/Info.plist`: OK.
- `flutter analyze --no-fatal-infos --no-fatal-warnings` on touched Dart files: exit 0, existing warnings remain.

## Blockers

- `flutter build ios --profile --flavor dev --no-codesign` stops before app Swift compile because the `dev` scheme embeds a watch app and this machine has no watchOS 26.5 runtime.
- Direct plugin scheme compile still lacks Flutter SPM wiring for `MWDATCore` / `MWDATCamera`; Flutter SPM was enabled with `flutter config --enable-swift-package-manager`, but the standalone Xcode plugin scheme does not pick it up.

## Not yet recreated

- Old Omi4Meta UI flow wiring.
- Device ID to nickname map.
- Paired device list.
- EddyPhone install.
