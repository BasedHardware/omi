# Ray-Ban Meta — Founder Acceptance Guide

Acceptance is only claimable on a **physical iPhone + physical Ray-Ban Meta
glasses + DAT-enabled build** (see `rayban-meta-dat-setup.md`). No mock mode,
no fake transcripts, no manual uploads.

## Preconditions

- [ ] Physical iPhone (iOS 15.2+; tested on current iOS).
- [ ] Physical Ray-Ban Meta glasses, charged, paired in the Meta AI app,
      **Developer Mode enabled** (Meta AI app → Settings → App Info → tap the
      version 5×), glasses software v20.0+.
- [ ] Build through `app/scripts/rayban_dat.sh`; its dedicated target links DAT
      without the `mcumgr_flutter`/SwiftProtobuf pod graph.
- [ ] Omi built in **full** mode (`getAvailabilityMode() == 'full'`): DAT SPM
      package 0.8.0 linked only to `RunnerRayBanDat` + glasses Developer Mode
      on. No Meta Developer Center credentials are needed for local testing.
- [ ] Fresh install of this branch's Omi app (`raybanDat` flavor), signed into an
      account.
- [ ] Local backend is reachable from the iPhone over the Mac's LAN URL and its
      log is visible for transcript/photo evidence.

## Signing / build environment (read first — this is what blocks on-device runs)

The app must run under its **real identity** or auth and multi-target signing
break. Do not fall back to a personal Apple team — that forces a different
bundle id, which cascades into a Firebase project mismatch (auth 401s), a
Sign-in-with-Apple entitlement loss, and Watch-app/widget bundle-prefix
signing errors. Instead:

- [ ] Sign with the **Based Hardware Apple team** (`9536L8KLMP`, the committed
      default). The team's Apple Developer Program membership must be active,
      and your Apple ID must have the **Developer** role plus Certificates,
      Identifiers & Profiles access — *Customer Support* cannot issue profiles.
      Have the Account Holder renew the membership or an Admin grant access
      when Apple reports "Access Unavailable".
- [ ] The development profile for
      `com.friend-app-with-wearable.ios12.development` contains the test
      iPhone's UDID. `fastlane match development --readonly` only downloads the
      existing profile; it cannot register a new device or regenerate it.
- [ ] Keep the original bundle id (`com.friend-app-with-wearable.ios12.development`)
      so the committed `based-hardware-dev` Firebase config and
      `USE_AUTH_CUSTOM_TOKEN`/`USE_WEB_AUTH` flow match (custom-token auth; a
      natively-minted Firebase token is rejected by `api.omiapi.com` with 401).
- [ ] Build and install via
      `FLUTTER_BIN=/path/to/flutter-3.41.9/bin/flutter app/scripts/rayban_dat.sh run -d <device-id>`.
      Never hand-install a stale `build/ios/iphoneos/Runner.app`.
- [ ] Before pairing, inspect the launch log: no duplicate SwiftProtobuf class
      warning, `SIGSEGV`, `EXC_BAD_ACCESS`, or `swift_getObjectType` crash.

## Acceptance checklist

1. [ ] Open Omi → Devices/Connect. **Ray-Ban Meta** is listed alongside
       Omi devices.
2. [ ] Tap Ray-Ban Meta → setup sheet → **Connect through Meta AI** →
       authorize in Meta AI → returned to Omi automatically.
3. [ ] Grant glasses camera permission from the sheet.
4. [ ] Green connected state: device screen shows the glasses name and
       **Connected** pill.
5. [ ] Capabilities visible: **Microphone ready** and **Image capture ready**
       (Camera row).
6. [ ] Ray-Ban Meta is the active capture device (battery pill shows the
       glasses; capture starts from it).
7. [ ] Speak ≥2 minutes of natural conversation wearing the glasses. Live
       transcript segments appear in Omi. Phone music (if playing) pauses —
       expected HFP behavior.
8. [ ] Capture ≥1 image (Capture Photo action, or wait for the 30 s
       auto-capture). Glasses LED lights during camera session. Photo appears
       in the conversation with an AI description.
9. [ ] Stop capture; conversation processes: summary, memories, action items
       created as with any Omi device.
10. [ ] Conversation is labeled Ray-Ban Meta (source `rayban_meta`).
11. [ ] Switch active device back to Omi pendant / phone mic without
        reinstalling; capture works from the new source.
12. [ ] Reconnect flow: toggle glasses off/on → Omi reconnects or offers the
        device again without app restart.

## Founder demo script (~3 minutes)

1. Open Omi.
2. Go to Devices.
3. Select **Ray-Ban Meta**.
4. Pair/connect the glasses (Meta AI authorization already done in prep).
5. Show the green connected status — "Ray-Ban Meta connected".
6. Show capabilities — "Microphone ready", "Image capture ready".
7. It is the active capture device (battery pill).
8. Start capture.
9. Say: *"This is Omi using Ray-Ban Meta as the capture device. Create a
   memory that Ray-Ban Meta can replace the Omi wearable for audio and visual
   context."*
10. Tap **Capture Photo** while looking at the room.
11. Stop capture.
12. Open the conversation: live transcript + the captured photo with its
    description.
13. After processing: show the summary, memory, and action items.
14. Devices → disconnect Ray-Ban Meta → switch back to Omi/phone mic to prove
    clean device swapping.

## What was verified without hardware vs. what requires it

Verified automatically in this repo (no glasses needed):

- Dart device layer: serialization, locator, photo-event framing, discoverer
  matching — `app/test/unit/rayban_meta_device_test.dart`.
- DAT build boundary: generated-plugin removal/restoration, dedicated target,
  exact Meta package pin, signing identity, and default mcumgr preservation —
  `app/ios/test/rayban_dat_*_test.rb`.
- DAT firmware policy: Omi pendant DFU disabled while OpenGlass OTA remains —
  `app/test/unit/firmware_*_test.dart`.
- Backend source handling + photo provenance —
  `backend/tests/unit/test_rayban_meta_source.py`.
- Full app compiles and existing suites pass; iOS dev-flavor build succeeds in
  audio-only mode (no SDK, no credentials).

Requires physical hardware, Bluetooth pairing, and Developer Mode (NOT
claimable from CI):

- Meta AI registration round-trip (URL scheme callback).
- Real HFP mic capture quality and route stability.
- End-to-end transcript/memory quality from glasses audio.

Requires physical hardware + the DAT build (NOT claimable from CI):

- DAT camera stream, photo capture, LED behavior.
- Runtime launch without the SwiftProtobuf duplicate-class crash.
