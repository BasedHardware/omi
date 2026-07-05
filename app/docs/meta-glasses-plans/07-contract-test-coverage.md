# 07 — Contract-test the new surface

## Goal
The camera-permission state machine, compatibility update actions, and
device-kind labels (added during the Codex refactor) have no test coverage.
Pin them so a future edit can't silently regress them.

## Grounding
- Test file: `test/unit/omi4meta_reconstruction_contract_test.dart` (source-grep style assertions) and `test/unit/meta_glasses_device_sanitize_test.dart` (behavioral unit tests). Follow their existing patterns.
- Surface to cover (all present in current code):
  - `lib/services/devices/meta_wearables_service.dart`: `MetaGlassesCameraPermissionState`, `openFirmwareUpdate()`, `openDATGlassesAppUpdate()`, `cameraPermissionState` on snapshot.
  - `lib/providers/meta_wearables_provider.dart`: `openCompatibilityUpdate(device)`, `hasCompatibilityUpdateAction(device)`, `cameraPermissionState`, `isRequestingCameraPermission`, `capturedAtFromQueueFile` (already unit-tested), `_sessionTargetUuid`, `_manualStopRequested`, gesture debounce.
  - `lib/utils/meta_wearables_device_label.dart`: `metaWearablesDeviceKindLabel`.
  - Plugin 4-layer for `openFirmwareUpdate`/`openDATGlassesAppUpdate` (facade + interface + method channel + native Swift handler present).

## Steps
1. Add a contract test asserting the service exposes `MetaGlassesCameraPermissionState` with the 5 states and `openFirmwareUpdate`/`openDATGlassesAppUpdate`, and that native `MetaWearablesDatPlugin.swift` has `case "openFirmwareUpdate"` and `case "openDATGlassesAppUpdate"` (guards against a Dart-only add).
2. Add a behavioral unit test for `openCompatibilityUpdate`: with a fake `MetaWearablesService` recording calls, `deviceUpdateRequired` → `openFirmwareUpdate` called; `sdkUpdateRequired` → `openDATGlassesAppUpdate`; `compatible`/`unknown` → neither.
3. Unit-test `metaWearablesDeviceKindLabel` maps each `DeviceKind` to the right l10n getter (use a real `AppLocalizations` for `en`).
4. Assert every new ARB key added by the refactor exists in `app_en.arb` (`metaGlassesTypeRayBanMeta`, `metaGlassesTypeRayBanDisplay`, `metaGlassesTypeOakleyMeta`).
5. If plans 01/02/03/04 land first, extend this file to cover their surfaces too (thermal mapping, pause/resume ordering, display throttle, frame throttle).

## Acceptance
- New tests fail if any covered symbol is removed/renamed, and pass on current code.
- `flutter test test/unit/omi4meta_reconstruction_contract_test.dart test/unit/meta_glasses_device_sanitize_test.dart` green.
- Analyze clean.
