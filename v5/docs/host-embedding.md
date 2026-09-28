# v5 runtime inside the shipping Mac app (B2 development spike)

The shipping SwiftPM app keeps `DesktopHomeView` and its signed-in startup, auth,
notification, capture, floating bar, and sign-out lifecycle. When a development
build contains `OmiV5Runtime.xcframework` and the local `omi.v5ui.localOverride`
preference is true, only the signed-in product content becomes the React Native
root. The framework is generated locally and ignored by Git. Release packaging
and cohort flag delivery belong to B2b/B5.

## Build and packaging measurements

| Measurement | Result | Command / evidence |
| --- | --- | --- |
| JSC framework build (arm64 and x86_64) | Pass, 57 s warm build; 40,570,880 bytes XCFramework | `v5/react-native/scripts/build-host-framework.sh`; `/tmp/v5-host-framework-final2.log`. Both slices built separately, then combined with `lipo` into a universal framework. |
| SwiftPM, framework absent | Pass, 74.29 s | `xcrun swift build -c debug --package-path desktop/macos/Desktop`; `/tmp/v5-host-swift-without.log` |
| SwiftPM, framework present | Pass, 7.37 s incremental; `V5HostKit` compiled and executable linked | Same command after framework generation; `/tmp/v5-host-swift-with-final.log` |
| App bundle payload delta | Calculated +33,464,849 bytes (+31.9 MiB) | Debug host executable without framework: 261,564,208 bytes; with framework: 254,510,176 bytes. The added universal framework file payload is 40,518,881 bytes. This is a `run.sh`-equivalent unsigned bundle calculation; a fully assembled or signed app was not measured. |
| Exported symbols | Pass, exactly 2 global exports: `OmiV5Host` class and metaclass | `nm -gU <slice>/OmiV5Runtime.framework/OmiV5Runtime` on the universal slice. The three ObjC protocols are declared in the public module header; a Swift import/conformance link probe passed. |
| Duplicate symbol warnings | 0 | Searched both arch `xcodebuild` logs and the SwiftPM link log for `duplicate symbol`. A duplicate `-rpath` warning in a Swift test link is unrelated to runtime symbol exports. |

`OmiV5Host` is the only public class. Its three protocols are declared for B3
provider registration. Registration is intentionally inert in B2; authenticated
reads remain disabled in JS host mode until B3 connects the shipping session.
The same gate disables v5 Rewind capture and ambient audio. The standalone v5
app continues to use its existing native session and capture path.

## GUI acceptance runbook for the orchestrator and David

This lane cannot launch the GUI or sign in. These steps require a GUI session.
Use a named development bundle and the host's real session only through the
normal app UI. Do not use `?rig=dev` or tooling requests to any `omi.me` host.

1. Build the runtime and host bundle using `cd desktop/macos && OMI_APP_NAME=omi-v5-host OMI_V5_HOST=1 OMI_SKIP_BACKEND=1 OMI_SKIP_TUNNEL=1 ./run.sh --full`. This command **launches the GUI**. Set `omi.v5ui.localOverride` to true in the named bundle's defaults domain, then relaunch. Inspect the bundle ID with `defaults read /Applications/omi-v5-host.app/Contents/Info CFBundleIdentifier` before writing the domain. Capture a screenshot with `screencapture -x -o /tmp/omi-v5-host.png` and record its path below. Confirm Activity fills the signed-in region, while onboarding and sign-in still come from the Swift host.
2. For classic, set the same preference false, quit, and relaunch the same bundle. Record three cold-launch intervals from `open -n /Applications/omi-v5-host.app` until the first visible content frame. Repeat three times with the override true. Use a screen recording or timestamped screenshots at the display refresh rate; report the mean and each raw interval. The root creation log is only a bootstrap marker, not proof that the frame was painted.
3. After each variant idles for 60 seconds, find the PID using `pgrep -fl '/Applications/omi-v5-host.app/Contents/MacOS/Omi Computer'`, then run `ps -o pid=,rss= -p <PID>`. Record RSS in KiB and the difference. Use the same account and window size.
4. In v5, click an Activity row, scroll the list, resize, drag, and toggle fullscreen. Record whether input and host window behavior work, plus any visible glitches.
5. For hardened-runtime JSC, sign a **development** copy with `codesign --force --deep --options runtime --entitlements desktop/macos/Desktop/Omi-Release.entitlements --sign - <path-to-dev-app>`; verify with `codesign -dv --verbose=4 <path-to-dev-app> 2>&1` and `codesign -d --entitlements :- <path-to-dev-app>`. Confirm App Sandbox is on and `allow-jit` absent. Launch this signed development copy, time one full Activity list scroll and one chat render, and inspect its unified logs with `log show --last 10m --style compact --predicate 'process == "Omi Computer"'` for JavaScriptCore JIT messages. Record an explicit `JIT active`, `JIT inactive`, or `unknown`; elapsed time alone cannot prove JIT state. Compare with the regular development build. Do not add `allow-jit` in this lane.
6. If JSC performance fails, measure a separate Hermes framework build with `:hermes_enabled => true` in a disposable copy of the Podfile. Record the `hermes.framework` bundle increase and bytecode compilation of `main.jsbundle` before proposing a change to the main branch.

### GUI results to fill

| Metric | Classic | v5 | Notes |
| --- | --- | --- | --- |
| Cold launch → first content frame, runs 1/2/3 | Not measured (needs GUI session) | Not measured (needs GUI session) | |
| RSS after 60 s idle (KiB) | Not measured (needs GUI session) | Not measured (needs GUI session) | |
| Click and scroll | Not measured (needs GUI session) | Not measured (needs GUI session) | |
| Drag, resize, fullscreen | Not measured (needs GUI session) | Not measured (needs GUI session) | |
| Hardened sandbox JSC, scroll and chat render | Not measured (needs GUI session) | Not measured (needs GUI session) | |
| JSC JIT state | Not measured (needs GUI session) | Not measured (needs GUI session) | |
| Screenshot path | Not measured (needs GUI session) | Not measured (needs GUI session) | |
