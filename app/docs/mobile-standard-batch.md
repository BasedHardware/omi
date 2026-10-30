# Mobile Standard pendant batch lane

Default off. Scope: Omi pendant Opus on the ordinary Omi STT path. Explicit
Transcribe Later, phone microphones, OpenGlass, custom/on-device STT, onboarding,
voice commands and installations with realtime integrations keep existing routing.
No UI or localization changes. ONNX Runtime requires iOS 15.1, so the deployment
minimum advances from 15.0 to 15.1; flag rollback does not undo that binary minimum.

## Existing pipeline and storage parity

`BleDeviceSource` removes the three-byte BLE transport header. Its original Opus
payload is the unit saved by `MobileBatchBuffer`, using the existing WAL layout:
little-endian uint32 length followed by the unchanged frame. No sample-rate
conversion or Opus re-encoding occurs in capture, persistence or upload.

Sealed files enter `LocalWalSyncImpl.addExternalWal`, `RecordingTransferCoordinator`,
`SyncProvider`, the existing `/v2/sync-local-files` upload, and backend-sync's
`decode_files_to_wav → VAD → STT → temporal conversation assignment` pipeline.
The existing job/content ledger makes upload retries idempotent. The existing
recording origin is retained for live-generation affinity. Batch files cannot
mix with streamed safety copies in one upload, preserving their evidence/dedupe
contract. Fractional starts and frame counts carry exact audio bounds. Nothing replaces
its cooldown, fair-use, account ownership, job polling or recovery behavior.

Today's realtime private-cloud path forwards decoded PCM (including silence while
there is a current conversation) from listen receiver to pusher. Pusher groups it
into five-second chunks and `upload_audio_chunks_batch` Opus-encodes it. Today's
sync playback path decodes WAV, converts to 16kHz mono PCM16 and re-encodes Opus;
VAD-selected conversation segments omit silence outside assigned segments. Raw
sync staging is temporary (one-day bucket lifecycle plus explicit cleanup).
Neither path permanently preserves the original pendant bitstream.

For this lane, upload admission archives EVERY original WAL file, including all
silence, before a 202, content-cache hit, decoding or VAD. Archive failure fails
acceptance, so the phone retains its retryable copy. Content-addressed objects
live under `raw-mobile-batch/{uid}/{sha256}/{original-name}.bin[.enc]` in the existing
private-cloud bucket. Enhanced protection encrypts original bytes. Account deletion
purges the owner prefix through the existing write fence. There is no application
TTL. The live production bucket lifecycle was read with `ro-prod` on 2026-10-14:
its Delete rules target only `merged/` (3 days) and `playback/` (30 days); neither
reaches the raw prefix. Existing conversation playback continues unchanged.
Training use remains subject to existing consent; retention is not training opt-in.

## Routing, durability and bounds

The same `ListenClientState` that emits `{foreground, transcript_visible}` selects
routing at the BLE packet boundary. A batch-owned packet goes to neither the live
socket nor the ordinary streaming safety WAL. Showing the transcript seals the
batch and sends only subsequent frames live; hiding it admits subsequent frames
back to batch. There is no replay of earlier batch audio into live STT. Existing
streamed safety copies keep their current server-evidence reconciliation. Socket
transcript expectations pause during batch ownership and restart with a fresh
deadline on live handback; BLE ingress recovery remains active.

A sidecar is persisted before the first append. Writes cross into the OS before
live delivery can be suppressed; fsync runs each audio-second and at seal. App
process kill retains complete frames. Power-loss exposure is at most one second.
Restart's existing WAL loader discovers unindexed journals, reconstructs lengths
from original bytes and retains torn tails before repair. Indexed files retain
job/retry state and never get a second WAL identity. UID partitioning is unchanged.

The lane stops admission at 256MiB (including retained torn originals) or 4,096
files across account buckets, or when free space is unknown/below the existing 512MiB reserve. Pending audio is never
evicted. New packets return to existing live/safety-WAL capture. Existing global
WAL reserve policy remains the last storage guard. Native capture when the Flutter
engine is absent keeps the existing capture/recovery route; this does not introduce
an independently authorized native batch recorder. A restarted engine reloads the
journal and gets a fresh server authorization before batching again.

