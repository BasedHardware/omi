# Dark batch-live orphan repair

Operation: `batch-live-inprogress-orphan-repair-v1`. Owner: dazheng.
P0 freeze exemption: lead2 bus 8c0822. Both `QUIET_EMPTY_EXIT_ENABLED` and
`BATCH_LIVE_ORPHAN_REPAIR_ENABLED` default **off** in `config/refactor_modes.py`.
This fileset changes no serving config, IAM, timer, dispatcher or live.py.
No production execution is authorized by this implementation handoff.

## Plan, review, approve one page

A separately authorized operator uses the existing approved runtime, encryption
key and explicit serving admission-policy map (see
[record-seal repair](../record-seal-repair/README.md)). Do not use a human ADC
login. Dry-run can use `ro-prod`; apply requires `prod-operator`. Staging should
first exercise `plan_repair` / `apply_repair` with an explicit dev store and
synthetic captures. The production CLI refuses emulator credentials.

Prepare a private scratch directory with mode 0700. The server-flags JSON holds
only the allowlisted admission inputs, collected from all positive-traffic roles
and checked for agreement, including effective ramp overrides. Never print it.
Each invocation discovers at most 128 document identities in name order. The
collection-group query filters the owner marker but uses `.select(())`: it returns
only document paths, with no document fields or capture content. After privacy
authorization, it checks canonical job existence inside the candidate transaction.
Eligible registrations repeat that read through canonical admission. Refused rows count toward the page cap. No new index
is required; discovery reuses `record_seal_nojob.discover`.

```sh
# Within the approved operator environment, with the repository backend on PATH:
python backend/scripts/repair_record_orphans.py --limit 128 \
  --server-flags-file /Volumes/Ephemeral/scratch/private-orphans/flags.json
```

Default dry-run performs **no data or filesystem writes**. Add `--next-file`
explicitly to save a private next-page cursor when pagination is needed. Owner
authority and subsequent allowed-capture authority walks request snapshots,
preventing optional cache-token minting in dry-run. Its report contains counts, closed
exits, a plan digest, and `sealed_received_audio_seconds`: the sum of verified
retained sample spans for sealed+received rows, excluding gaps and trimmed
overlaps. `sealed_received_stt_seconds` separately sums the canonical unit
durations, including any silence padding within units.
This estimates STT volume; it is not a vendor cost quote. Privacy-skipped and
unproved rows cannot contribute verified seconds. A zero value does not prove
those rows contain no audio. SDK output and exceptions are suppressed. No UID,
conversation ID, object path or private cursor is printed. The only filesystem
write is the explicitly requested private next-page cursor, never a plan or user content.
Without `--next-file`, even dry-run creates no cursor file.

Review counts, audio volume, privacy skips and failures before approval. Retain
the exact input cursor; copy the reported digest to the approved invocation:

```sh
BATCH_LIVE_ORPHAN_REPAIR_ENABLED=true python backend/scripts/repair_record_orphans.py \
  --limit 128 --apply --approve-plan-sha256 REVIEWED_DIGEST \
  --server-flags-file /Volumes/Ephemeral/scratch/private-orphans/flags.json \
  --next-file /Volumes/Ephemeral/scratch/private-orphans/next.json
```

For subsequent pages add `--after-file` naming a **different** private cursor.
Advance input only after settling the page. Pace pages manually; do not run
parallel applies. Reconstructed plans and storage generations must match the
approved digest. A changed row, job, proof, consent or privacy generation refuses
writes; get a fresh plan and approval. Empty page resets the cursor to the
beginning; repeat whole passes to revisit parked rows and concurrent arrivals.
This is a bounded operator tool, not a cron or a new standing scheduler.

## Dispositions and exits

- `register` / `registered`: stale in-progress, both seals,
  received audio, no tokens, no upload failure and no canonical job. Bounded
  archive-required listing (4096 objects) and the canonical generation-pinned
  retained decoder prove up to 128 units. One transaction stamps window/content,
  moves the sealed capture to `completed` (required by the existing record
  admission barrier), and creates the canonical `record_pending` job. Exit:
  **normal batch pipeline**, with its existing compute/funding/STT gates.
