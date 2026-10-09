# INV-CAP-1: Pendant audio is never discarded without an explicit user pause

**Status:** locked

**Statement:** While the user has not deliberately paused the microphone or powered off the pendant, every audio frame the pendant samples is either delivered live, durably written on the device, or held in a ring that a later sync drains. A connected pendant must not drop frames because a phone-side power policy closed a socket, unsubscribed a characteristic, or went to sleep. Battery optimization may change WHEN audio is transmitted and transcribed; it may never change WHETHER captured audio survives.

This covers every path a pendant can take while connected: live transcription, silence-based power saving, phone background eviction, BLE reconnect windows, and any future uplink-throttling policy. "The phone paused the uplink to save battery" is not a user pause. Only an explicit user gesture — mute, pause, or power-off of the device — licenses frame loss.

## Why

The tiered capture work of 2026-10-06 (omi#20837) shipped a battery fix that paused the phone's BLE subscription and transcription socket after a silence timeout. On current pendant firmware, a connected pendant in live mode discards frames when no phone is subscribed (the pusher writes to storage only when `!conn` or in batch mode; live mode is explicitly never persisted — `omi:omi/firmware/omi/src/lib/core/transport.c`). The result: a user wearing the pendant all day would lose speech that started more than two minutes after their last conversation, with no indication and no user action — exactly the class this invariant forbids. The failure was caught in review of the product trade before any field loss, and the pause path is being disabled pending a device-side retention guarantee.

The design had been accepted through two review rounds as an "accepted trade." A trade that silently deletes user recordings is not acceptable at any battery saving. This invariant exists so the next battery proposal — on any platform, by any contributor or agent — hits a named, indexed rule instead of re-deriving the boundary in review.

## MUST NOT

- Close, unsubscribe, or fence a pendant uplink while leaving the pendant in a state where sampled audio has no durable destination.
- Treat silence timeout, app backgrounding, sync-scoped fencing, or any automatic scheduler as license to discard frames. These may pause TRANSMISSION only if the device is concurrently retaining.
- Ship a phone-side power policy whose correctness depends on pendant firmware behavior that is not itself shipped and verified (e.g. counting on a future firmware ring-buffer without gating the phone behavior on the firmware's advertised capability).
- Describe a policy that drops frames as "syncs later". Sync-later claims require the audio to exist somewhere durable.
- Let a resume path imply recovery of the gap. A resume that restores live capture after frames were discarded is a new session, not a recovery.

## MUST

- Gate any uplink pause on a verified device-side retention guarantee: an advertised, tested capability that the pendant retains frames across the pause (ring buffer, flash record, or equivalent), with an explicit protocol for drain-on-reconnect.
- Prefer, in order: (1) device-side retention during pause, (2) keeping the uplink open at reduced duty cycle, (3) not pausing at all. Frame loss is never on the list.
- Surface to the user, when a pause is active, that capture is suspended — the UI must never show a live/listening state while frames are being discarded.
- Add a regression test for any change that alters when the phone stops consuming pendant audio, asserting either continued delivery or verified device retention.

## Guard tests

- `app/test/services/capture/tiered_capture_test.dart` — current firmware keeps live delivery beyond silence, queued expiry has no pause effects, historical automatic pauses recover, and manual mute survives restart.
- `app/test/services/capture/resume_sync_fence_test.dart` — historical pause recovery reconciles the uplink after coalesced sync scopes, including charging-edge admission and zero-transport sync wakes.

## Surfaces

- Flutter capture controller and uplink policy (`omi:app/lib/services/capture/`), device connectors, and the sync-wake fence
- iOS/Android BLE managers' subscription lifecycle (`omi:app/ios/Runner/Ble/`, Android BLE service)
- Pendant firmware audio transport and storage paths (`omi:omi/firmware/omi/src/lib/core/transport.c`, mic capture, SD/ring writers)
- Any future tiered capture, silence detection, or battery-optimization policy on any platform

## Path globs

- `app/lib/services/capture/**`
- `app/lib/services/devices/connectors/**`
- `app/lib/services/wals/**`
- `app/ios/Runner/Ble/**`
- `app/android/app/src/main/kotlin/com/friend/ios/ble/**`
- `omi/firmware/omi/src/lib/core/**`
