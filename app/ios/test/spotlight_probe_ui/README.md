# iOS Spotlight simulator probe

This optional XCUITest drives system Spotlight for the synthetic items indexed by
`-omi-siri-probe-spotlight`. It is not part of required CI. Use Xcode 27 and an
iOS 27 simulator. The probe app uses an isolated bundle ID and a loopback-only
fake session; it never signs in or writes account data.

Build the Runner `dev` scheme with `OMI_SIRI_PROBE` in
`SWIFT_ACTIVE_COMPILATION_CONDITIONS`, `APP_BUNDLE_IDENTIFIER=com.omi.spotlightprobe`,
and `CODE_SIGNING_ALLOWED=NO`. Install its `Runner.app`, then launch it with
`xcrun simctl launch booted com.omi.spotlightprobe -omi-siri-probe-spotlight`.
Wait for `[SiriSceneProbe] syntheticIndex=ready` and a nonzero
`syntheticQueryCount` before testing.

Generate the external UI test project with:

```bash
ruby app/ios/test/spotlight_probe_ui/prepare.rb /tmp/omi-spotlight-ui
xcodebuild build-for-testing -project /tmp/omi-spotlight-ui/SpotlightProbe.xcodeproj \
  -scheme SpotlightProbe -destination 'platform=iOS Simulator,id=<UDID>' \
  -derivedDataPath /tmp/omi-spotlight-ui-build ARCHS=arm64 ONLY_ACTIVE_ARCH=YES
```

Run `test-without-building` with the generated `.xctestrun` twice: once with
the probe app in the background, then after ending the probe app process by
PID. The test presses Home, opens system Search, enters `Spotlight`, and taps
the synthetic conversation result. Inspect `[SiriSceneProbe]` logs for the
intent and scene activity delivery. A `CSSearchQuery` count proves the item is
indexed but does not prove system Search displays it. If the result is absent,
the test fails at that assertion and no tap-path claim is justified.