- `delete_empty` / `empty_deleted`: archive closed, explicit received=false, no
  window/content/audio metadata, no tokens/failure, **empty storage proof**, and
  the existing quiet cutoff + identity + expired lease. The existing lifecycle
  deletion transaction rechecks the approved row, job absence, owner consent and
  canonical privacy authority. Exit: **noise/discard terminal**. Owned audio
  cleanup preserves all raw audio and GCS objects.
- `upload_pending`: skipped; exit **producer-token lease repair**. This tool never
  removes producer tokens or clears upload failures.
- `privacy_skipped`: skipped with no data mutation and no storage proof; exit
  **operator re-run after consent**. An owner with private cloud sync off or a null preference is never processed.
  An absent preference keeps the canonical enabled default; no new opt-in rule
  is introduced. Account deletion, migration, protection and privacy
  generation gates remain canonical and live in the write transaction.
- `already_registered`: exit **normal batch pipeline**; never overwrite a job,
  including an empty job document. `not_candidate`: exit **existing lifecycle
  owner**. A disappeared row is an idempotent no-op.
- `barrier_mismatch` and `lease_unknown`: counted, skipped, **parked for operator review**
  (`operator_review`). Quiet checks with no bounded base exit retire their obligation
  and leave the row for this review; repeated wakes cannot settle unknown custody.
- Proof/read/write error, storage audio on a
  received-false row, state change, or empty storage on a received-true row:
  **park for operator re-run**. The private in-memory entry records a closed
  `last_failure_code`; the aggregate report names the exit. Privacy refusals do
  not create a new row-level failure marker. Received=true is never changed to
  false and never deleted, even if storage is empty. An unclosed archive is parked;
  this tool does not manufacture a close barrier. A never-received, closed
  archive may use proven-empty cleanup even without the separate record seal. A live lease exits via the
  **quiet check after lease**.

Registration trusts both closed custody barriers and no producer tokens, just
like normal batch admission; a missing old session does not strand retained
audio. Only delete-empty requires a known expired recording lease.

In dry-run and apply, owner consent, deletion/erasure and protection authority
are checked before any conversation-row or canonical-job document read, including
the final deletion transaction. Next, a Firestore field mask reads only the capture's
`uses_custom_stt`, `private_cloud_sync_enabled` and `data_protection_level`.
A capture-level refusal returns `privacy_skipped` without reading the full row,
the job or storage. Only an allowed capture proceeds to those reads. This projection
gate repeats for storage reauthorization and canonical registration reads.
Every eligible apply reauthorizes before storage and re-proves object spans, then
rechecks row, job absence, consent, privacy generation and switch in the same
transaction as the write. Lost responses are safe to retry; registration uses a
deterministic job identity and deletion leaves the existing session tombstone.
Storage proof is immutable-generation evidence, not permission to delete objects.

## Rollback and acceptance

Set `BATCH_LIVE_ORPHAN_REPAIR_ENABLED=false` or stop the exact owned operator
process; already-committed rows/jobs follow the normal pipeline. No apply can be
undone by deleting audio. Keep `QUIET_EMPTY_EXIT_ENABLED=false` until the lead has
accepted staging repair and drained the backlog. Then the lead may separately
approve that flip and watch `listen_quiet_check_empty_exit_total`, orphan counts,
and pipeline age. Unbounded quiet refusals retire their obligation and leave the
row for this repair; #24893's state machine should absorb that standing exit. #24953's pending-job drain
is disjoint: this repair requires job absence. #24866's due/dispatch is untouched.

Local synthetic tests and trace do not establish recovered transcripts. Staging
plan/apply, authorized row-level transcript completion and Home clearance are
operator acceptance work, intentionally not run by this implement lane.
