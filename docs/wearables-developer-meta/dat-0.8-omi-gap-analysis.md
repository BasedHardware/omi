# Meta DAT 0.8 OMI Gap Analysis

Date: 2026-07-03

Theory: OMI now has a good Flutter/provider scaffold and a native DAT Flutter plugin. Remaining risk is not API discovery. Remaining risk is end-to-end wiring: URL callback, display config, real device lifecycle, and test harness.

## Docs Baseline

- Scraped DAT 0.8 reference pages: 81.
- Groups: camera 11, core 31, display 25, mockdevice 12, mockdevicetestclient 1, index 1.
- Local mirror: `docs/wearables-developer-meta/reference/ios_swift/dat/0.8/`.

## Already Covered

- Native plugin exists: `app/third_party/meta_wearables_dat_flutter/`.
- Plugin imports/uses `MWDATCore`, `MWDATCamera`, `MWDATDisplay`.
- Plugin exposes registration, device streams, camera permission, stream session, photo capture, display session, and MockDeviceKit methods.
- App plist has URL schemes, `fb-viewapp`, external accessory protocol, Bluetooth/background modes, `MWDAT.AppLinkURLScheme`, `MetaAppID`, `ClientToken`, `TeamID`.
- AppDelegate forwards open URLs to the DAT plugin notification `MetaWearablesDatHandleURL` while preserving the existing Dart deep-link fallback.
- App plist enables Display with `MWDAT.DAMEnabled` and has `NSLocalNetworkUsageDescription` alongside `NSBonjourServices`.
- Camera permission now has app-visible states: `notRegistered`, `unavailable`, `needsRequest`, `requesting`, and `granted`.
- Provider preserves the plugin `requestCameraPermission()` result and shows an in-flight request state in the permission CTA.
- Stream/photo defaults are now documented by contract: raw codec, medium preview, low photo capture, and DAT-valid 7 fps photo sessions.
- Provider now surfaces stream/device session states, keeps `paused` passive, releases stream resources on `stopped`, and maps session errors into `lastError`.
- Firmware and DAT-glasses-app update-required compatibility states now have plugin wrappers, provider dispatch, and update CTAs on the glasses page and devices hub.
- Meta glasses rows now show localized device-kind metadata on both the glasses page and devices hub.
- Display scope is explicitly gated to a Ray-Ban Display capture status card; no standalone Display DSL UI is offered yet.
- MockDeviceKit smoke coverage now drives enable -> pair -> power -> unfold -> don -> permission -> captured image -> provider preview/photo queue without hardware.
- iOS generic Profile-dev build passes after SPM repair with signing disabled.
- agent-flutter simulator proof now covers the debug-only Meta UI proof harness on `DevicesPage` and `MetaGlassesPage`.
- Flutter app uses registration/device streams, camera permission, capture modes, photo queue, display session calls, and devices hub UI.
- Reconstruction contract test exists and passed after the stale assertion fix.

## P0 Gaps

1. Real-device lifecycle proof incomplete.
   - Provider now handles `started`, `paused`, `stopped`, stream errors, and session errors.
   - Need proof for: hinge close/open, glasses removed, registration revoked, permission denied, another app/session preempts OMI.
   - EddyPhone proof attempt on 2026-07-03 reached signing, then failed before install because Xcode has no account/profiles for team `9536L8KLMP`, bundle `dev.moni11811.omi`, and widget bundle `dev.moni11811.omi.widget`.
   - Local signing check found code-sign identities, but zero installed provisioning profiles matching `dev.moni11811.omi` or team `9536L8KLMP`.
   - `xcodebuild ... -allowProvisioningUpdates` with the project team still fails with `No Account for Team "9536L8KLMP"` and no profiles for `dev.moni11811.omi` / `dev.moni11811.omi.widget`.
   - Alternate local team `GRSWQKJR57` has an EddyPhone-capable wildcard profile, but it is not equivalent: it cannot satisfy the app's required entitlements (`aps-environment`, Apple Sign In, Associated Domains, HealthKit, Hotspot Configuration, Wi-Fi info, App Groups), and it also conflicts with the existing App Group.
   - Xcode prefs only show `GRSWQKJR57` as the local provisioning team; `~/.appstoreconnect/private_keys/AuthKey_PG9SF4822K.p8` exists, but no issuer metadata was found locally, so it cannot be used for `xcodebuild -authenticationKey...`.
   - Risk: generic build plus simulator proof is not enough for hardware lifecycle.

2. Hardware DAT capture proof incomplete.
   - MockDeviceKit proves the app/provider path without hardware.
   - Need real glasses proof for registration callback, permission prompt/result, preview stream, manual photo capture, background/gesture capture, and display status card.

## Completed Gaps

1. URL callback bridge.
   - Added contract coverage for native DAT callback forwarding.
   - `AppDelegate.application(_:open:options:)` now posts `MetaWearablesDatHandleURL` for the plugin before preserving Dart deep-link forwarding.
   - Verified focused callback test and full reconstruction contract.

2. Display access plist.
   - Added contract coverage for Display scope and plist config.
   - Added `MWDAT.DAMEnabled` and `NSLocalNetworkUsageDescription`.
   - Verified focused Display plist test and full reconstruction contract.

3. Camera permission state split.
   - Added contract coverage for explicit app-visible permission states.
   - Added `MetaGlassesCameraPermissionState` and provider `isRequestingCameraPermission`.
   - `MetaWearablesService.requestCameraPermission()` now returns the plugin result instead of discarding it.
   - Verified focused permission-state test, touched-file analyzer, and full reconstruction contract.

