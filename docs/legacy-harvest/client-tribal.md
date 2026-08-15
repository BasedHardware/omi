# Client tribal harvest

Analysis lane. Harvest pin: `BasedHardware/omi` `3f5bbcdbc00a48b97e6bc78ffa31a187bd9a5e0e`
(`origin/main` at 2026-08-15 02:36:20 -0400, the brief's freshness). Native clients
and the physical world only. Sibling `legacy-fix-harvest` owns backend/domain
logic. This file proposes ports; it does not change product code.

Ledger rows in `docs/legacy-ledger.md` were not reopened.

Do-not-port (David, screen domain, applied as judgement everywhere): no
`lsregister`/`tccutil`/`sh` self-surgery; no private AX; no macOS 13
`screencapture` CLI fallback; no ffmpeg subprocess; no dead battery-OCR; no
lying `isIndexed`; no server-side OCR truncate-while-embedding-full; no
hard-coded per-frame duration; no 3450-line kitchen-sink modules; no
`nonisolated(unsafe)` statics with hand-rolled locks; no three `processFrame`
overloads; no PTS from a frozen frame rate.

## Contents

| ID | Rule | Verdict | Risk |
| --- | --- | --- | --- |
| T-TCC-FRONTMOST | Request Screen Recording (and Microphone) TCC only while the app is frontmost, then open Settings | mixed: screen `HONORED`, mic `VIOLATED` | high |
| T-TCC-RELAUNCH | A Screen Recording grant does not apply to this process until relaunch | `VIOLATED` | high |
| T-PERM-BADGE | Permission badge mirrors `CGPreflightScreenCaptureAccess` only; engine failures never look like denial | `HONORED` | high |
| T-INT-NAN | Refuse zero-area window frames; `Int(NaN)` traps | `HONORED` (filter) / gap: no testable function | high |
| T-A2DP-ENGINE | Do not capture through `AVAudioEngine` on macOS; it builds an implicit aggregate and flips Bluetooth A2DP→SCO | `VIOLATED` | high |
| T-402-RETRY | HTTP 402 / Payment Required is never retryable; match status shape, not the digits `402` | `VIOLATED` | high |
| T-SSE-AFTER-DONE | Reject provider bytes after the terminal SSE marker; do not apply late tokens to a finished turn | `HONORED` | high |
| T-KEYCHAIN-DP | Never opt into the data-protection keychain on a non-sandboxed Developer ID app | `HONORED` | high |
| T-CONVERTER | Reuse one `AVAudioConverter`; never `.endOfStream` mid-stream; hand each buffer once | `HONORED` | high |
| T-PHONEMIC | iOS capture must self-heal interruption / route / media-reset; declined calls never deliver `.ended` (#6499) | `NOT-APPLICABLE` | high |
| T-SCSHAREABLE | Cache `SCShareableContent`; enumerating every tick stalls the WindowServer | `VIOLATED` | medium |
| T-SAMPLE-FINITE | Reject non-finite hardware sample rates (`Inf > 0` is true) | `VIOLATED` | medium |
| T-SIGPIPE | Ignore `SIGPIPE` so a dead pipe is an error, not a process kill | `VIOLATED` | medium |
| T-CADENCE | Screen cadence constants (heartbeat, battery ×3, dHash, idle, sharing backoff, OCR every 3rd) | `HONORED` | medium |
| T-PRIME-CONSENT | Prime SCK with a real 2×2 `captureImage`; enumerating content does not show the consent sheet | `HONORED` | medium |
| T-WKSCHEME-STOP | Never `didReceive`/`didFinish` a `WKURLSchemeTask` after `stop` | `HONORED` | medium |
| T-DMG | Running from a DMG / App Translocation path makes TCC grants not stick | `NOT-APPLICABLE` | high |
| T-SETICON | Never `NSWorkspace.setIcon(forFile:)` on the `.app` bundle | `NOT-APPLICABLE` | high |
| T-COREAUDIO-UID | Identify capture devices by UID; CoreAudio numeric IDs change on reconnect | `NOT-APPLICABLE` | high |
| T-BLE-FINALIZE | Finalize the in-progress BLE batch on disconnect; a drop never delivers another packet | `NOT-APPLICABLE` | medium |
| T-SPARKLE-26 | macOS 26 launchd on-demand-only can leave Sparkle installer jobs unstarted | `NOT-APPLICABLE` | medium |
| T-BETA-SIDECAR | Beta is a distinct bundle id (own TCC/Keychain/defaults); stable must never consume the beta Sparkle channel | `NOT-APPLICABLE` | medium |
| T-WINDOW-CACHE | 500 ms window-resolve timeout + 2 s last-known-good cache; never poison the cache with a nil window ID | `VIOLATED` | medium |

---

## T-TCC-FRONTMOST — request TCC while frontmost, then open Settings

### Legacy evidence

`desktop/macos/Desktop/Sources/ScreenCaptureService.swift` 233–240, 267–281
(`e4c4286cdf0631fad2600bb2aad5b57447cb78df`, 2026-07-07, "register
screen-recording TCC row while frontmost, then open Settings"):

```
// Activate first so the request fires while Omi is frontmost. A
// screen-capture access request from a backgrounded app does not reliably
// register the kTCCServiceScreenCapture row
NSApp.activate()
CGRequestScreenCaptureAccess()
```

Opening Settings first backgrounded the app, so the registering call never
created the row and Omi never appeared in the list (PERM-02 / BL-050).
Microphone follows the same activate-before-request rule
(`AppState+SystemActions.swift` 21–26). Already-denied microphone must not call
`requestAccess` (it returns false with no prompt).

Soft recovery via `lsregister` / `tccutil` is diagnosis only — do not port the
shelling.

### The rule

Request Screen Recording and Microphone TCC only while the window is frontmost.
If the user must visit System Settings, register the TCC row first, then open
the pane. If status is already denied, open Settings; do not call `requestAccess`.

### Whether our code honors it

**Screen: `HONORED`.** `frontend/shells/macos/shell/Sources/OmiShell/ScreenCapture.swift`
114–118 activates, then `CGRequestScreenCaptureAccess()`. The composition
harness calls `screen.requestPermission` before `screen.openSettings`
(`frontend/shells/macos/tests/screen-bridge-composition.test.mjs` 114–117).
`requestPermission` does not itself open Settings (legacy combined them); two
UI buttons can still invert the order. Keep the combined helper as the port.

**Microphone: `VIOLATED` (reading).** `ListenSocket.swift` 263–275 calls
`AVCaptureDevice.requestAccess` with no `NSApp.activate()`. It does honor the
denied-no-prompt half (only `.notDetermined`).

```
frontend/shells/macos/shell/Sources/OmiShell/ListenSocket.swift:270:
          AVCaptureDevice.requestAccess(for: .audio) { ... }
frontend/shells/macos/shell/Sources/OmiShell/ScreenCapture.swift:115:
    NSApp.activate()
```

TCC prompt appearance could not be exercised here (no interactive grant).

### Port

One function `requestTccWhileFrontmost(_ service)` that activates, then
requests. A test that the microphone path calls it. Do not port `lsregister`.

---

## T-TCC-RELAUNCH — grant applies at next process launch

### Legacy evidence

`ScreenRecordingPermissionPolicy.swift` (whole file) and `AppState.swift`
370–373 (`6aaec52a0aea19b8a8a67c36941b69eda91df16f`, 2026-07-16):

```
/// A screen-recording grant only takes effect at process launch (the window
/// server evaluates it once per connection). Granted now but not at launch
/// means capture stays dead until the app relaunches
static func needsRelaunchToApply(grantedNow: Bool, grantedAtLaunch: Bool) -> Bool {
  grantedNow && !grantedAtLaunch
}
```

Offer "Reopen" exactly once in that case. An app that already relaunched after
the grant must never be asked again.

### The rule

Capture `CGPreflightScreenCaptureAccess()` once at launch. If a later preflight
is true and the launch snapshot was false, offer relaunch; do not start SCK in
the still-unauthorized process and call that success.

### Whether our code honors it

**`VIOLATED` (reading).** `ScreenCaptureEngine.requestPermission` (ScreenCapture.swift
300–307) requests, primes consent, and returns. `start()` treats a live
preflight as enough to enter `.recording`. No `grantedAtLaunch`, no
`needsRelaunchToApply`.

```
rg -n "needsRelaunch|grantedAtLaunch|relaunchToApply" frontend/shells
# (no matches)
```

Could not flip TCC in this environment.

### Port

Two booleans and the three-line predicate above, plus a unit test of the truth
table. The rewrite already maps engine failure away from denied (T-PERM-BADGE);
this is the missing relaunch half.

---

## T-PERM-BADGE — badge is TCC preflight, not the capture engine

### Legacy evidence

`ScreenRecordingPermissionPolicy.swift` 2–12; `ScreenCaptureService.swift`
86–91 (`do not spawn /usr/sbin/screencapture` — the helper failed for reasons
unrelated to this app's grant and painted a red "disabled" while Settings
showed allowed). `AppState.swift` 382: `isScreenCaptureKitBroken` is "not the
source of permission truth".

### The rule

UI permission state is `CGPreflightScreenCaptureAccess()` only. SCK enumeration
failure is a capture-engine diagnostic.

### Whether our code honors it

**`HONORED` (ran).** `ScreenPermissionPolicy.map` / `engineFailureNeverDenied`
in `ScreenPolicy.swift` 89–101. `node --test frontend/shells/macos/tests/screen-policy.test.mjs`:

```
ok 1 - screen cadence, dHash, Hamming, fence, ingest cursor, permission, retention are pure and testable
# tests 1
# fail 0
```

The harness asserts `perm-engine-failure-not-denied`. Do not port the
`screencapture` CLI probe (do-not-port list).

### Port

None. Keep the existing test.

---

## T-INT-NAN — zero-area frames must not reach `Int(NaN)`

### Legacy evidence

`ScreenCaptureService.swift` 862–872
(`1bc1327994cf584539ef4e8f89fa69b27ffec4e1`, 2026-07-14, #9659) and
`ScreenCaptureDimensionsTests.swift` 7–11, 35–37:

```
/// A zero-width frame makes aspectRatio 0, so configWidth / aspectRatio is
/// NaN (0/0). NaN fails every comparison, so the > maxSize clamp does not fire
/// and Int(NaN) traps — an uncatchable crash
guard width > 0, height > 0 else { return nil }
```

### The rule

Sizing is a pure function that returns nil for non-positive dimensions. Never
inline `Int(width * scale)` on a frame that might be degenerate.

### Whether our code honors it

**`HONORED` for the crash, gap for the testable function.**
`ScreenCaptureKitSource.captureFocused` keeps windows with
`frame.width > 0 && frame.height > 0` (ScreenCapture.swift 50). There is no
`captureDimensions` and no Swift test of the NaN case.

Measured (scratch `/tmp`, not the worktree):

```
OK: inf-gt-zero
OK: nan-gt-zero-is-false
OK: zero-width-nil
OK: nan-width-nil
OK: normal-1440x900
# unguarded Int(NaN) helper:
nan-trap-exit=133
```

133 is SIGTRAP. `width > 0` also rejects NaN, which is why the filter works.

### Port

Lift the legacy pure function (not the 3450-line service) into ScreenPolicy.swift
and port `ScreenCaptureDimensionsTests` as a swiftc harness like
`screen-policy.test.mjs`.

---

## T-A2DP-ENGINE — `AVAudioEngine` degrades Bluetooth output

### Legacy evidence

`desktop/macos/Desktop/Sources/AudioCaptureService.swift` 5–8, 13–14:

```
/// Uses CoreAudio IOProc directly on the default input device to avoid
/// AVAudioEngine's implicit aggregate device creation, which degrades
/// system audio output quality (especially Bluetooth A2DP → SCO switch).
/// A currently available CoreAudio input device. `uid` stays stable when
/// CoreAudio assigns a different numeric device ID after reconnecting it.
```

Silent Bluetooth input after A2DP/HFP conflict is a second learned failure
(same file, silent-mic watchdog). Preferred-mic reconnect must key on UID
(`PreferredMicrophoneReconnect.swift`, #10921).

### The rule

macOS listen capture opens a CoreAudio IOProc on a UID-stable device. Do not
install an `AVAudioEngine` tap on the default input. Pin preferred devices by
UID, not `AudioDeviceID`.

### Whether our code honors it

**`VIOLATED` (reading; Bluetooth hardware not available).**
`ListenMicrophoneCapture` is an `AVAudioEngine` tap
(ListenCapture.swift 91–113). No CoreAudio IOProc, no UID.

```
rg -n "AVAudioEngine|AudioDeviceIOProc|IOProc" \
  frontend/shells/macos/shell/Sources/OmiShell/ListenCapture.swift
92:  private let engine = AVAudioEngine()
```

Named gap: reproducing A2DP→SCO needs a Bluetooth headset. The rewrite has
never seen that failure mode.

### Port

A small CoreAudio input actor (UID + IOProc + 16 kHz PCM16 chunks), not the
legacy 1100-line service. Tests: UID identity across fake reconnect; silent-mic
policy table. Do not port `nonisolated(unsafe)` listener state.

---

## T-402-RETRY — Payment Required is never retryable

### Legacy evidence

`desktop/macos/Desktop/Sources/Chat/AgentErrorClassifier.swift` 114–132
(`8c2bf23e90c2c40b0e97cd3b5e6e2594b9c17e77`, 2026-08-07, plus
`0a8d0ffe98af9e6e82379701884e27c8b5cd3717`, 2026-08-13):

```
// The Omi-account proxy answers an exhausted billing lane with a bare 402
// and no body, so the raw transport string ("HTTP 402 status code (no
// body)") fell through to `unknown` and was shown verbatim — and, worse,
// marked retryable, which is the retry storm this classifier exists to
// prevent. Payment Required is never fixed by resending the same message.
// Matched on status shape rather than a bare `402` so a token count or cost
// that happens to contain those digits cannot claim this rule.
```

Flutter voice SSE (`app/lib/backend/http/api/messages.dart` 100–105) never
surfaces a malformed `error:` frame; quota keeps the legacy `error:402:` shape.

### The rule

Classify HTTP 402 / "Payment Required" / "402 status" as non-retryable billing.
Do not match the substring `402` inside token counts. Do not retry the same
message.

### Whether our code honors it

**`VIOLATED` (ran).** `apps/service/chat` has no `402` / payment-required
classifier. Gateway failures after a terminal marker are `retryable: true`
(`generation-gateway-source.test.ts`).

```
rg 402 apps/service/chat
# No matches found
```

### Port

A pure classifier on the gateway error string + HTTP status, with fixtures
`HTTP 402 status code (no body)` → not retryable and `used 4020 tokens` → not
billing. Do not port the 160-line desktop classifier.

---

## T-SSE-AFTER-DONE — nothing after the terminal marker is a token

### Legacy evidence

`ChatTurnLifecycle.swift` 115–123: claiming terminalization is synchronous so
a later streaming callback cannot enqueue after ownership is taken; a
supersedable `status: .streaming` flush after the terminal mutation would
regress the turn. `ChatStreamingBuffer.swift` 39–41: discard only the revoked
turn's deltas, or a newer turn loses tokens / applies late output.

### The rule

After the provider's terminal marker (or the user stop), further bytes are not
content. Late flushes must not reopen a terminalized turn.

### Whether our code honors it

**`HONORED` (ran)** on the gateway:

```
bun test apps/service/chat/generation-gateway-source.test.ts
  14 pass
  0 fail
```

That file includes `rejects gateway data after the terminal SSE marker` and
`rejects an unterminated gateway fragment after the terminal SSE marker`.
macOS `ChatStream.swift` 91–109 is a strict incremental UTF-8 decoder (no
replacement characters). `node --test frontend/shells/macos/tests/chat-stream-host.test.mjs`
passed (`Last-Event-ID` replay included).

### Port

None for the gateway. When a desktop token buffer exists, port
`discardPendingSegments(messageId:)` as a one-function test, not the buffer
module.

---

## T-KEYCHAIN-DP — file-based keychain, never data-protection

### Legacy evidence

`DesktopKeychainStore.swift` 7–18, 57–64
(`7416458d2b4a2030a672d1c5c243a382cc81ff37`, 2026-07-06;
`58a6308d2063e6ed0cb1303c81e83e001455bcb6`, 2026-07-08, #9167 / #9283):

```
/// Never opt into the data-protection keychain (`kSecUseDataProtectionKeychain`)
/// — this non-sandboxed Developer ID app has no `keychain-access-groups`
/// entitlement.
/// On the signed/notarized build that made every SecItem write fail with
/// errSecMissingEntitlement (-34018), so token storage failed
```

Also: never query pre-scoping legacy service names (foreign-team ACL still
raises the login-keychain password sheet despite `interactionNotAllowed`).
Scope service names by Team ID **and** bundle id so Apple Development / named
bundles cannot poison notarized Beta/Prod.

### The rule

Generic-password items, file-based keychain, silent `LAContext`, team+bundle
service name. Fail closed rather than prompt on the launch path.

### Whether our code honors it

**`HONORED` for -34018 and launch-path silence.**
`Credentials.swift` never sets `kSecUseDataProtectionKeychain`, uses
`interactionNotAllowed`, and bounds the launch read at 2 s
(Credentials.swift 58–96, 292–352).

```
rg -n "kSecUseDataProtectionKeychain" frontend/shells
# (no matches)
```

Team+bundle scoping is **not** present (scratch service name). That is a
shipping-identity gap, not a prototype defect — queue it with packaging
(T-BETA-SIDECAR).

### Port

When the shell ships a Developer ID identity: `scopedService` + a test that the
query dict has no `kSecUseDataProtectionKeychain`. Keep the 2 s deadline.

---

## T-CONVERTER — resampler state, no `.endOfStream`, one-shot input

### Legacy evidence

`app/ios/Runner/PhoneMic/PhoneMicConverterPipeline.swift` 6–13, 55–78
(`babb0d51c784dd1d21612c41cea0dc10155e67e4`, 2026-07-10):

```
/// AVAudioConverter's resampler carries fractional-phase state between calls,
/// which is what keeps non-integer ratios (44.1k -> 16k) artifact- and
/// drift-free. Recreating the converter per buffer resets that state
/// +64 frames of headroom absorbs the resampler's internal-buffer flush
/// Hand the buffer to the converter exactly once — the input block can be
/// called multiple times per convert(), and re-returning the same buffer
/// duplicates audio.
/// .noDataNow, never .endOfStream: endOfStream permanently finalizes the
/// converter mid-stream.
```

Installing a tap over an existing tap crashes (`PhoneMicCaptureEngine.swift`
54). CoreAudio may reuse the tap buffer the moment the block returns — copy
before any async hop (same file 60–61).

### The rule

One converter per route generation. `noDataNow` after the first input. Headroom
on the output buffer. `removeTap` before `installTap`. Copy or fully consume
the tap buffer before returning.

### Whether our code honors it

**`HONORED` (ran + reading).** `ListenMicrophoneCapture.start` builds one
converter; `ListenPcm16.convert` uses a `submitted` flag and `.noDataNow`
(ListenCapture.swift 48–57). `start()` calls `stop()` first, which `removeTap`s.
Convert runs on the tap thread (no async hop of the live buffer).
`node --test frontend/shells/macos/tests/listen-socket-composition.test.mjs`
passed, including `CHUNK-BYTES=3200` and 48 kHz→16 kHz resample bounds.

Gap: output headroom is `+32` frames, not `+64`. Whether 32 is enough is
`COULD-NOT-DETERMINE` without a 44.1 kHz hardware device. Port the +64 comment
and constant.

Format-drift (buffer format ≠ converter input) is not checked. That matters
once T-A2DP-ENGINE / route changes exist.

### Port

`+64` with the flush comment; a `formatDrift` guard when a route observer
exists. Do not port the iOS opus/batch stack.

---

## T-PHONEMIC — iOS interruption / route / media-reset

### Legacy evidence

`PhoneMicInterruptionMonitor.swift` 17–23, 31–34, 75–78 and
`PhoneMicController.swift` 327–347, 364–366
(`83c5493b5f694dea97576bd8fb0a47912f9c7a31`, 2026-04-12, #6499;
`e7bb7e9b229bd1ed41086c407979207f8fa1d7d5`, 2026-08-06, #4706):

```
/// From CXCallObserver: covers the declined-call case where the
/// interruption .ended notification is never delivered (issue #6499).
/// #4706: with .mixWithOthers, competing audio can stop the engine
/// without an interruption notification. Foreground return must
/// heal a zombie "still Listening" session.
```

Session rules (`PhoneMicSessionConfigurator.swift`): never deactivate a shared
session; no `setPreferredSampleRate` (fight the OS across route changes);
`.mixWithOthers` so recording does not stop music; `.defaultToSpeaker` so
later playback is not the earpiece. Opus: `discardPartial()` on teardown so
pre- and post-interruption audio is never spliced across one frame.

Bring-up retry: 0.35 s, max 2; resume ticker 3 s.

### The rule

Native capture owns recovery. Dart does not restart the engine. Resume without
the OS `shouldResume` bit is allowed to *probe* (YouTube / Stage Manager never
set it) but must stay silent on failure. Rebuild the engine on route /
config-change / `mediaserverd` reset. Keep the encoder across rebuilds; drop
the sub-frame remainder.

### Whether our code honors it

**`NOT-APPLICABLE`.** The rewrite iOS shell (`AppDelegate.swift`) does listen
preflight and `requestRecordPermission` only. There is no `AVAudioEngine`
capture, no interruption observer, no session configurator.

```
rg -n "interruptionNotification|routeChangeNotification" frontend/shells
# (no matches)
```

### Port

When iOS listen capture exists: the monitor's typed events + the controller's
state machine as tests (declined-call → `allCallsEnded`; foreground + dead
engine → rebuild). Do not port Pigeon or the 480-line controller as a unit.

---

## T-SCSHAREABLE — do not enumerate every window every tick

### Legacy evidence

`ScreenCaptureService.swift` 47–56 (TTL 5.0 s):

```
/// SCShareableContent.excludingDesktopWindows enumerates every on-screen window
/// through the WindowServer; calling it every 3 seconds contends with other
/// screen-capture apps (CleanShot, Zoom share, Loom, etc.) and causes UI stalls.
```

Legacy poll is ~1 s with a 5 s cache. Rewrite poll is 1 s with **no** cache.

### The rule

Reuse a recent `SCShareableContent` snapshot (TTL on the order of seconds).
Force-refresh when the target window is missing. Actor-isolated, not a
`nonisolated(unsafe)` static + `NSLock`.

### Whether our code honors it

**`VIOLATED` (reading).** `captureFocused` and `primeConsent` both await
`SCShareableContent.excludingDesktopWindows` with no TTL
(ScreenCapture.swift 38–39, 75–76). The run loop sleeps 1 s
(ScreenCapture.swift 397). WindowServer stall needs concurrent capture apps —
named hardware gap.

### Port

A 5 s cache on `ScreenCaptureEngine` (already an actor). Refresh on miss.
Do not port the static lock.

---

## T-SAMPLE-FINITE — `Inf > 0` is not a valid sample rate

### Legacy evidence

`PhoneMicCaptureEngine.swift` 47:
`inputFormat.channelCount > 0, inputFormat.sampleRate > 0, inputFormat.sampleRate.isFinite`.

### The rule

Treat non-finite or non-positive hardware formats as "no input", not as a
converter source.

### Whether our code honors it

**`VIOLATED` (ran).** ListenCapture.swift 105:

```
guard hardwareFormat.sampleRate > 0, hardwareFormat.channelCount > 0 else { return false }
```

Measured:

```
OK: inf-gt-zero
OK: listen-guard-inf-would-pass-gt-zero
OK: inf-is-not-finite
```

A `+Inf` rate passes the rewrite guard.

### Port

Add `.isFinite` to the existing guard; one swiftc assertion. Tiny.

---

## T-SIGPIPE — dead pipes must not kill the process

### Legacy evidence

`OmiApp.swift` 307–308:

```
// Ignore SIGPIPE so broken-pipe writes return errors instead of crashing the app.
// Without this, writing to a dead FFmpeg stdin or agent-bridge pipe kills the process.
signal(SIGPIPE, SIG_IGN)
```

ffmpeg subprocess is do-not-port; the signal rule is independent (any pipe,
including a future agent stdio or a dropped WebSocket).

### The rule

Process-wide `signal(SIGPIPE, SIG_IGN)` at startup, before any I/O.

### Whether our code honors it

**`VIOLATED` (ran).**

```
rg -n "SIGPIPE" frontend/shells
# (no matches)
```

### Port

One line in `main.swift` with the comment. Do not port ffmpeg.

---

## T-CADENCE — load-bearing screen cadence

### Legacy evidence

Coordinator scout + `ScreenCaptureService` / rewind pipeline: 1 s poll; heartbeat
3 s default, ×3 on battery; dHash Hamming ≤5 stretches heartbeat ×2 and skips
OCR; idle ≥60 s (media exempt); sharing 10 s backoff; OCR at most every 3rd
frame; per-app overrides (Music 10 / Books 20 / TV 30); video-call 1-in-5;
anchor every 30 s; long edge 3000; retention invalid → unlimited.

A threshold without a reason is not in this list. These values exist because
the obvious ones (heartbeat=1 always, OCR every frame, no idle gate) burn
battery, OCR, and disk, or capture lock/loginwindow.

### The rule

Keep the constants with their reasons next to `ScreenCadencePolicy`.

### Whether our code honors it

**`HONORED` (ran).** `ScreenPolicy.swift` 245–315 and
`node --test frontend/shells/macos/tests/screen-policy.test.mjs` (fail 0),
including `battery-x3`, `dhash-static`, `idle-media-exempt`, `zoom-1-in-5`,
`ret-invalid` → 0.

### Port

None.

---

## T-PRIME-CONSENT — enumeration is not consent

### Legacy evidence

`ScreenCaptureService.swift` 285–306:

```
/// Enumerating shareable content (`SCShareableContent`) does NOT trigger this
/// consent — only an actual `SCScreenshotManager.captureImage` with an
/// app-built `SCContentFilter` does. So we do a minimal 2×2 display capture.
```

### The rule

After TCC is granted, fire a throwaway 2×2 `captureImage` during the permission
step so the SCK bypass-picker sheet appears in context, not on the first real
capture.

### Whether our code honors it

**`HONORED` (reading).** `ScreenCaptureKitSource.primeConsent` (ScreenCapture.swift
73–86) does a 2×2 `captureImage`. `requestPermission` awaits it after a grant
(303–305). Legacy filters a display; rewrite uses the first window — same
consent trigger. Could not show the sheet without TCC.

### Port

None. Keep the comment that enumeration is insufficient.

---

## T-WKSCHEME-STOP — WebKit crashes if a stopped scheme task completes

### Legacy evidence

Rewrite already carries the Apple forums thread 712430 comment. Included
because it is the same class of "OS crashes if…" knowledge, now on our tree.

`frontend/shells/ios/app/ios/Runner/AppDelegate.swift` 20–21, 101–118:

```
// Guard for the documented stop-race (forums thread 712430): WebKit crashes
// if didReceive/didFinish arrive after stopURLSchemeTask.
```

### The rule

After `stop`, drop all `didReceive` / `didFinish` for that task.

### Whether our code honors it

**`HONORED` (reading).** The `stopped` set is checked before every callback.

The SPIKE-ONLY `WKWebView` init swizzle in the same file is **not** tribal
capture knowledge; it is a known ship-blocker (ADR path is `OmiUiWebView`).
Do not treat the swizzle as something to port.

### Port

None for the stop-race. Replacing the swizzle is a sibling-owned iOS shell
task.

---

## T-DMG — translocation randomizes identity; TCC never sticks

### Legacy evidence

`desktop/macos/Desktop/Sources/Startup/AppInstaller.swift` 4–14
(`09afc8f06a9632f9f2e189f536d54f28494f9230`, 2026-07-07):

```
/// Running off the DMG is what produced the beta-user trio of bugs this fixes:
/// - App Translocation gives the bundle a randomized path/identity every launch,
///   so TCC grants (Screen Recording, System Audio) never stick
/// - Sparkle updates fail on the read-only volume.
```

Gate: only `/volumes/` and `/apptranslocation/`; never `~/Downloads` or dev
checkouts. Stop after two relaunch attempts. Never downgrade an installed build.

### The rule

If the bundle path is a mounted volume or App Translocation, copy to
`/Applications` and relaunch before any TCC request. Skip for named/dev
bundles.

### Whether our code honors it

**`NOT-APPLICABLE`.** The rewrite shell is an unsigned prototype, not a
notarized `.app` on a DMG. `rg` found no `AppTranslocation` / `/volumes/`
installer.

### Port

When packaging exists: the three predicates (`isInstallerLocation`,
`shouldReplaceInstalled`, relaunch-attempt cap) as tests. Do not port Finder
window choreography.

---

## T-SETICON — resource forks break the code signature

### Legacy evidence

`OmiApp.swift` 350–352:

```
// Do NOT call NSWorkspace.setIcon(forFile:) — it writes a resource fork onto
// the .app bundle, which breaks the code signature and prevents Sparkle
// auto-updates from working ("An error occurred while running the updater").
```

### The rule

Set `NSApp.applicationIconImage` in memory if you must. Never write an icon
into the bundle.

### Whether our code honors it

**`NOT-APPLICABLE`.** The prototype does not call `setIcon(forFile:)`.

### Port

A one-line comment next to any future Dock-icon code. A test that the shipping
target does not contain `setIcon(forFile`.

---

## T-COREAUDIO-UID — numeric device IDs are not identity

Covered under T-A2DP-ENGINE. Standalone so the next listen wave cannot miss it.

### Legacy evidence

`AudioCaptureService.swift` 13–14; `PreferredMicrophoneReconnect.swift` 4–26
(`3241e975ea9113b9464560d00a8a0d02f45d34c6`, 2026-07-23). Require
`isCaptureLive` so a HAL startup flap cannot restart into `stopCapture()` as a
no-op.

### Verdict

**`NOT-APPLICABLE`** until T-A2DP-ENGINE lands. Then it is mandatory.

---

## T-BLE-FINALIZE — disconnect never delivers the next packet

### Legacy evidence

`app/ios/Runner/Ble/OmiBleManager.swift` 650–652, 633–638:

```
// Finalize the in-progress batch recording so it's saved + ingestable right away
// (a plain BLE disconnect never delivers another packet to trigger the gap finalize).
OmiBatchAudioWriter.shared.stop("disconnected")
// Retry previously-connected peripherals — otherwise a failed connect silently
// drops the user. iOS queues this at the chipset level; it's free while waiting.
```

200 ms reconnect delay; skip auto-reconnect on manual disconnect and
`peerRemovedPairingInformation`.

### The rule

On `didDisconnectPeripheral`, finalize the open audio file immediately. Do not
wait for a gap timeout that will never fire.

### Whether our code honors it

**`NOT-APPLICABLE`.** No BLE stack in the rewrite shells.

### Port

When BLE lands: `onDisconnect → finalizeOpenBatch()` as a test with a fake
peripheral that never sends another packet. Do not port the manager.

---

## T-SPARKLE-26 — launchd on-demand-only vs installer jobs

### Legacy evidence

`UpdaterViewModel.swift` 582–593 (CHANGELOG: Sparkle 2.9.0 + kickstart for
macOS 26):

```
/// On macOS 26+, launchd may be in "on-demand-only mode" which prevents RunAtLoad
/// services from starting. We force-start them via launchctl kickstart as a backup
/// to Sparkle 2.9.0's built-in probe (PR #2852).
```

### The rule

Keep the diagnosis: Sparkle 2.9.0+ and its built-in probe. Do **not** port
`Process` + `/bin/launchctl kickstart` (same family as `lsregister`/`tccutil`
self-surgery).

### Verdict

**`NOT-APPLICABLE`.** No Sparkle in the rewrite. When an updater exists, depend
on Sparkle ≥ 2.9.0; do not shell out.

---

## T-BETA-SIDECAR — beta is a different app as far as TCC is concerned

### Legacy evidence

Landed on `origin/main` *after* the 02:36 pin, while this sweep was running
(`9d3a0feacff1048e8d1fd99c6e08899125152381`, 2026-08-15 03:36, #11614). This
lane did not fetch; the object was already in the shared git dir. `AppBuild.swift`
7–11, 210–213:

```
/// A distinct bundle id gives it its own UserDefaults domain, TCC grants,
/// Keychain ACL, and single-instance lock, so it runs side-by-side with stable.
/// Stable.app never consumes the beta Sparkle channel: leftover
/// `update_channel` defaults and server-synced settings must not opt it into
/// newer stable-identity zips against production APIs.
```

### The rule

Channel is identity-bound. Do not switch a stable-identity app onto the beta
Sparkle feed. Beta needs its own bundle id or it shares (and corrupts) TCC and
Keychain with stable.

### Verdict

**`NOT-APPLICABLE`.** No updater / dual-channel packaging yet. Queue with
T-DMG and T-KEYCHAIN-DP scoping.

---

## T-WINDOW-CACHE — timeout and last-known-good, without poisoning

### Legacy evidence

`ScreenCaptureService.swift` 10–11, 28–31, 496–571: 500 ms resolve timeout, 2 s
cache. A helper/secure surface can resolve an app name without a window ID;
that result must not replace a known-good target. A nil window ID must not
enter the cache. A no-window result is distinct from a timeout (pause rather
than capturing the previous app from cache on lock/loginwindow).

Legacy AX skip-after-3-failures and `nonisolated(unsafe)` statics are
do-not-port. Private `_AXUIElementGetWindow` is do-not-port; resolve from SCK.

### The rule

Bound WindowServer lookups. Cache only snapshots that have a captureable
window ID. Do not use the cache to record lock/loginwindow/screenshot apps.

### Whether our code honors it

**`VIOLATED` (reading).** Rewrite resolves `NSWorkspace.frontmostApplication`
+ SCK windows with no timeout and no last-known-good cache. Helper transitions
drop the tick (`captureFocused` returns nil). `CGWindowListCopyWindowInfo` in
`screenSharingActive()` (ScreenCapture.swift 156) is still a synchronous
WindowServer call every second.

SkyLight stall could not be reproduced without a wedged WindowServer.

### Port

A 500 ms timeout around shareable-content / window-list, plus a 2 s
last-known-good on the engine actor, with tests: nil window ID does not cache;
lock/loginwindow does not play back the previous app. No AX.

---

## Ranked port queue

| Rank | ID | Size | Surface | Why first |
| --- | --- | --- | --- | --- |
| 1 | T-INT-NAN | S — pure function + existing JS/swiftc harness | `frontend/shells/macos` ScreenPolicy | Uncatchable crash; we already filter but the trap is one refactor away |
| 2 | T-SAMPLE-FINITE | XS — one `.isFinite` | `ListenCapture.swift` | Same class of trap; measured `Inf > 0` |
| 3 | T-TCC-FRONTMOST (mic) | S — activate before `requestAccess` | `ListenSocket.swift` | PERM-02 was a real empty Settings row |
| 4 | T-TCC-RELAUNCH | S — launch snapshot + 3-line predicate + UI copy | ScreenCapture engine + surface | Capture starts in a process the WindowServer has not authorized |
| 5 | T-402-RETRY | S — classifier + fixtures | `apps/service/chat` | Retry storm on a dead billing lane |
| 6 | T-SIGPIPE | XS — one `signal` | `main.swift` | Process death on any broken pipe |
| 7 | T-SCSHAREABLE | M — TTL cache on the existing actor | ScreenCaptureEngine | 1 Hz WindowServer enumeration |
| 8 | T-WINDOW-CACHE | M — timeout + last-known-good on the actor | ScreenCaptureEngine | Helper transitions drop recording; list-copy can stall |
| 9 | T-CONVERTER +64 / formatDrift | S | `ListenPcm16` | Cheap once route changes exist |
| 10 | T-A2DP-ENGINE + T-COREAUDIO-UID | L — new input actor | macOS listen | Bluetooth output quality; UID reconnect. Largest listen debt |
| 11 | T-PHONEMIC | L — when iOS capture exists | iOS shell | #6499 / #4706; do not start iOS capture without this |
| 12 | T-DMG + T-SETICON + T-KEYCHAIN scope + T-BETA-SIDECAR | M — packaging wave | shipping macOS app | TCC identity. Not the prototype's problem |
| 13 | T-BLE-FINALIZE | S — when BLE exists | iOS BLE | Disconnect must close the file |
| 14 | T-SPARKLE-26 | S — Sparkle ≥ 2.9.0, no `launchctl` | updater | Diagnosis only |

Already honored; do not re-port: T-PERM-BADGE, T-CADENCE, T-PRIME-CONSENT,
T-SSE-AFTER-DONE, T-CONVERTER (except +64), T-KEYCHAIN-DP (except team scope),
T-WKSCHEME-STOP.

---

## Coverage

**Swept (git grep / git show against pin `3f5bbcdb`, plus the post-pin sidecar
commit already in the shared object store):**

- macOS screen: `ScreenCaptureService.swift`, `ScreenRecordingPermissionPolicy.swift`,
  `ScreenCaptureManager.swift`, dimension tests
- macOS audio: `AudioCaptureService.swift`, `PreferredMicrophoneReconnect.swift`,
  `AudioSourceManager.swift` (disconnect fallback comment)
- macOS permissions / lifecycle: `AppState.swift`, `AppState+SystemActions.swift`,
  `OmiApp.swift`, `AppInstaller.swift`, `DesktopKeychainStore.swift`
- macOS packaging / update: `UpdaterViewModel.swift` (Sparkle 2.9 / kickstart),
  `AppBuild.swift` (#11614 sidecar), `Node.entitlements` (JIT — noted, not a
  finding without a bundled V8)
- iOS capture: `PhoneMic{SessionConfigurator,InterruptionMonitor,Controller,CaptureEngine,ConverterPipeline,OpusEncoder}.swift`
- iOS BLE: `OmiBleManager.swift` disconnect/finalize
- iOS Flutter stream: `messages.dart` malformed `error:` frames
- Desktop chat stream: `AgentErrorClassifier.swift`, `ChatTurnLifecycle.swift`,
  `ChatStreamingBuffer.swift`
- Rewrite: `frontend/shells/macos/shell/Sources/OmiShell/{ScreenCapture,ScreenPolicy,ScreenImaging,ListenCapture,ListenSocket,ChatStream,Credentials,main}.swift`,
  iOS `AppDelegate.swift`, `apps/service/chat/generation-gateway-source.test.ts`

**Not swept (out of half, or too large to claim):**

- Flutter Dart listen/BLE UI (`app/lib` beyond the SSE parser)
- Android
- Windows desktop
- Full 1179-file `desktop/macos` tree (chat UI, Rewind UI, agent runtime, WAL)
- Firmware / glasses DAT
- Signing scripts, notarization pipelines, provisioning profiles (names only;
  no secrets copied)
- Backend Python provider adapters (sibling lane)
- Private AX call sites (do-not-port; not inventoried)

**Scale actually touched:** ~40 legacy files via `git show`/`git grep` of
`origin/main` at the pin (plus #11614); ~15 rewrite files read; ~12 commits
whose messages explain a rule (`git log -S` / `-1`). Not a line-by-line read of
the 1354 Swift files at HEAD.

**Ran:**

- `node --test frontend/shells/macos/tests/screen-policy.test.mjs` → 1 pass
- `node --test frontend/shells/macos/tests/listen-socket-composition.test.mjs frontend/shells/macos/tests/chat-stream-host.test.mjs` → 2 pass
- `bun test apps/service/chat/generation-gateway-source.test.ts` → 14 pass 0 fail
- `/tmp` swiftc: `Inf > 0`, `Int(NaN)` exit 133, `captureDimensions` nil on zero/NaN
- `rg` for SIGPIPE, 402, data-protection keychain, interruption notifications,
  `needsRelaunch`, SCShareable cache, IOProc

**Did not run:** the legacy app; any request to `https://api.omi.me`; TCC
prompts; Bluetooth / BLE hardware; Sparkle install; DMG translocation;
ScreenCaptureKit against a live WindowServer (TCC).

**Green gates (this worktree):**

- `bun run lint:imports` exit 0
- `bun run lint:closure` exit 0 (three production entrypoints; all forbidden
  substrings ok)
- `bun test` after `bun install`: **2207 pass, 34 skip, 2 fail**. Both failures
  are `omi dev-server: failed to bind 127.0.0.1:4851` in
  `apps/service/bin/dev-server.test.ts`. Occupant: PID 65869
  `bun apps/service/bin/dev-server.ts`, cwd `/Users/dazheng/workspace/omi/platform`
  (the shared checkout this lane must not touch), PPID 1, listening ~40 min.
  Varied: first `bun test` without `node_modules` → 178 fail (missing `hono` /
  ratified-contracts); `bun install` then re-run → those cleared. Did not kill
  the shared-checkout server. Not a failure this docs-only change caused.

**Legacy checkout (read-only; no fetch/checkout/config write):**

```
$ git -C /Users/dazheng/workspace/omi/upstream-keep-clean status --porcelain
fatal: this operation must be run in a work tree
status_exit=128

$ git -C /Users/dazheng/workspace/omi/upstream-keep-clean rev-parse HEAD
519cf00ba8c664668e74f4e74ab5c9a0060e6c20
```

HEAD is unchanged from the start of this lane. The shared `.git` has
`bare = true` (it hosts worktrees), so `status --porcelain` cannot run without
`--work-tree`, which this lane did not pass. This lane issued only
`log|show|diff|grep|rev-parse|ls-tree`.

`origin/main` moved during the sweep from `3f5bbcdb` (02:36, brief pin) to
`9d3a0fea` (03:36, #11614) without this lane fetching. Harvest body is the pin;
T-BETA-SIDECAR is the one post-pin packaging rule already in the object store.

---

## Do-not-port encounters (kept the diagnosis, dropped the mechanism)

| Mechanism | Where | Keep |
| --- | --- | --- |
| `lsregister` / Launch Services re-register | `ScreenCaptureService.attemptSoftRecovery` | Stale LS mapping can grant the wrong binary; fix by shipping one identity |
| `tccutil` / TCC.db sqlite | `AppState+SystemActions.cleanUserTCCDatabase` | Diagnosis: ad-hoc rebuilds orphan TCC rows |
| macOS 13 `screencapture` CLI | `captureWithScreencaptureAsync` | Floor is macOS 14; SCK only |
| `launchctl kickstart` | Sparkle installer | Sparkle ≥ 2.9.0 built-in probe |
| `nonisolated(unsafe)` + `NSLock` on AX / shareable-content cache | `ScreenCaptureService` | Actor state |
| Private AX `_AXUIElementGetWindow` | window ID resolve | SCK `SCWindow` |
| ffmpeg stdin | SIGPIPE comment | Ignore SIGPIPE; no ffmpeg |
| WKWebView init swizzle | iOS `AppDelegate` | Ship path is `OmiUiWebView`; not a port |
