# Mobile local preview

Batch-lane mobile sessions render an on-device streaming preview; the batch
transcript is the record. The preview is display only: it never stores, uploads
or owns audio, and WAL/batch custody is unchanged.

## Admission

The iOS client declares `local_preview=enabled` on `/v4/listen` (part of the
socket reuse key) unless the PostHog kill switch `mobile-local-preview-disabled`
is true (`LivePreviewGate`; absent/false/offline/error keeps it on). Custom STT,
onboarding and phone-call sockets never declare it. Android installs no preview
controller yet, so it never declares it and keeps today's cloud transcript.

The server grants it on `service_status` `ready` / `mobile_batch_admission` with
`local_preview: true` and `mobile_standard_batch: true`. The grant is
socket-scoped: close, reconnect and account change clear it until re-granted,
and it rides `MobileStandardBatch.authorize` (same two-minute expiry).

## Routing

While admitted, `MobileStandardBatch.eligible` ignores transcript visibility and
voice-command sessions no longer force frames to the socket. Every other
realtime-consumer clause is unchanged; a frame the journal refuses still goes to
the safety WAL and the socket. Any audio reaching an admitted socket opens the
deferred cloud stream, so a socket that declared local preview holds pendant
frames until its verdict (`LocalPreviewAdmission`). They still go to the safety
WAL, and an in-memory copy (at most 10 s / 500 frames, oldest first) is kept: a
refusal (verdict without `local_preview`, or no verdict within 10 s) sends them
to the socket in order before any newer frame, so non-admitted sessions keep
their whole live transcript; a grant drops the copy; overflow stops holding and
flushes. Socket close before a verdict keeps the copy for the replacement
socket, resolved against its verdict (a replacement that did not declare local
preview is a refusal); only capture end or an account change discards it. The
journal's first-use warm-up also keeps frames off the socket, only on an
admitted socket. Frames that never reach a socket (warm-up, held then granted)
stay in the safety WAL; an admitted session gets no ConversationEvent, so that
WAL stays unconfirmed and the ordinary recovery drain uploads it through
`/v2/sync-local-files` to the batch record (covered by
`test/services/live_preview/local_preview_routing_test.dart`).

Known gaps:
- Phone-mic capture is not in the batch route: its audio still streams to the
  socket (and opens the deferred cloud stream). The preview still runs from
  `phoneMicAudioTap`; the surface keeps showing it while an engine runs.
- Android's native background streamer (`OmiBackgroundAudioStreamer.kt`, used
  without a Flutter engine) does not declare local preview and stays a normal
  cloud stream.

## Engine

`LivePreviewEngine` over `com.omi/live_preview` (+ `/events`), separate from the
single-flight `com.omi/on_device`. iOS (`ios/Runner/LivePreviewPlugin.swift`):
SpeechAnalyzer/SpeechTranscriber with volatile results on iOS 26+ when the locale
asset is already installed (never downloads), else on-device SFSpeech with
existing permission (never prompts), rotated every 50 s, else none. Omi's own
Parakeet model is not used for streaming yet (`bundled_not_built`). A running
engine that dies reports a typed runtime failure (`engine_error`); the
controller retries the selection once without it, else shows the no-engine
state. Decode work runs in bounded slices (8 packets per event-loop turn). No engine is
a calm "Transcribing…" state; there is never a cloud fallback.

Pendant packets are copied, the 3-byte header stripped and decoded with a
preview-only Opus decoder; the tap only enqueues into a bounded queue, and
overload drops preview audio.

## UI and hand-off

`LivePreviewController` is a separate model from `CaptureController.segments`
(never in LocalSegmentStore, the REST poll, `_segmentArrivals` or conversation
creation). Lines clear on capture stop/account change, and after a silence as
long as the conversation timeout; the conversation list's normal refresh shows
the record.

## Telemetry

`Live Preview Engine` (engine, reason, platform, os_major, bundled_installed),
`Live Preview First Word` (latency_ms from first fed audio) and `Live Preview
Session Ended` (preview_words, preview_audio_ms, dropped_audio_ms). No text,
audio or locale leaves the phone. Preview-to-record disagreement is a follow-up:
it needs an on-device span match against the batch record.
