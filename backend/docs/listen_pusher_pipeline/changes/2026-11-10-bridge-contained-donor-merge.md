# Contained-donor bridge merge

A sync donor summarized before its live target closed is refused forever by the
`already_processed` fence in `_finish_pending_live_bridge`. The Fable class 8
scoping measured 54 of 204 surviving duplicate pairs (26%, about 4.2k rows a
week) where the donor's recorded span is fully inside the live target's and the
only blocker is that fence.

`SYNC_BRIDGE_CONTAINED_DONOR_MERGE_ENABLED` is a three-value mode, and it ships
**default `off`**:

- `off` is the pre-change refusal, byte for byte. The processed donor is refused
  by the blanket `already_processed` fence; no span is compared and no assignment
  is attempted.
- `shadow` runs the containment predicate and the span comparison, emits a
  bounded counter and one log line, and returns the same refusal. It never
  assigns, tombstones, retracts notes or memories, and never emits an identifier
  or content. It also emits no capture-coverage `live_bind` comparison, so it
  cannot inject samples into that rollout's evidence, and a target read that
  raises counts the bounded `outcome=error` and still refuses instead of
  propagating. A donor the transaction would refuse before planning (a
  user-managed anchor or a manual speaker receipt) counts
  `outcome=donor_ineligible`, and a donor carrying unplaced speech counts
  `outcome=unplaced_donor`, so the dry-run count does not overstate eligible
  merges. This is the plan's dry-run count.
- `on` lets the bridge absorb such a donor. Containment is proven by placed
  transcript-segment spans on both sides (`segment_span`); a row whose only span
  is the `finished_at` wall-clock envelope never authorizes it, and that donor
  stays standalone. The merged predicate applies tolerance inward, so the
  configured tolerance is `0.0`: exact containment (the identical re-upload
  shape) passes, and a donor that extends even slightly past the target is
  refused. A stricter value can only refuse more.

Every other fence is unchanged: user curation, an open target,
`choose_live_overlap` (live provenance plus recorded overlap), privacy and size.
Partial overlap keeps the standalone row.

The bridge passes `absorb_contained_processed_donor` only when
`contained_donor_merge_enabled()` is true, so the irreversible effect is guarded
locally by the same parser that selects the mode. The assignment transaction
then re-proves containment on the rows it will merge, independent of
`merge_before_processing`. If the donor grew past the target between the bridge
read and the transaction, the whole assignment is refused with
`contained_donor_not_contained`; the bridge treats that as "not yet" and leaves
the donor visible. The existing donor retraction path then discards the donor's
standalone notes, copies its audio, and regenerates notes from the merged
transcript.

A contained donor whose speech is an exact repeat of the live target is still
absorbed: the repeat-only fast path in `assign_in_transaction` is skipped when
this call requested donor absorption, so the donor redirect is committed instead
of being acknowledged as a no-op.

Only the documented lowercase words select a mode (`on`, `true`, `yes`,
`enabled`, `shadow`). An absent, blank, unknown, misspelled or numeric value
resolves `off` in every capture-coverage mode, so a typo disables the merge and
never enables it.

Risk: in `on`, the donor's notes are rewritten from the merged transcript.
Containment bounds this to the same minutes and audio is copied rather than
deleted, so the loss is a note rewrite, not data loss. Rollback: set the mode to
`off`, which restores the pre-change refusal exactly. `off` is the default, so a
revert and a config rollback are the same state. Deployment belongs to the lead's
backend image train and the sync/enrichment hosts after review and merge.

Regression coverage: `tests/unit/test_sync_pending_live_bridge.py` covers a
contained donor merging in `on`, a legacy donor whose only span is the
`finished_at` envelope refused, partial overlap refused, an open target refused,
a donor with a 0.1 s overhang past the target refused, an identical-boundary
donor accepted at the configured `0.0` tolerance, a donor carrying unplaced
speech refused, a user-managed donor counted `donor_ineligible` in shadow, a
repeat-only contained donor still committing its redirect, the `off` refusal,
the `shadow` dry-run that never assigns or retracts and emits no capture-coverage
comparison, a shadow target read failure that still refuses with
`outcome=error`, the mode parser's fail-closed values, and the surface agreement
between the parser, the registry, the runtime-env manifest and the
deployment-setting classification.
`tests/unit/test_sync_live_overlap.py` and
`tests/unit/test_sync_cross_job_assignment.py` retain the ordinary assignment
and overlap contracts.