4. Stream/photo configuration defaults.
   - Added contract coverage for DAT-valid frame rates and chosen defaults.
   - Plugin default remains raw codec, 30 fps, medium quality.
   - Background photo capture now uses low quality and 7 fps, matching DAT's valid frame-rate set: 2/7/15/24/30.
   - Verified red focused StreamSession contract, green focused contract, touched-file analyzer, and full reconstruction contract.

5. Session lifecycle state handling.
   - Added contract coverage for stream/device state streams, error streams, and video size stream.
   - Provider tracks `StreamSessionState` and `DeviceSessionState`.
   - `paused` is passive; `stopped` releases preview/photo timer resources so a later session can start cleanly.
   - Stream and device session errors clear stream resources and surface `lastError`.
   - Verified red focused lifecycle contract, green focused contract, touched-file analyzer, and full reconstruction contract.

6. Compatibility update actions.
   - Added contract coverage for `deviceUpdateRequired` and `sdkUpdateRequired` recovery.
   - Added plugin/public/platform/method-channel/iOS wrappers for `openFirmwareUpdate()` and `openDATGlassesAppUpdate()`.
   - Added provider dispatch and update CTAs on `MetaGlassesPage` and `DevicesPage`.
   - Verified red focused update-CTA contract, green focused contract, touched-file analyzer, and full reconstruction contract.

7. Device-kind metadata in rows.
   - Added contract coverage for doc-level device kind labels in `MetaGlassesPage` and `DevicesPage`.
   - Added localized labels for Ray-Ban Meta, Meta Ray-Ban Display, and Oakley Meta across all ARB locales.
   - Generated l10n getters and added a shared `metaWearablesDeviceKindLabel` helper.
   - Verified red focused metadata contract, green focused contract, l10n generation, touched-file analyzer, full reconstruction contract, and 49/49 ARB key coverage.

8. Display scope gate.
   - Added contract coverage for Display scope.
   - Provider exposes `canShowDisplayStatus` only for `DeviceKind.rayBanDisplay`.
   - Advanced Display UI remains disabled; the app only sends a capture status `FlexBox`/`DisplayText` card.
   - Verified red focused Display-scope contract, green focused contract, touched-file analyzer, and full reconstruction contract.

9. MockDeviceKit smoke harness.
   - Added contract coverage requiring a focused MockDeviceKit smoke test.
   - Added `test/unit/meta_wearables_mockdevice_smoke_test.dart`.
   - Fake DAT platform exercises the same public MockDeviceKit calls as hardware-free setup: enable, pair, power, unfold, don, grant camera, set captured image.
   - Provider initializes from the fake DAT service, starts preview, captures a photo, and proves the image reaches the on-disk provider queue.
   - Verified red contract, red smoke on missing `dumpDiagnostics`, green smoke, touched-file analyzer, and contract+smoke test run.

10. iOS generic build proof.
    - Ran `./scripts/repair_flutter_spm_ios_target.sh` successfully.
    - First generic build failed on `openFirmwareUpdate()`/`openDATGlassesAppUpdate()` missing `try await`.
    - Patched iOS wrapper to call both DAT update helpers with `try await` and return Flutter errors on failure.
    - Incremental `xcodebuild -workspace ios/Runner.xcworkspace -scheme dev -configuration Profile-dev -destination 'generic/platform=iOS' -derivedDataPath /tmp/omi4meta-dat-full-dd CODE_SIGNING_ALLOWED=NO COMPILER_INDEX_STORE_ENABLE=NO build` succeeded.

11. Flutter UI proof harness.
    - Added a debug-only compile-time gate: `--dart-define=OMI_META_UI_PROOF=true`.
    - Harness injects a proof `MetaWearablesProvider` with Ray-Ban Meta and Meta Ray-Ban Display devices plus update-required compatibility states.
    - agent-flutter simulator proof captured `DevicesPage` rows and `MetaGlassesPage` rows/capture mode.
    - Screenshots: `/tmp/omi4meta-meta-ui-proof.png`, `/tmp/omi4meta-meta-ui-proof-glasses.png`.

12. EddyPhone dev signing assets.
    - Created Apple Developer App Group `group.dev.moni11811.omi` under team `GRSWQKJR57`.
    - Created/configured App IDs `dev.moni11811.omi` and `dev.moni11811.omi.widget` with required app-group capability.
    - Created/downloaded/installed EddyPhone iOS development profiles:
      `OMI Dev EddyPhone Development` and `OMI Dev Widget EddyPhone Development`.
    - Added `ios_dev_signing_contract_test.dart` so the dev signing team and app group cannot silently regress.
    - `flutter run --flavor dev -d 00008130-000C04D81891401C --dart-define=OMI_META_UI_PROOF=true` completed the Xcode build.
    - `xcrun devicectl device install app --device 00008130-000C04D81891401C build/ios/iphoneos/Runner.app` installed `dev.moni11811.omi` on EddyPhone.
    - Red launch proof: the Debug build crashed outside Flutter tooling with `Cannot create a FlutterEngine instance in debug mode without Flutter tooling or Xcode`.
    - Green launch proof: `flutter build ios --profile --flavor dev --dart-define=OMI_META_UI_PROOF=true` built `Runner.app`, `devicectl` installed it, launched PID `18974`, and `awaitTermination --timeout 12` timed out, proving the app stayed alive.

## P2 Gaps

1. Docs mirror should be indexed/searchable for agents.
    - Files exist.
    - Add index/search helper or mention canonical path in AGENTS if this lane continues.

## Recommended Next Patch Order

1. Re-run without proof harness and exercise real DAT glasses registration, permission, stream, photo, background/gesture, and display status flows.
