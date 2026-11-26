# Batch speakers on conversations-v3 rows; final-pass evidence floor; clock-conflicting units

Contract: [batch conversation speakers runbook](../../runbooks/batch-conversation-speakers.md). No flag, no env
change: every change below is on by default inside the existing batch speaker authority.

## What was wrong

Measured on the consenting owner's own account (read-only, writes refused, 2026-11-26) with the pipeline lab's
speaker diagnosis (`testing/pipeline_lab/speakers/prod_diagnose.py`):

- **v3 rows never got batch speaker resolution.** A conversations-v3 row copies its recordings' projected
  segments, but the staged units' projection receipts name the recording. `load_reference` answered
  `skipped_merged` for the row, so both the original-evidence resolver and the whole-conversation final pass
  refused: 24 of 24 fresh v3 rows, and none of the owner's 200 newest rows carried a resolved speaker status.
- **Clock-conflicting units refused the whole pass.** 9 of 24 refused `conflicting capture clocks`: the same
  recording staged as two units whose clocks overlap with different audio (correlation about 0 at every lag
  within 0.5 s).
- **An unevaluated final-pass voice revoked earlier labels.** A voice the final pass could not name (under the
  5 s evidence floor, or no compatible print) was stamped `no_match`, which `apply_speaker_resolution` treats as a
  decision and clears the resolver's owner label with. On short v3 rows this erased correct owner labels.

## What changed

- `load_reference(..., source_ids=)` accepts receipts naming the row's own `v3_recording_ids`; any other owner is
  still a merge or a shared unit, and the privacy fence covers the row and its recordings.
- A source unit carries only the row's own speech: samples outside its own segments' words (unit clock, padded
  0.25 s, joined across pauses up to 1 s) are silenced, and batch identity turns are clipped to them. Each source
  recording must exist, be unlocked and still claim the row; its claims and deleted spans are fingerprinted before
  inference and re-checked after. No recurring profile is learned from source units.
- v3 rows get a fresh final-pass obligation key once, so rows settled as `skipped_merged` are not closed forever.
- A unit whose clock overlaps placed audio with different samples is appended after the native timeline instead
  of refusing; labels map back by segment id.
- A final-pass voice naming never evaluated is `unknown` (keeps existing labels); only an evaluated, rejected
  voice is `no_match`.

## Evidence

- Lab scenarios `speaker_owner_and_person_finish` and `speaker_owner_absent` (public LibriSpeech voices, production
  receipts): `scenario compare origin/main --worktree --metric speakers` gives final pass `skipped_merged` ->
  `success`, owner recall 0 -> 1, named accuracy 0 -> 1; replay only, in CI.
- Owner account, 24 fresh v3 rows, read-only: resolver `resolved` 0 -> 19; final pass refused 24 -> 9 (all clock
  conflicts, since fixed). Owner recall against silver truth on the words every arm labeled: production 0.000,
  resolver with the fix 0.757 at owner precision 1.000.
- Unit tests in `test_batch_final_pass.py` and `test_batch_final_pass_lifecycle.py` cover each change, the
  sibling-speech mask, a revoked source, the obligation key and a three-unit append.

## Not covered

Sync-off v3 rows (`utils/batch_pipeline/voice_evidence.py` reads `database/batch_voice_evidence.load_reference`)
keep the old receipt rule. Live listen naming is unchanged.
