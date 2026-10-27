# Offline recording export

`AudioPlayerUtils` selects local WALs in timestamp order, resolves platform directories and
playback-cache paths, then sends a data-only job through `compute`. It opens the platform share
sheet on the UI isolate only after the worker returns a complete file. Single-file playback and
sharing use the same decoder as whole-recording export.

`wal_wav_worker.dart` owns byte traversal, length-prefixed disk framing, memory-frame conversion,
native Opus initialization/decoder disposal and PCM WAV writing. Disk input is streamed and PCM
output is buffered to 256 KiB, so decoded memory does not grow with recording duration. A frame
may cross read chunks; complete frames before a truncated tail retain the existing behavior.
Missing local files, corrupt Opus packets and unreadable WAV artifacts retain the established
skip behavior. Native-library, file-read/write and incompatible-format failures propagate.
Zero-byte payloads contain no audio and are skipped before native Opus can synthesize concealment
samples; decoder typed-list views retain only their selected sample range.

Each job owns a unique scratch directory. Whole-recording jobs delete decoded scratch parts on
success and failure, without deleting input WALs or reused playback caches. `WavCombiner` reads
only the fixed 44-byte PCM header, validates available payload length, streams compatible parts
and publishes by renaming a completed staging file beside the destination. Failure removes
staging and preserves a previous complete destination. The shared header rejects RIFF overflow.

Single-file results and final share files remain in platform temporary storage for playback or
receiving apps. Concurrent recording shares have different output directories. Do not delete a
complete share file merely because the share sheet returns: the receiving app may read it later.
This export pipeline does not change upload status, capture buffers, recording timestamps,
account ownership or automatic transcription.

## Implementation and verification checklist

- [x] Disk and memory-backed decode plus combination run in the worker.
- [x] Main-isolate platform selection/share calls are covered through the real channel adapter.
- [x] Ordering, corrupt/missing parts, chunk boundaries and empty input have behavioral coverage.
- [x] Scratch cleanup, failed streams, prior-output preservation, retry and concurrent shares have
  behavioral regressions; a failed export never invokes the share channel.
- [x] A CPU-bound decoder fixture demonstrates that UI timer events run during worker execution.
- [x] The native integration uses the real plugin loader/Opus decoder, a 3,601-second synthetic
  Opus/PCM recording and UI pumping; it also exercises fresh-isolate single-file native decode.

Hermetic coverage (including protected spine contracts):

```sh
bash app/test.sh test/unit/audio_player_utils_test.dart test/utils/wav_combiner_test.dart
```

Native simulator/emulator coverage (from `app/`, using the documented dev/local_dev setup):

```sh
bash scripts/validate_mobile_build_config.sh --flavor dev --profile local_dev
OMI_APP_PROFILE=local_dev flutter test integration_test/offline_recording_export_native_test.dart \
  -d <simulator-or-emulator-id> --flavor dev --dart-define=OMI_APP_PROFILE=local_dev
```

This uses synthetic files in the isolated development app, no backend or customer audio. A
simulator run is native codec/export evidence, not a physical-device or receiving-app benchmark.
Current-commit CI and release state belong in the PR; mobile distribution follows merge.
