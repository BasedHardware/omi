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

## Step 1 — Add the DAT Swift package

The Omi iOS project uses CocoaPods for everything else; the Meta toolkit is
SPM-only, so it is added as an SPM package reference on the Runner project:

1. Open `app/ios/Runner.xcworkspace` in Xcode.
2. Runner project → **Package Dependencies** → `+` →
   `https://github.com/facebook/meta-wearables-dat-ios` (0.8.x or newer tag).
3. Add products **MWDATCore** and **MWDATCamera** to the **Runner** target.
   (Optionally **MWDATMockDevice** for hardware-free testing on Debug.)

No source changes are needed: `RayBanMetaHostApiImpl.swift` activates its DAT
path via `#if canImport(MWDATCore)` the moment the package is present. If the
0.8 API surface has drifted from what the bridge was written against
(registration/device/session/stream symbols), fix-ups belong only in
`app/ios/Runner/RayBanMeta/RayBanMetaHostApiImpl.swift`.

## Step 2 — Configure Info.plist

Add to `app/ios/Runner/Info.plist` (values from the Developer Center; do NOT
commit real credentials — inject via xcconfig/build settings):

```xml
<key>MWDAT</key>
<dict>
    <key>MetaAppID</key>
    <string>$(META_APP_ID)</string>
    <key>ClientToken</key>
    <string>$(META_CLIENT_TOKEN)</string>
    <key>TeamID</key>
    <string>$(DEVELOPMENT_TEAM)</string>
    <key>AppLinkURLScheme</key>
    <string>omirayban://</string>
    <key>DAMEnabled</key>
    <true/>
</dict>
<key>UISupportedExternalAccessoryProtocols</key>
<array>
    <string>com.meta.ar.wearable</string>
</array>
```

And register the callback URL scheme (Meta AI app → back to Omi):

```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>omirayban</string>
        </array>
    </dict>
</array>
```

Set `META_APP_ID` / `META_CLIENT_TOKEN` in `ios/Flutter/devDebug.xcconfig`
(and the flavor configs you build) or as Xcode user-defined build settings.
Register the exact `omirayban://` scheme in the Wearables Developer Center app
settings.

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
