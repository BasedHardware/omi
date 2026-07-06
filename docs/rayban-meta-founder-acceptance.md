# Ray-Ban Meta — Founder Acceptance Guide

Acceptance is only claimable on a **physical iPhone + physical Ray-Ban Meta
glasses + DAT-enabled build** (see `rayban-meta-dat-setup.md`). No mock mode,
no fake transcripts, no manual uploads.

## Preconditions

- [ ] Physical iPhone (iOS 15.2+; tested on current iOS).
- [ ] Physical Ray-Ban Meta glasses, charged, paired in the Meta AI app.
- [ ] Meta Wearables Developer Center app credentials; Omi built in **full**
      mode (`getAvailabilityMode() == 'full'`).
- [ ] Fresh install of this branch's Omi app (dev flavor), signed into an
      account.

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
- Backend source handling + photo provenance —
  `backend/tests/unit/test_rayban_meta_source.py`.
- Full app compiles and existing suites pass; iOS dev-flavor build succeeds in
  audio-only mode (no SDK, no credentials).

Requires physical hardware + DAT credentials (NOT claimable from CI):

- Meta AI registration round-trip (URL scheme callback).
- Real HFP mic capture quality and route stability.
- DAT camera stream, photo capture, LED behavior.
- End-to-end transcript/memory quality from glasses audio.
- First compile of the `#if canImport(MWDATCore)` code path against the real
  SDK (written against the DAT 0.8 reference; symbol drift is possible and
  fixes are contained to `RayBanMetaHostApiImpl.swift`).
