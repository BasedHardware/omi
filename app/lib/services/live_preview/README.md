# Mobile local preview

Batch-lane mobile sessions render an on-device streaming preview; the batch
transcript is the record. The preview is display only: it never stores, uploads
or owns audio, and WAL/batch custody is unchanged.

## Admission

The iOS and Android clients declare `local_preview=enabled` on `/v4/listen` (part of the
socket reuse key) unless the PostHog kill switch `mobile-local-preview-disabled`
is true (`LivePreviewGate`; absent/false/offline/error keeps it on). Custom STT,
onboarding and phone-call sockets never declare it.

The server grants it on `service_status` `ready` / `mobile_batch_admission` with
`local_preview: true` and `mobile_standard_batch: true`. The grant is
socket-scoped: close, reconnect and account change clear it until re-granted,
and it rides `MobileStandardBatch.authorize` (same two-minute expiry).

A client asks only when its routing can journal pendant audio: an Omi pendant
on an Opus codec, auto-sync on, no Transcribe Later, no custom STT, not kept on
the phone, no onboarding, and a batch journal installed. Otherwise it does not
declare `local_preview` and reports `Live Preview Not Requested` (closed
reason). Phone-mic capture therefore never asks (PCM, not journaled) and keeps
today's cloud transcript. If one of these flips while admitted, the grant is
dropped for the rest of that socket (preview hides, today's cloud view
returns, no later grant on it re-admits). A hold that times out or overflows
latches the socket as refused too. Transient refusals (disk, journal failure)
keep the WAL+socket carve-out below.

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
preview is a refusal). The batch journal's first-use warm-up never keeps
frames off the socket: a frame it refuses goes to WAL and socket (the
never-lose carve-out; the server counts the deferred stream it opens). Only
WAL-accepted frames are ever held. Granted held frames never reach a socket:
they stay in the safety WAL; an admitted session gets no ConversationEvent, so
that WAL stays unconfirmed and the ordinary recovery drain uploads it through
`/v2/sync-local-files` to the batch record (covered by
`test/services/live_preview/local_preview_routing_test.dart`). Until the WAL
reports them strictly durable (`LocalWalSyncImpl.isFrameDurable`: written to a
disk WAL by a flush of the current generation whose index save completed) the
router keeps a copy and never drops it early. The copies are capped at 18000
frames (2x the WAL's ~3 min worst-case in-memory window at 50 frames/s); at the
cap the router stops suppressing new frames (they stream) instead of evicting: at capture end the copies (and any held frames of an ungranted
socket) go to an open socket first; on an account change with no socket they
are written to the batch journal for the old owner, because the account
cleanup (unchanged from main) discards the WAL's in-memory tail.

Known gaps:
- Android's native background streamer (`OmiBackgroundAudioStreamer.kt`) owns
  pendant audio only while the Flutter engine is absent or not foreground-ready,
  and has no batch journal. It never declares local preview (pinned by
  `OmiBackgroundAudioStreamerTest`): a declared, admitted session would receive
  the audio anyway and open the deferred cloud stream unannounced. Its sessions
  stay ordinary cloud sessions (today's behaviour, counted by the server as
  `local_preview=false`). Journaling from native is a follow-up.

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

Android (`android/.../livepreview/LivePreviewPlugin.kt`): API 33+
`createOnDeviceSpeechRecognizer` fed through a pipe (`EXTRA_AUDIO_SOURCE`, PCM16
16 kHz mono extras, `EXTRA_SEGMENTED_SESSION`), started only when
`isOnDeviceRecognitionAvailable` and `checkRecognitionSupport` list the language
as installed (never `triggerModelDownload`). Recognizer calls run on the main
looper; PCM is written on one background thread behind a bounded queue. The
recognition service checks the caller's RECORD_AUDIO even for an app-supplied
audio source, so without it the reason is `speech_permission_denied` (never
prompted). Android 11-12: `os_too_old`; no on-device service (e.g. no Google
speech services): `os_engine_unavailable`. Without an OS engine, Omi's already
downloaded Whisper model (`whisper_flutter_new`) runs as a windowed
pseudo-stream (4 s windows, one at a time, 30 s bounded buffer, final lines
only); otherwise none.

## On-device live notes

`LivePreviewNotes` (Dart) drafts up to four twelve-word bullets from the
preview text, entirely on this phone, for the Summary tab's "So far" card while
the session has no server running notes. iOS drafts with Apple Foundation
Models (iOS 26+ with Apple Intelligence available) over
`com.omi/live_preview_notes` (`LivePreviewNotesPlugin.swift`; the schema caps
the array at four bullets, the clamp is the belt, generation runs detached off
the main thread and a busy draft is dropped). Android ships no engine in this
release. A session generation fences late results after any clear, including a silence clear-and-refill. New-word admission uses a monotonic session total, independent of the bounded prompt and line eviction. A draft runs at most once a minute and only after at least 40 new
preview words. The shared Dart `LivePreviewWordBudget` and matching native
clamp budget Han/Kana/Hangul-syllable/Thai runs at one word per two graphemes
(rounded up), and other non-whitespace runs at one word; script transitions
end a run. This deterministic approximation bounds mixed and unspaced text
without depending on OS tokenizers. The prompt is capped to the newest ~1500 words (AFM's context
budget is prompt plus completion). When the engine is unavailable or errors,
the card shows the quiet "Notes start when the final transcript arrives."
line — there is no cloud fallback. The preview and the notes never leave the
phone and are never logged; they clear on capture stop, account change and the
controller's own conversation-gap clear. Once server running notes exist the
card shows those, as before.

## UI and hand-off

`LivePreviewController` is a separate model from `CaptureController.segments`
(never in LocalSegmentStore, the REST poll, `_segmentArrivals` or conversation
creation). Lines clear on capture stop/account change, and after a silence as
long as the conversation timeout; the conversation list's normal refresh shows
the record. Home's listening row reads the running session duration (the same
`LiveStartAnchor` start the live page counts from — local capture start is authoritative,
with the server episode start used only until a local capture start is known) in its tile, as whole
minutes under the live dot, and, for an admitted preview, the newest preview words on line two,
trimmed at the start so the latest stay visible. The live page's one-line header adds
"· since <time>" and a small Continues pill for the previous episode. The
Summary tab shows at most four notes (on-device, above, or the newest server notes) and a
"Live" card of the newest preview text (no speaker label, trimmed at the start) with an Open
transcript link. The Transcript
tab shows final segments first, then a "Live on this phone" divider, then the
preview lines the finals do not already cover (union of final audio-time intervals; timed words allow partial hand-off; the
volatile tail reads lighter), with one quiet "Final transcript about <N>s
behind" line replacing the uploading pill (failed/retrying uploads keep their
actionable pill). With no on-device engine the tab shows the calm "Recording
safely" card; its "Turn on live text" link appears only where the platform can
deep-link to its speech settings (a denied speech permission).

