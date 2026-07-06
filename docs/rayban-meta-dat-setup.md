# Ray-Ban Meta — Meta Wearables DAT Build Setup

The default Omi build ships **audio-only** Ray-Ban Meta support (no Meta SDK,
no credentials). This guide produces the **full** build: DAT camera/photo
capture + HFP audio. Full mode is required for founder acceptance.

## Prerequisites

1. **Hardware**: Ray-Ban Meta (Gen 1/Gen 2) or Oakley Meta glasses, paired to
   the **Meta AI app** on the test iPhone and updated to current glasses
   firmware.
2. **Meta Wearables Developer Center** account: <https://wearables.developer.meta.com>.
   Create an app to obtain:
   - `MetaAppID`
   - `ClientToken`
3. **Developer mode / test channel**: DAT apps cannot ship through the App
   Store yet. Run local development builds, or distribute to your org's
   testers through the Wearables Developer Center beta channel.
4. Xcode 15.4+ (repo currently builds with Xcode 26), iOS device on iOS 15.2+.

## Step 1 — DAT Swift package (already in the project)

The Runner project carries an SPM reference to
`https://github.com/facebook/meta-wearables-dat-ios` (exact 0.8.0; binary
xcframeworks) with products **MWDATCore** and **MWDATCamera** on the Runner
target. Nothing to do — `RayBanMetaHostApiImpl.swift` activates its DAT path
via `#if canImport(MWDATCore)`, and this compiles clean against 0.8.0
(verified). To bump versions, edit the package requirement in Xcode's Package
Dependencies. (Optionally add **MWDATMockDevice** to Debug for hardware-free
testing.)

## Step 2 — Credentials (the only manual step)

Info.plist already carries the `MWDAT` dictionary (`MetaAppID`/`ClientToken`
resolve from build settings), the `omirayban` callback URL scheme, and the
`com.meta.ar.wearable` accessory protocol. Provide the credentials via a
git-ignored xcconfig:

```bash
cd app/ios/Flutter
cp RayBanMetaCredentials.xcconfig.template RayBanMetaCredentials.xcconfig
# fill in META_APP_ID and META_CLIENT_TOKEN from the Developer Center
```

With the file absent the build stays in audio-only mode; with it present,
`getAvailabilityMode()` returns `full`. Register the exact `omirayban://`
scheme and your iOS bundle id in the Wearables Developer Center app settings.

Already present in Omi's Info.plist (no action): `NSMicrophoneUsageDescription`,
`NSBluetoothAlwaysUsageDescription`, `NSCameraUsageDescription`, background
mode `audio`.

## Step 3 — Build

```bash
cd app
bash setup.sh ios              # first time only
flutter build ios --flavor dev --debug   # or run on device from Xcode
```

`getAvailabilityMode()` now returns `full` (SDK linked + `MetaAppID` present).

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

Add **MWDATMockDevice** to the Runner target in Debug and follow Meta's
MockDeviceKit docs to simulate a paired device, permissions, and photo
capture. Useful for exercising the pairing sheet and photo pipeline in CI-less
environments; founder acceptance still requires real glasses.
