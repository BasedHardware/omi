# Operator-authorized iPhone permission automation

This XCUITest runner changes Omi Mic Probe's Microphone and Bluetooth
switches. It opens that probe's own Settings URL, locates the named controls,
taps their trailing toggles, and waits for the requested value. A centre tap
hits the label area on iOS 27 and leaves the value unchanged; the assertion
must fail in that case. It never changes the user's ordinary Omi permissions.

Use only during an active, explicitly authorized physical-phone session.
An unlocked paired phone and development signing are required. Never add a
personal phone to the unattended dedicated-device registry for this purpose.
The XCTest host is another separate diagnostic app, not the Omi product.

Generate outside Git (requires XcodeGen):

```bash
python3 app/ios/test/phone_probe_ui/prepare.py --output /absolute/fresh/ui-project
xcodebuild build-for-testing \
  -project /absolute/fresh/ui-project/OmiProbePermissions.xcodeproj \
  -scheme ProbePermissions -configuration Debug -sdk iphoneos \
  -destination 'generic/platform=iOS' \
  -derivedDataPath /absolute/fresh/ui-project/build \
  DEVELOPMENT_TEAM='<authorized team>' CODE_SIGN_STYLE=Automatic \
  CODE_SIGN_IDENTITY='Apple Development'
```

This uses an already available Xcode-managed development profile; do not add
provisioning-update flags or silently switch Apple teams when signing fails.
Keep generated projects, signed binaries, logs, and result bundles outside Git.

With the updated probe installed, first run the read-only inspection:

```bash
xcodebuild test-without-building -xctestrun /absolute/path/to/generated.xctestrun \
  -destination 'platform=iOS,id=<authorized device>' \
  -only-testing:ProbePermissionTests/PermissionTests/testInspectSettings \
  -collect-test-diagnostics never -resultBundlePath /absolute/fresh/inspect.xcresult
```

Select `testDenyMicrophone` and `testDenyBluetooth` next, collect completed
denied microphone/BLE probe traces, then select `testRestoreMicrophone` and
`testRestoreBluetooth`. Always restore both grants before ending the session,
including after a failed attempt. Each XCTest step verifies the switch only;
the probe's paired-trace analyzers independently verify actual denied capture
and successful capture after restoration. Do not count a settings tap as
permission-recovery evidence.

Other explicitly selected helpers are `testStopWearable`, `testStopMicrophone`,
`testApproveInterrupterMicrophone`, and `testApproveCapturePrompts`. The consent
helpers restrict the app identity and permission type to the separate diagnostic
apps. The interrupter helper expects its initial microphone prompt; do not repeat
it after permission has already been granted. `testSiriInterruption` submits an
arithmetic text request to Siri; this alone does not prove audio interruption.
Only a probe trace containing the actual interruption and resumed frames can
qualify recovery.

`testApproveWearableCapturePrompts` handles the separate wearable qualification
bundle. Both capture consent helpers activate an existing process so a host
console session can remain attached. `testInspectCapture` prints only the
qualification app's accessibility tree and attaches its screenshot after the app-switch
animation settles for startup diagnosis; it makes no
product acceptance assertion.

Each test returns to the separate permission host. While foreground, that host
disables its idle timer to reduce repeated unlock requests; it changes no iOS
auto-lock setting. Close the host at the end of the physical session. Other apps
foregrounded during a run may still permit the screen to lock.

Use `-collect-test-diagnostics never` to avoid whole-device diagnostic capture.
Do not run this device-only suite in ordinary hermetic Flutter tests or CI.
No phone is needed for the probe analyzers and native policy replay documented
in [the microphone guide](../phone_mic_probe/README.md).
