# 06 — Mock Device Kit integration tests

## Goal
Replace the manual `OMI_META_UI_PROOF` screenshot screen with real, CI-runnable
tests driven by Meta's Mock Device Kit — pair simulated glasses, feed a fixed
image, and assert the capture pipeline end-to-end without hardware.

## Grounding (verified)
- Facade: `enableMockDevice({bool initiallyRegistered, bool initialPermissionsGranted})`, `disableMockDevice()`, `pairMockRayBanMeta()`, `pairedMockDevices()`, `setMockCameraFeed(uuid, path)`, `setMockCapturedImage(uuid, path)`, `mockPowerOn/Off`, `mockDon/Doff`, `setMockPermission(...)`.
- **Important:** the current install build *excludes* the mock SDK compile path (contract test "Meta DAT install build excludes mock SDK compile path" asserts `MWDATMockDevice` is not linked and `MetaMockDeviceManager.swift` is a stub). Mock support must be **debug/test-only** so it never links into a shipped build.

## Steps
1. Gate mock behind a compile flag + `kDebugMode`, e.g. `bool.fromEnvironment('OMI_META_MOCK')`. Do NOT enable it in profile/release. Keep the install-build exclusion contract test green — if enabling the mock SDK requires linking `MWDATMockDevice`, do it only under a debug-only SPM/pod configuration, not the default target.
2. Add `integration_test/meta_glasses_mock_test.dart` (the `integration_test` dep already exists but is unused). It should: enable mock + register, `pairMockRayBanMeta()`, `setMockCapturedImage` to a bundled fixture, start capture via `MetaWearablesProvider`, and assert a photo lands in `CaptureController.photos` with the fixture bytes and correct `createdAt` ordering.
3. Cover the sanitizer/link-state paths with mock devices in two link states.
4. Once the mock harness exists, convert `lib/debug/meta_wearables_ui_proof.dart` into a thin wrapper that reuses the mock service, or delete it in favor of the tests (keep only if still useful for manual visual QA — but it must stay `kDebugMode`-gated per plan constraints).
5. Document how to run: `flutter test integration_test/meta_glasses_mock_test.dart --dart-define=OMI_META_MOCK=true` in `app/AGENTS.md` §Meta Wearables.

## Tests
- The integration test itself is the deliverable. Also add a contract-test assertion that mock code is `kDebugMode`/define-gated and the install-build exclusion still holds.

## Acceptance
- `flutter test integration_test/...` pairs a mock Ray-Ban, captures a fixture image, and asserts it flows through the queue → conversation.
- Default (non-mock) build unchanged; "excludes mock SDK compile path" contract test still green.
- Analyze clean.
