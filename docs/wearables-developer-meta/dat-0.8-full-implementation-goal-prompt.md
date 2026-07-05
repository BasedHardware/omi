# Meta DAT 0.8 Full Implementation Goal Prompt

Use this prompt to hand off the remaining Meta Wearables DAT 0.8 implementation in `/Users/Moni11811/OMI4META`.

```text
You are working in /Users/Moni11811/OMI4META.

Goal: Build the Meta Wearables DAT 0.8 integration fully for the OMI Flutter iOS app, using the local scraped docs as the source of truth.

Local docs:
- Reference mirror: docs/wearables-developer-meta/reference/ios_swift/dat/0.8/
- Manifest: docs/wearables-developer-meta/reference/ios_swift/dat/0.8/manifest.json
- Gap analysis: docs/wearables-developer-meta/dat-0.8-omi-gap-analysis.md

Hard rules:
- Follow AGENTS.md.
- Maximum brevity in status.
- State theory of the bug before each patch.
- Write the failing regression test first.
- Do not claim done without fresh verification.
- Forbidden: shipping a new build until the previous symptom has a regression test that fails without the fix.
- Do not push, create PRs, or touch main unless explicitly asked.
- Use the existing local docs. Do not guess DAT APIs.
- Keep proof lanes separate: unit/contract tests, analyzer, iOS build, MockDeviceKit harness, real EddyPhone proof.

Current known state:
- Flutter/provider scaffold exists.
- Native plugin exists under app/third_party/meta_wearables_dat_flutter/.
- Plugin exposes registration, device streams, camera permission, stream session, photo capture, display session, and MockDeviceKit methods.
- App plist already has URL schemes, fb-viewapp, external accessory protocol, Bluetooth/background modes, MWDAT.AppLinkURLScheme, MetaAppID, ClientToken, TeamID.
- Scraped docs list 81 DAT 0.8 pages: camera, core, display, mockdevice, mockdevicetestclient.

Build fully means:
1. Registration callback works end-to-end.
2. Camera permission state is complete and visible.
3. Device list and devices hub represent all linked glasses with compatibility/link state.
4. Stream/photo capture lifecycle follows DAT session rules.
5. Background/gesture/manual capture all feed the OMI conversation image pipeline.
6. Display support either works completely or is explicitly gated off.
7. MockDeviceKit smoke tests prove the app path without hardware.
8. Real EddyPhone install/launch proof is collected only after tests pass.

Required implementation order:

Phase 1: URL callback bridge
- Theory: registration starts but may not complete because the Meta AI callback is not routed to MetaWearablesDatFlutter.handleUrl.
- Write failing test in app/test/unit/omi4meta_reconstruction_contract_test.dart that requires:
  - AppDelegate open-url callback handles DAT callback URLs, or
  - Flutter deep-link listener calls MetaWearablesDatFlutter.handleUrl.
- Run focused test and confirm failure.
- Implement the smallest bridge.
- Verify focused test passes.
- Verify app/ios callback logic still forwards existing OAuth/deep-link behavior.

Phase 2: Display config decision
- Theory: display session API exists, but plist lacks DAT display enablement keys.
- Decide from product code whether Display is in scope.
- If Display is in scope:
  - Add failing contract test requiring MWDAT.DAMEnabled true.
  - Add failing contract test requiring NSLocalNetworkUsageDescription when NSBonjourServices is present.
  - Patch app/ios/Runner/Info.plist.
  - Verify focused test.
- If Display is not in scope:
  - Hide or gate display UI/actions.
  - Add failing test proving gated display actions are not offered.

Phase 3: Camera permission states
- Theory: registration and camera permission are separate DAT flows; UI must distinguish them.
- Add tests for registered/unregistered, camera granted/denied/unavailable, request in progress, and permission lost.
- Use MetaWearablesDatFlutter.getCameraPermissionStatus and requestCameraPermission.
- Surface states in provider and page.
- Verify no hardcoded strings outside l10n.

Phase 4: Session lifecycle
- Theory: happy-path start/stop is not enough; DAT sessions pause/stop on hinge, doff, disconnect, another session, revoked registration, or thermal/error state.
- Add tests for provider reactions to:
  - streamSessionStateStream
  - streamSessionErrorStream
  - deviceSessionStateStream
  - deviceSessionErrorStream
  - videoStreamSizeStream
- Ensure paused does not auto-restart.
- Ensure stopped releases resources and allows a new session.
- Ensure errors map to actionable UI state.

Phase 5: Device compatibility and update CTAs
- Theory: docs expose compatibility/link state; users need recovery actions for update-required states.
- Add tests requiring every Meta glasses row to show:
  - sanitized name or id
  - device type
  - link state
  - compatibility
  - update-required CTA when compatibility requires it
- If plugin lacks openFirmwareUpdate/openDATGlassesAppUpdate, add wrapper support in plugin first, with tests.
- Wire UI actions.

Phase 6: Stream and photo configuration
- Theory: docs define resolution, frame-rate, codec, and photo capture format; current app likely uses defaults without explicit contract.
- Add tests documenting chosen defaults:
  - videoCodec
  - resolution
  - frameRate
  - photo format
- If UI should expose choices, add l10n-backed controls.
- Otherwise document fixed defaults in code comments and contract tests.

Phase 7: MockDeviceKit harness
- Theory: static contract tests prove wiring, not real plugin behavior.
- Add a debug/test-only path using plugin mock APIs:
  - enableMockDevice
  - pairMockRayBanMeta
  - mockPowerOn
  - mockUnfold
  - mockDon
  - setMockPermission
  - setMockCapturedImage
  - capturePhoto
- Add a focused integration/smoke command that proves:
  - device appears
  - permission granted
  - stream/photo path starts
  - captured image reaches provider queue or CaptureController.ingestCapturedImage
- Keep production behavior isolated from mock-only hooks.

Phase 8: Flutter UI proof
- Run flutter analyze on touched files.
- Run flutter test for focused contracts and any new unit/integration tests.
- For Flutter UI changes, use agent-flutter:
  - hot restart if app already running
  - connect
  - snapshot
  - interact with Meta glasses page/devices page
  - screenshot evidence

Phase 9: iOS build and real-device proof
- Run scripts/repair_flutter_spm_ios_target.sh before iOS build if needed.
- Build iOS dev/Profile with CODE_SIGNING_ALLOWED=NO first.
- Only after tests/analyzer/build pass, install on EddyPhone.
- Launch with console capture.
- Verify:
  - app launches
  - Meta registration callback completes
  - linked glasses appear
  - permission flow surfaces correct state
  - manual capture path works or fails with documented hardware limitation
  - no previous symptom regresses

Minimum verification commands:
- cd app && dart format --line-length 120 <touched dart files>
- cd app && flutter analyze <touched dart files>
- cd app && flutter test test/unit/omi4meta_reconstruction_contract_test.dart
- cd app && flutter test <new focused tests>
- cd app && ./scripts/repair_flutter_spm_ios_target.sh
- cd app && xcodebuild -workspace ios/Runner.xcworkspace -scheme dev -configuration Profile-dev -destination 'generic/platform=iOS' -derivedDataPath /tmp/omi4meta-dat-full-dd CODE_SIGNING_ALLOWED=NO COMPILER_INDEX_STORE_ENABLE=NO build

Expected final deliverables:
- Code changes for the gaps above.
- New/updated tests that fail without the fixes.
- Updated gap analysis marking completed and remaining items.
- Real proof summary with exact commands and outcomes.
- No PR/push unless user explicitly asks.
```

