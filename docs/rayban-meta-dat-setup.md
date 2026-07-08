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
4. Xcode 16.4+ (per `app/setup.sh`; repo currently builds with Xcode 26), iOS device on iOS 15.2+.

## Step 1 — Link the DAT Swift package (deliberately NOT linked by default)

The default project ships **without** the Meta package: `MWDATCore.framework`
embeds SwiftProtobuf, which collides with the copy `mcumgr_flutter` links and
crashes at launch (see `rayban-meta-troubleshooting.md` → "App crashes at
launch"). For a DAT development build, link it manually:

1. Open `app/ios/Runner.xcworkspace` → Runner project → **Package
   Dependencies** → `+` → `https://github.com/facebook/meta-wearables-dat-ios`
   (exact 0.8.0; binary xcframeworks).
2. Add products **MWDATCore** and **MWDATCamera** to the **Runner** target.
   (Optionally **MWDATMockDevice** for hardware-free testing on Debug.)

`RayBanMetaHostApiImpl.swift` activates its DAT path via
`#if canImport(MWDATCore)` — no source changes needed; the code compiles clean
against 0.8.0 (verified). Do not commit the linkage until the SwiftProtobuf
collision is resolved.

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

```bash
cd app
bash setup.sh ios              # first time only
flutter build ios --flavor dev --debug   # or run on device from Xcode
```

`getAvailabilityMode()` now returns `full` once the SDK is linked.

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