Raw chunks seal at 60 audio-seconds, on visible/realtime demand, and after a
speech-to-silence transition with 2s hangover. A 500ms pre-roll is inherently
preserved because all frames are kept. Backend VAD/word-end assignment, not local
chunk edges, owns the existing 120s conversation silence boundary. Chunk files
are not separate user conversations merely because VAD seals them.

## VAD and battery-hillclimb

The bundled model is byte-identical to desktop's Silero ONNX asset (MIT license
beside the model). Mono 16kHz decoding is a VAD-only copy. Inference uses 512-sample
windows, 64-sample context, Float32 recurrent state and one native worker/thread.
The scheduling threshold is 0.35 (recall-oriented; desktop onset is 0.5). Errors
or a queue exceeding 32 frames return future capture to live, without discarding
already-owned batch frames. Local VAD never decides retention or suppresses backend
processing: silence-only files still upload on the 60s bound.

Reproducible host core benchmark:

```sh
DYLD_LIBRARY_PATH=/opt/homebrew/lib backend/.venv/bin/python app/tool/benchmark_mobile_batch_vad.py --seconds 300
# Actual Flutter/native binding (requires host libopus and plugin ORT dylib):
(cd app && OMI_OPUS_LIBRARY=/path/to/libopus.dylib flutter test tool/mobile_vad_native_benchmark_test.dart)
```

2026-10-14 arm64 Mac, ORT 1.19 core, 300s silent Opus: 7.08 CPU ms/audio-second,
7.63 elapsed ms/audio-second, 9,375 inference windows. The actual Dart/native wrapper
probe passed 60s of Opus and recurrent inference at 24.38 elapsed ms/audio-second. These are host baselines,
not physical-phone recall, power, thermal or suspension evidence.

For workspace `battery-hillclimb`, compare flag-off versus this UID cohort on the
same pendant/phone: CPU/audio-second (decode + inference), wakeups, BLE delivery,
network bytes, disk writes, upload latency, missed words and battery/hour. Include
speech/noise and screen-off traces. `inferenceTime`/`vadAudioSamples` expose wrapper
cost; the native-core benchmark separates model cost from Dart/platform overhead.
Physical iOS/Android power and noisy-speech recall qualification must precede ramps.

## Release and rollback (lead-owned)

1. Deploy this PR's backend-sync raw archive acceptance first; verify that silence
   is retained and a simulated archive failure leaves the phone's WAL retryable.
2. Deploy backend-listen capability handling. New clients on old listen servers
   remain live: a missing capability is false. Keep flags off during binary review.
3. On listen, `MOBILE_STANDARD_BATCH_ENABLED=true` plus
   `MOBILE_STANDARD_BATCH_UIDS=<dogfood-uids>` authorizes dogfood. Empty/default
   allowlist and `MOBILE_STANDARD_BATCH_PERCENT=0` authorize nobody. The percentage
   uses stable salted UID hashing; malformed percentages fail closed.
4. Admission also requires private-cloud sync and no enabled apps, audio webhook,
   developer realtime-transcript webhook or custom STT. Authorization renews via
   existing client-state control records every 60s; inventory reads are bounded to
   once/30s. Missing renewal expires client permission after 2min. The server can
   revoke on the next heartbeat; transcript visibility takes effect per packet.
5. Lead ramps to **at most 5%**, waits **at least 12h**, checks capture integrity,
   duplicates, backlog/disk, VAD recall and physical-phone battery, then expands.
6. Rollback: set `MOBILE_STANDARD_BATCH_ENABLED=false` (percent 0, clear allowlist).
   Existing batch files still archive/process through sync; retain the archive
   handler while any released clients can upload them. Never delete pending local
   files or permanent raw audio to perform a routing rollback.

No merge, deployment, release or App Store submission is performed by this lane.
