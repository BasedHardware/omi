# Hide the empty stubs left by the listen rollover storm

The 2026-11-16 22:06Z listen rollout left about 43k `batch_live_v1` rows
`in_progress`. Each received a first frame but never committed audio, so no
existing path could close it:

- empty cleanup needs `server_batch_audio_received=False`;
- orphan repair parks rows that are received but unclosed;
- the quiet check had already retired.

The cause is fixed in #25599.

The reversible no-speech terminal gains one class, `empty_stub`. It requires:

- both retained-object listings empty;
- the exact empty row shape;
- no close barrier, seal, WAL handoff or producer;
- no live recording-session lease.

It applies the same hidden terminal (`status=completed`, `discarded=true`,
`terminal_no_derived_effects`, marker with the prior fields) with zero speech
and zero audio. Nothing is deleted, and the ledger undo restores the row.

`--only` binds a single class into the plan digest. A stub drain therefore
cannot close `no_speech` captures, and the reverse also holds.

Owner decision: David, 2026-11-17, approved hiding or deleting these stubs.
This change only hides them.

Rollback: `NO_SPEECH_TERMINAL_ENABLED=false` stops new closes, and the per-page
ledger undo restores closed rows.

Tests: `backend/tests/unit/test_no_speech_empty_stub.py`.
