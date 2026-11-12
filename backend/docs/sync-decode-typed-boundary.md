# Sync decode typed boundary

The strict sync decoder (`utils/batch_pipeline/capture_decode.py`) is the
shared CPU reader for decoded sync WAL uploads and held WAVs. It feeds the
batch GPU worker's `fetch_decode` stage, intake admission, cap-hold
admission (`wav_units`) and the missing-input repair lane.

## Contract

Every fault the strict sync decode raises is deterministic on the pinned
stored bytes (or on frozen admission arguments): the same `.bin` frames
re-parse, re-canonicalize and refuse identically on every attempt. The batch
decode family's doctrine is that such faults carry the family type
`StagedAudioInvalid` (a `ValueError` subclass), the same way
`decode_pcm16_wav`, `with_context` and the retained-audio decoder wrap sites
do. Downstream boundaries read the type, never the message:

- every parse/canonicalization refusal raises `StagedAudioInvalid`;
- a container wave itself refuses to open (garbage RIFF, truncated header,
  0 channels, 0 sample width) is the container fault, not the shape fault;
- non-finite or out-of-horizon unit ceilings are refused before any bytes
  are read;
- a bundle whose decode drops any uploaded frame is the preservation fault.

Because the type is a `ValueError` subclass, every existing
`except ValueError` caller keeps catching these faults unchanged. The
observable change is at the typed boundaries: worker evidence vocabulary,
admission repair holds and cap-hold recovery classification now name the
fault family instead of collapsing the cohort into anonymous
`ValueError`/`wave.Error`/`OverflowError` tokens that production books as
unclassified errors (the bare-`ValueError` decoder-fault cohort behind the
`error_class=ValueError stage=fetch_decode` sensor signature family).

## Verdicts

| Fault | Type | Message |
| --- | --- | --- |
| Stream header shorter than 4 bytes | `StagedAudioInvalid` | `truncated sync audio frame` |
| Zero/oversize/short frame | `StagedAudioInvalid` | `invalid sync audio frame` |
| Stream with no frames | `StagedAudioInvalid` | `empty sync audio` |
| Unopenable or truncated container | `StagedAudioInvalid` | `invalid sync audio container` |
| Declared shape outside 1-2 ch / width 1-4 / 8-48 kHz | `StagedAudioInvalid` | `unsupported sync PCM format` |
| Payload the conversions fold to nothing | `StagedAudioInvalid` | `invalid sync PCM payload` |
| Decode dropped an uploaded frame | `StagedAudioInvalid` | `sync decode did not preserve every uploaded frame` |
| Ceiling non-finite, <= 0, or > 7200 s | `StagedAudioInvalid` | `invalid dedicated capture-unit ceiling` |
| Canonicalization of a hold is empty | `StagedAudioInvalid` | `empty held audio` |

Admissible shapes canonicalize through the documented pipeline: bias width-1
to signed, widen to PCM16, fold stereo to mono, resample to 16 kHz. The
parity grids (`test_sync_canonical_pcm_grid_*.py`,
`test_sync_frame_stream_grid.py`, `test_sync_decode_units_grid.py`) pin the
full declared-shape verdict surface and the exact pipeline outputs.

Failure-Class: FC-sync-decode-fault-anonymous-at-typed-boundaries
