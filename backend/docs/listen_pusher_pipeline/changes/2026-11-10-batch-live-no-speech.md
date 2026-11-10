# Reversible no-speech terminal for stale batch-live captures

Operation: `batch-live-no-speech-v1`. Owner: dazheng. Authority: relay-cl1 GO
320bdf (David's orphan proposal; ff0427 item 3). This fileset changes no
serving config, IAM, timer, dispatcher or `live.py`. No scheduled or automatic
apply exists, and no production execution is authorized by this handoff.

## Why

The 2026-11-10 VAD census (`data/run-2026-11-08-pipeline-refactor/orphan-tiers-2026-11-10.md`)
found 99.2% of a 385-row stratified sample of stale `status=in_progress`,
`record_lane_owner=batch_live_v1` captures had under ten seconds of strict-VAD
speech, with 0.000 speech hours. They are near-empty captures. The existing
orphan repair would park them, not recover anything, and paid STT would spend
money on silence. David's ruling: spend $0 on transcription and give them a
reversible terminal "no speech" state.

## State and exit

The state is named `no_speech` in the `no_speech_terminal` marker. The close
stamps the reviewed hidden terminal shape: `status=completed`,
`discarded=true`, `terminal_no_derived_effects=true`, plus the marker. The
marker records the prior `status`, `discarded` and `terminal_no_derived_effects`
values (present/absent and value) and the strict-VAD measurement. Its exit is
`restore_no_speech` (operator undo), which restores those fields exactly and
deletes the marker. Nothing deletes a conversation row or an audio object.

`status=completed` is the existing terminal shape used by the reviewed
`stuck_backfill` noise close; `terminal_no_derived_effects` is the established
signal that suppresses delivery, summary, finalization and episode effects.
`discarded=true` is the indexed Home hide and is reversible. The row is
excluded from the in-progress and processing queries by its status, and from
Home by the indexed `discarded == false` filter. Export/compliance readers with
`include_discarded=true` still see the preserved row.

## Classification

A row is eligible only when all of the following hold:

- `record_lane_owner=batch_live_v1`, `status=in_progress`, older than two hours,
  not deleted/discarded/locked/merged, no finalization job, no upload session or
  upload failure, and the canonical owner/capture privacy gates pass.
- Its retained raw-live objects decode through the repository's
  `source_audio.read_reference` (owner path, generation, checksum, application
  decryption, omi-wal Opus decode) and the concatenated real PCM has less than
  ten seconds of `offline_pcm_speech_segments` speech; or
- There are no raw-live objects and the existing archive-required listing
  (`list_audio_chunks(require_archive=True, include_raw=True)`) is empty.

Rows that fail decode or privacy checks are left untouched and counted. Rows
with legacy chunks but no raw-live objects are `retained_audio_unmeasured` and
left untouched: the tool never claims silence it did not measure. The repair's
`list_audio_chunks` empty result alone is not proof of no retained audio,
because it skips gapped packs; the direct raw-live listing is the proof.

## Delivery

`backend/scripts/mark_no_speech_orphans.py` is a sibling of the orphan repair
with the same contract: dry-run default, digest-bound plan, paced, newest-first,
counts-only output, private cursor and private rollback ledger. Apply and undo
are refused when `NO_SPEECH_TERMINAL_ENABLED` is false. The tool requires
`prod-operator` for apply and allows `ro-prod`/`prod-operator` for dry-run; the
evidence shows audio GETs need `prod-operator`. Discovery uses the new
`record_no_speech_newest` collection-group index
(`record_lane_owner`, `status`, `created_at DESC`, `__name__ DESC`).

## Rollback

Set `NO_SPEECH_TERMINAL_ENABLED=false` to stop new applies and undos. Run the
tool's `--undo` mode with the private ledger to restore any closed page exactly.
No audio or row deletion is involved, so rollback never needs a storage
operation.

## Verification

Synthetic strict-transaction tests cover the classification threshold,
byte-for-byte close/undo, refusal of foreign or changed rows, no deletion path,
privacy/decode rows left untouched, Home hiding, and the kill switch. No cloud
access, staging apply, production dry-run or Home acceptance is claimed by this
implementation lane.
