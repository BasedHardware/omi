# Provider-route units join the ordered merge (2026-11-13)

## Why

Units for languages Parakeet cannot serve (Japanese is about 85% of them) take the provider route:
`provider_pending` → vendor call → `result_ready`. From 2026-11-05 almost none of them went further. On
2026-11-13, 1.68 million transcribed provider units were `result_ready` with `merge_pending` set, and 97–100%
of the units settled 6 hours, 1 day, 3 days and 6 days earlier were still unmerged. An unmerged unit has no
result-log row, so projection never builds its conversation.

Three gaps, all specific to the provider route:

- Nothing woke the owner's merge when a provider unit settled. The GPU pump drains the owner after each
  publication; the provider stage settled and returned. The only discovery left was the maintenance page of
  the 100 oldest `result_ready` rows, and two owners filled it.
- Provider settle wrote no `ready_at`. The head wait orders by `ready_at`, so a ready provider row could
  never commit past an unready head.
- Provider admission wrote no `fresh_capture`. Fresh-first could not apply, and an owner's old provider rows
  would have committed ahead of new ones.

## What changed

Behind one kill switch, `BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED` (on unless `false`):

- `provider_stt_admission.enqueue_in_transaction` stamps `fresh_capture` with the rule GPU admission uses
  (`FRESH_CAPTURE_LAG_SECONDS`).
- `ProviderSttStore.settle` stamps `ready_at` on a result, as `Scheduler.complete` does.
- The merge counts a provider row with no `fresh_capture` (admitted before the stamp) as catch-up. An
  owner's fresh rows commit ahead of that backlog, and the backlog follows under the existing catch-up
  depth hold as projection advances.
- The serving route wakes one owner drain after a delivery that settles a unit or ends it terminally
  (`utils/batch_pipeline/provider_drain.py`, `Serving.drain_settled_async`). The wake is coalesced per owner
  per process: a burst of settles costs one drain after 2 s and one after the head wait, and a settle during
  that round buys exactly one more round. At most 4 drains run at once per process. Past 4,096 live wake
  tasks an owner waits in arrival order instead of being dropped. The tasks are tracked background tasks.
- A provider row settled before the `ready_at` stamp waits from its intent's `settled_at`. When the
  `ready_at` probe finds no waiter, the merge reads the owner's earliest ready row once (one extra query per
  blocked drain) so those rows can also pass an unready head after the head wait.

The commit body, late marking, log chain, privacy fence and projection order are unchanged. No row skips
the head wait or the depth hold. The wake is an in-memory hint: if the process stops first, the owner is
drained by its next settle or by the maintenance page, as before.

## Rollback

Set the switch to `false`. New units get neither stamp and no wake. Rows stamped while it was on keep
`ready_at` and `fresh_capture` and stay eligible for the existing head wait and fresh-first; nothing needs
undoing.

## What to watch

- Share of provider units settled one hour earlier that are `committed` (near 0% before this change).
- Projection pending and fresh GPU-route time to episode: must stay flat.
- `firestore_transaction_contention operation=batch_pipeline_store ... outcome=exhausted`.
- `event=batch_provider_drain outcome=queued` (owner bound reached) and `outcome=retry`.

## Not in this change

Owners with a transcribed backlog and no new settles are not woken; releasing those is a separate, paced
job. The provider queue's dispatch rate and the per-owner document the merge serializes on are unchanged.
