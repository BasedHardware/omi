# Ray-Ban Meta — Troubleshooting

## "Ray-Ban Meta" doesn't appear in the device list

- **Android**: not supported yet — iOS only.
- **Audio-only build** (default repo build): the entry appears only when the
  glasses are connected to the phone as a Bluetooth audio device whose name
  matches a Meta product ("Ray-Ban…", "Oakley Meta…", "Meta Glasses"). Check
  iOS Settings → Bluetooth shows the glasses connected, then rescan.
- **Full build**: `getAvailabilityMode()` must be `full`. If the setup entry
  is missing, the SPM package is not linked into the Runner target or the
  Developer Mode-safe `MWDAT` Info.plist dictionary is missing
  (`AppLinkURLScheme` / `DAMEnabled`). Developer Mode should not include
  `MetaAppID` / `ClientToken`.

## Registration never completes (stuck on "Finish connecting in Meta AI")

- Meta AI app must be installed, signed in, and the glasses paired inside it.
- The callback URL scheme (`omirayban`) must be registered in **both**
  Info.plist `CFBundleURLTypes` and the Wearables Developer Center app config.
- Kill and reopen Omi, tap the Ray-Ban Meta entry again, use **Check Again**.
- For beta/distribution builds only, confirm the Wearables Developer Center
  team, bundle id, and callback scheme match the signed app.

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

### Concrete implementation plan (chosen: option 3 — DAT flavor without `mcumgr_flutter`)

Option 3 is the only fix landable without waiting on Meta, and it is fully in
our control. The audio-only path (the one that ships today) needs none of this;
this is only for producing a **camera-capable DAT build**. It must be built and
verified on a Mac + a physical iPhone + glasses — there is **no iOS build in PR
CI** (mobile CI is `ubuntu-latest`: `flutter pub get`, `gen-l10n`, `dart
analyze`, `flutter test` only), so none of the steps below are exercised by CI
and each must be validated on-device.

1. **Gate `mcumgr_flutter` behind a build flag.** In `app/ios/Podfile`, when an
   env flag is set (e.g. `OMI_RAYBAN_DAT=1`), remove the `mcumgr_flutter` pod
   target and every pod that depends on it from `installer.pods_project` in
   `pre_install`/`post_install`, so SwiftProtobuf never enters the `Runner`
   static image alongside `MWDATCore`.
2. **Stop the generated registrant from importing it (the easy-to-miss step).**
   `app/ios/Runner/GeneratedPluginRegistrant.swift` is regenerated on every
   `flutter pub get`/build from pub resolution, and it will `import
   mcumgr_flutter` + call `McumgrFlutterPlugin.register(...)`. With the pod
   removed that is a compile/link error, so a Podfile change **alone produces a
   broken DAT build**. Either (a) exclude the plugin from pub resolution for the
   DAT build so it is never generated, or (b) add a build phase that strips the
   `mcumgr_flutter` import/registration from the generated file for that
   configuration.
3. **Guard the Dart firmware-update call sites.** `mcumgr_flutter` is used
   across the CV1/OpenGlass OTA flows (`firmware_mixin.dart`,
   `firmware_update*.dart`, `device_provider.dart`, `omiglass_ota_update.dart`,
   et al.). In a DAT build those paths must be unreachable (feature-flagged
   off), since the plugin is absent. Ray-Ban glasses never do nRF MCU firmware
   updates, so this is acceptable for that flavor.
4. **Accept the tradeoff:** the DAT flavor cannot OTA-update Omi CV1 pendants.
   Ship it as a separate build, not the default.

Verification (Mac + hardware, no CI coverage): build the DAT flavor, launch,
confirm the `objc[…] Class _TtC13SwiftProtobuf… implemented in both …` warning
is gone and there is no `SIGSEGV`/`EXC_BAD_ACCESS` in `swift_getObjectType`
during plugin registration, then run the founder-acceptance checklist
(`rayban-meta-founder-acceptance.md`) end-to-end including a photo capture.

## Reference

- Meta toolkit docs: <https://wearables.developer.meta.com/docs/develop/>
- Mic/speaker guidance (HFP): <https://wearables.developer.meta.com/docs/develop/dat/microphones-and-speakers/>
- iOS integration: <https://wearables.developer.meta.com/docs/build-integration-ios/>
