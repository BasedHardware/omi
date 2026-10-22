# Committed capture coverage

`coverage.py` is the authority for committed source-frame ranges. Its public
`record`, `admit`, and read-only `query` APIs use `models.capture_coverage`.
`admit` does not reserve an in-flight provider attempt. Commit-time assignment
uses `frame_proof.py` to prevent a second transcript when another writer won.

Each authenticated user's ledger is partitioned by every `CaptureKey` field:
capture root, channel, string clock epoch, device, and recording session. A
missing optional field is a value, not a wildcard. Producers must populate the
same fields consistently. Frame ranges are half-open. Only complete committed
frame interiors enter the ledger; wall clocks and speaker labels never prove
coverage. The existing S1 union, subtraction, validation and WAV materializer
remain the interval and source-position implementations.

`sync_coverage.py` checks decoded WAL maps before VAD/STT and records surviving
segment receipts after assignment. `batch_coverage.py` carries compact source
runs across packing in authenticated encrypted audio context and rechecks at
projection. Unsupported resampling or insufficient provenance retains audio.
Serve bypasses the legacy clock/energy trim. Stored held pieces recheck before
each new paid intent; partial proof delegates to deterministic hash-verified
source slices in one lease-fenced checkpoint. Cached provider results keep
their reconciliation path, and child slices inherit the paid attempt limit.
`dedupe.py` shares the bridge/incoming fallback: committed frame proof first,
then unambiguous conversation-wide text clock estimation and narrow matching.
Known uncovered positions never fall through to text deletion. Speaker and
owner labels do not participate.

All paths read `CAPTURE_COVERAGE_MODE` through `config.refactor_modes`. Default
shadow computes decisions and records committed evidence while legacy output
serves. The explicit digest/percentage cohort may serve while the host stays
in shadow. Off disables ledger I/O; serve uses new decisions globally.

The authenticated GET `/v2/capture-coverage` accepts `capture_root`, `channel`,
`clock_epoch`, optional `device_id` and `recording_session_id`, and repeated
`start`/`end` query parameters paired by index. At most 32 ranges and 360,000
requested frames are accepted. Rate limiting is per authenticated user, 60 per
minute, and fails closed if its backing limiter is unavailable. The bounded
ledger rejects excess evidence rather than filling gaps or silently discarding
proof. It caps each track document at 256 conversation/origin records, 2,048
merged intervals, and 600,000 serialized bytes.
