# Ray-Ban Meta — Meta Wearables DAT Build Setup

The default Omi build ships **audio-only** Ray-Ban Meta support (no Meta SDK,
no credentials). This guide produces the **full** build: DAT camera/photo
capture + HFP audio. Full mode is required for founder acceptance.

## Prerequisites

1. **Hardware**: Ray-Ban Meta (Gen 1/Gen 2) or Oakley Meta glasses, paired to
   the **Meta AI app** on the test iPhone and updated to current glasses
   firmware.
2. **Developer Mode** enabled in the Meta AI app for local testing. A Meta
   Wearables Developer Center app, `MetaAppID`, and `ClientToken` are needed
   only for a future beta-channel distribution build.
3. DAT apps cannot ship through the App Store yet. Use a local development
   build for this checklist.
4. Xcode 26 with the iOS 26 SDK, CocoaPods 1.16.2, Flutter 3.41.9, and an iOS
   15.2+ device. The current `.allowBluetoothHFP` source requires the iOS 26
   SDK even though the app back-deploys to iOS 15.2.

## Step 1 — Confirm the isolated DAT target

The project pins `https://github.com/facebook/meta-wearables-dat-ios` to exact
0.8.0. `MWDATCore` and `MWDATCamera` belong only to `RunnerRayBanDat` /
`raybanDat`; they must never be added to default `Runner`, which still links
`mcumgr_flutter` for Omi pendant firmware updates.

Verify the committed graph without opening Xcode:

```bash
ruby app/ios/test/rayban_dat_xcode_graph_test.rb
```

`RayBanMetaHostApiImpl.swift` activates the full path through `canImport` only
in that target. `MWDATMockDevice` is intentionally not linked; add it only to
`RunnerRayBanDat` for a temporary hardware-free test.

## Step 2 — Credentials (distribution builds only — SKIP for Developer Mode)

**Developer Mode testing needs no Developer Center configuration at all.**
Meta's own DAT samples run with: glasses Developer Mode ON in the Meta AI
app → launch your locally built app → Connect. The Developer Center's
"Mobile app configuration" (Team ID / Bundle ID / credentials) applies only
to Meta beta-channel distribution.

Known distribution blocker: Meta's Bundle ID field rejects hyphens, and
Omi's iOS bundle ids (`com.friend-app-with-wearable.ios12[.development]`)
contain them — distributing through Meta's channel will require a dedicated
hyphen-free bundle identifier. Track this before any beta rollout.

### Distribution credentials (when you get there)

Info.plist already carries the Developer Mode-safe `MWDAT` dictionary: the
`omirayban` callback URL scheme and `DAMEnabled`. It deliberately does **not**
include `MetaAppID` or `ClientToken`, because Meta's Developer Mode flow must
run without those credential keys. The git-ignored xcconfig below is a staging
place for future beta/distribution work; the current Xcode project does not
consume `META_APP_ID` / `META_CLIENT_TOKEN` unless a distribution-specific
Info.plist/build-setting mapping is added at the same time.

```bash
cd app/ios/Flutter
cp RayBanMetaCredentials.xcconfig.template RayBanMetaCredentials.xcconfig
# fill in META_APP_ID and META_CLIENT_TOKEN from the Developer Center
```

Note: `getAvailabilityMode()` returns `full` whenever the DAT SDK is linked —
credentials do not gate the mode. For distribution, add the `MetaAppID` /
`ClientToken` keys to the `MWDAT` dictionary through a dedicated build
configuration or plist overlay, then register the exact `omirayban://` scheme
and your iOS bundle id in the Wearables Developer Center app settings.

Already present in Omi's Info.plist (no action): `NSMicrophoneUsageDescription`,
`NSBluetoothAlwaysUsageDescription`, `NSCameraUsageDescription`, background
mode `audio`.

## Step 3 — Build

Run the standard `bash setup.sh ios` once in a fresh checkout to seed Firebase
files and generated Dart sources, then stop its default launch. Set `.dev.env`
afterward; the DAT xcconfigs enforce the exact development team and bundle ID
even if setup generated a machine-specific `Custom.xcconfig`.

For a local backend, start it first and put the printed LAN URL in
`app/.dev.env` so the iPhone can reach it:

```bash
cd backend
./scripts/dev-serve.sh

cd ../app
# .dev.env
# API_BASE_URL=http://<mac-lan-ip>:<printed-port>/
# USE_WEB_AUTH=true
# USE_AUTH_CUSTOM_TOKEN=true

FLUTTER_BIN=/path/to/flutter-3.41.9/bin/flutter \
  scripts/rayban_dat.sh run -d <physical-iphone-id>
```

The wrapper performs the DAT-only plugin transform and CocoaPods install,
launches with `--flavor raybanDat --dart-define=OMI_RAYBAN_DAT=true --no-pub`,
and restores the exact default graph plus the prior `Generated.xcconfig` and
`flutter_export_environment.sh` bytes when Flutter exits. Its setup/cleanup
`pub get` calls enforce the committed lockfile, so use the pinned Flutter
version above. Use
`scripts/rayban_dat.sh restore` after an interrupted cleanup. Standard
`flutter run --flavor dev` remains the default audio-only build.

`getAvailabilityMode()` returns `full` in the running DAT build.

## Step 4 — Authorize and pair inside Omi

1. Launch Omi on the phone that has the Meta AI app + paired glasses.
2. Home → battery pill → **Connect** (or onboarding device list).
3. **Ray-Ban Meta** appears in the list → tap it.
4. The setup sheet opens Meta AI (**Connect through Meta AI**); approve the
   authorization there; Meta AI deep-links back to Omi.
5. Grant the glasses **camera permission** when the sheet asks (photo capture),
   or skip for audio-only behavior.
6. The glasses connect and become the active capture device.

## Verifying

- **Mic route**: start capture; the connected-device screen shows
  “Microphone ready”; iOS Control Center shows the glasses as the input;
  transcript segments appear in Omi within seconds of speech.
- **Photos**: connected-device screen → **Capture Photo**; the glasses'
  capture LED lights; within ~10 s the photo appears in the in-progress
  conversation (and the backend logs a `photo_described` event). While capture
  is running a photo is also taken automatically every 30 s.
- **Conversation provenance**: finished conversations carry
  `source=rayban_meta` (visible via `GET /v1/conversations` or the source tag).

## MockDevice (no hardware)

Add **MWDATMockDevice** to `RunnerRayBanDat` in Debug and follow Meta's
MockDeviceKit docs to simulate a paired device, permissions, and photo
capture. Useful for exercising the pairing sheet and photo pipeline in CI-less
environments; founder acceptance still requires real glasses.
