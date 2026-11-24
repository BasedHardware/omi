# Register recording debt before restore visibility

Explicit restore now registers the idempotent batch recording obligation before
committing restore metadata. Registration receives `discarded=False` while the
stored row remains discarded. Privacy or registration refusal leaves metadata
unchanged and returns the existing retryable restore error. A metadata failure
leaves at most one obligation parked behind the discarded row; seal and partial
workers continue to refuse it until a successful retry restores visibility.

Open audio archives register immediately; the batch drain retains its upload
barrier. Proven-empty server-batch photo captures skip registration when audio
is closed, explicitly never received, and has no failed or pending upload or
audio evidence.

Discarded server-batch finalization closes fanout through
`complete_finalization_fanout` before returning its discarded disposition. The
worker then uses the normal completion path with terminal outcome `success`.

These fixes are on without a new flag. Hermetic coverage lives in
`tests/unit/test_restore_recording_obligation.py` and
`tests/unit/test_record_finalizer_discard_registration.py`; the latter exercises
the real completion transaction with StrictFirestore. The existing
[listen/pusher pipeline](../../listen_pusher_pipeline.mdx) remains the capture
and upload contract.

An orphan obligation (restore-origin job on a still-discarded row) is parked by design; the `record_pending` terminal transition is deferred to a follow-up; the signal is the `event=record_seal_refused outcome=orphan_parked` log line and the `omi_record_seal_orphan_parked_total` counter.
