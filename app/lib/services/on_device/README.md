# Mobile on-device overflow

Everything, including the enhanced iOS freemium provider, is behind the default-off
`mobile-on-device-overflow` gate. A debug build can override it with
`--dart-define=OMI_ON_DEVICE_OVERFLOW=true`. No remote flag is changed by the app.

The existing WAL / native batch writer owns audio. `on_device_only` excludes a WAL
from all cloud-audio drains; `omibatchoverflow` identifies native batch files in
the existing recordings directory. The account-owned WAL index commits results
before the conversation provider publishes them. Every asynchronous operation
is fenced by the WAL session generation; retries use a stable from-segments
`client_session_id`. Input is decoded in independent 30-second windows, with
word times from native engines and one unlabeled voice.

Apple SpeechTranscriber is preferred on supported iOS 26 devices/locales. Its
assets use AssetInventory reservations and OS installation progress. English
Parakeet TDT v2 uses FluidAudio revision
`19600a485baa4998812e4654b70d2bab8f2c9949` on iOS 17+. The app remains iOS 15:
a separate iOS-17 framework is embedded and dynamically loaded after an
availability check. Older/unsupported locales retain lower-quality SFSpeech.
Android uses the existing whisper.cpp tiny download (74 MiB). Parakeet is
approximately 443 MiB; there is no Omi package download for Apple speech.
Wi-Fi-only setup checks connectivity and cancels native setup if Wi-Fi leaves.
Apple ultimately manages its asset lifetime; there is no remove-model button
for OS-managed engines.

The default policy runs while charging. The existing UIDevice / BatteryManager
channel supplies power. Foreground checks run every 30 seconds, and Transcribe
Now runs the same pipeline. iOS BGProcessingTask requests external power for
charging runs and reschedules after completion/expiry; iOS decides when they
execute. Background execution and cold-launch behavior need phone acceptance.
Android uses WorkManager charging constraints and a retained headless Dart
entry point. A live UI engine is reused; UI startup fences a headless writer
before loading the shared WAL index. Workers have an eight-minute time budget
and retain audio for retry if stopped. Both OS schedulers are best effort. “As you talk” works from finalized
WAL/native batch files, so its latency includes the existing file rotation
boundary (native pendant batches currently rotate at 15 minutes).

Foundation Models availability is checked at runtime. Fresh sessions summarize
bounded UTF-8 chunks, then reduce notes to the projection limits. A local summary
uses the existing hash-bound `client_processing` contract with `runtime=local`.
Transcript text and the display projection are submitted to the normal
from-segments path; original audio stays on the phone. Unsupported devices use
cloud processing of transcript text. No live-STT hours are consumed by this
ingestion path. “Keep everything on this phone” creates transcript-only local
conversations and sends neither audio nor transcript nor summary.

`/reprocess` regenerates intelligence from the saved transcript; it does not
rerun STT. The cloud re-transcription action stays hidden for these recordings.
Phone energy, thermal behavior, unattended scheduling, phone throughput, and
long-session conversation boundaries remain unmeasured. Mac benchmark numbers
are disagreement with cloud, not truth-labelled accuracy.
