# Ray-Ban Meta — Troubleshooting

## "Ray-Ban Meta" doesn't appear in the device list

- **Android**: not supported yet — iOS only.
- **Audio-only build** (default repo build): the entry appears only when the
  glasses are connected to the phone as a Bluetooth audio device whose name
  matches a Meta product ("Ray-Ban…", "Oakley Meta…", "Meta Glasses"). Check
  iOS Settings → Bluetooth shows the glasses connected, then rescan.
- **Full build**: `getAvailabilityMode()` must be `full`. If the setup entry
  is missing, the `MWDAT` Info.plist dictionary is missing/empty
  (`MetaAppID`) or the SPM package isn't linked into the Runner target.

## Registration never completes (stuck on "Finish connecting in Meta AI")

- Meta AI app must be installed, signed in, and the glasses paired inside it.
- The callback URL scheme (`omirayban`) must be registered in **both**
  Info.plist `CFBundleURLTypes` and the Wearables Developer Center app config.
- Kill and reopen Omi, tap the Ray-Ban Meta entry again, use **Check Again**.
- Confirm the `TeamID` in the `MWDAT` dict matches the signing team.

## Connected, but no transcript while speaking

- Check the input route: iOS Control Center → mic in use should be the
  glasses. If it's the phone mic, toggle glasses Bluetooth off/on and restart
  capture; the app prefers the `.bluetoothHFP` input but iOS can override.
- Another HFP device (car, headset) may have claimed the route — disconnect it.
- The wearer's voice is beamformed: other speakers are much quieter by design.
- Meta AI's own wake-word/assistant sessions share the mic with the system;
  finish or disable an active Meta AI voice interaction.
- Audio-only sanity check: with capture running, `isGlassesAudioRouteActive()`
  (logged by the transport as `glasses audio route active=`) should be true.

## Music keeps pausing

Expected. HFP (mic) and A2DP (music) are mutually exclusive on the Bluetooth
link — while Omi captures from the glasses mic, phone audio drops to the
voice channel. Stop capture to restore music quality.

## Photos never arrive

- Audio-only build: photo capture is unavailable by design (the UI says so).
- Camera permission: connected-device screen → Camera row must say
  "Image capture ready". Re-run the setup sheet to grant it.
- Meta's ordering constraint: the camera stream must start after HFP audio is
  stable. The bridge sequences this, but if the camera state (logged as
  `camera state=`) sticks at `starting`, stop and restart capture.
- DAT streams can stall on Bluetooth Classic bandwidth pressure; stop/start
  the camera (toggle capture) to recover.
- Check backend logs for `image_chunk` handling; chunks expire after 60 s if
  the stream is interrupted mid-photo.

## Conversation shows source "openglass" or "unknown" instead of Ray-Ban Meta

- `unknown`: the backend predates `ConversationSource.rayban_meta` — deploy a
  backend including it.
- `openglass`: the backend predates the source-aware photo flip
  (`resolve_photo_conversation_source`) — deploy current backend.

## Build errors in RayBanMetaHostApiImpl.swift after adding the SDK

The DAT integration was written against the DAT 0.8 API reference without SDK
access (the package is public but the API may drift between preview releases).
All DAT symbols live in `app/ios/Runner/RayBanMeta/RayBanMetaHostApiImpl.swift`
inside `#if canImport(MWDATCore)` — reconcile symbol names against
<https://wearables.developer.meta.com/docs/reference/ios_swift/dat/> for your
package version. `RayBanMetaAudioCapture.swift` has no DAT dependency and
should never break.

## Glasses battery not shown

Expected — DAT 0.8 exposes no battery API; the row is hidden.

## App crashes at launch after linking the DAT SDK (SwiftProtobuf collision)

**Known integration blocker — must be resolved before shipping the DAT build.**

Symptom: with `MWDATCore`/`MWDATCamera` linked, the app crashes on launch
(`EXC_BAD_ACCESS` / `SIGSEGV` in `swift_getObjectType`, during Flutter plugin
registration in `didFinishLaunchingWithOptions`), and the console prints, on
every launch:

```
objc[…]: Class _TtC13SwiftProtobuf… is implemented in both
  …/Runner.app/Frameworks/MWDATCore.framework/MWDATCore and …/Runner.app/Runner.
  This may cause spurious casting failures and mysterious crashes.
```

Root cause: Meta's `MWDATCore.framework` (a binary xcframework) **statically
embeds its own copy of SwiftProtobuf and exports its Objective-C classes**. The
Omi app already links SwiftProtobuf through `mcumgr_flutter` (the nRF MCU
firmware-update library, `iOSMcuManagerLibrary`). With
`use_frameworks! :linkage => :static`, SwiftProtobuf's classes end up in both
the `Runner` executable and `MWDATCore.framework`. Duplicate Objective-C class
registration corrupts the Swift runtime's type metadata, so a later,
unrelated Swift plugin's `register(with:)` dereferences null.

Confirmed by removing `mcumgr_flutter` (the app's only SwiftProtobuf consumer —
`whisper_flutter_new` does not use it): the duplicate disappears (`nm Runner |
grep -c SwiftProtobuf` → 0) and the launch crash goes away. That removal is not
shippable, though — it disables Omi CV1 MCU firmware updates.

Fix directions (pick one before enabling the DAT build in production):

1. **Ask Meta to stop exporting SwiftProtobuf** from `MWDATCore` (build it with
   hidden symbol visibility / a private module, or vendor it under a renamed
   namespace). This is the clean fix and the right upstream ask — file it on
   <https://github.com/facebook/meta-wearables-dat-ios/issues>.
2. **Remove the app's second SwiftProtobuf copy.** Replace `mcumgr_flutter`'s
   SwiftProtobuf dependency, or isolate MCU-DFU (the only consumer) behind a
   boundary that doesn't co-link with `MWDATCore` — e.g. load `MWDATCore` only
   in a build/flavor that excludes `mcumgr_flutter`, or move MCU-DFU to an app
   extension/process.
3. **Gate the DAT feature to a dedicated flavor** that excludes
   `mcumgr_flutter` (Ray-Ban glasses don't do nRF MCU firmware updates anyway),
   accepting that that flavor can't OTA-update Omi CV1 pendants.

Until one of these lands, keep the DAT SPM package out of the default shipping
build (the `#if canImport(MWDATCore)` guard already makes the app compile and
run in audio-only mode without it).

## Reference

- Meta toolkit docs: <https://wearables.developer.meta.com/docs/develop/>
- Mic/speaker guidance (HFP): <https://wearables.developer.meta.com/docs/develop/dat/microphones-and-speakers/>
- iOS integration: <https://wearables.developer.meta.com/docs/build-integration-ios/>