Audio feed timestamps are minted at the capture tap before bounded decoding,
so a queued PCM slice and a late recognition result do not shift the preview's
audio time to delivery time. iOS carries recognized word/phrase ranges; Android
14+ requests optional word-start timing; Whisper carries the window range.
Missing timing (including Android 13 recognizers) is kept conservatively. Final
coverage uses the server conversation origin, independently of the local capture
timer shown on Home. Preview words and timing stay display-only and in memory.

## Telemetry

`Live Preview Engine` (engine, reason, platform, os_major, bundled_installed),
`Live Preview First Word` (latency_ms from first fed audio), `Live Preview
Session Ended` (preview_words, preview_audio_ms, dropped_audio_ms), and
`Live Preview Notes` (engine, outcome, latency_ms, bullet_count — one row per
draft attempt, never any text). `Live Preview Verdict` is one row per socket that declared local_preview
(observational only): verdict (granted, refused, timeout, overflow,
socket_closed), platform, verdict_latency_ms from the request, hold_duration_ms,
held_frames and hold_timeout_replayed; `live-preview-verdict.sql` reads p50/p95
latency by verdict and platform and the timeout-replay rate. No text,
audio or locale leaves the phone. Preview-to-record disagreement is a follow-up:
it needs an on-device span match against the batch record.
