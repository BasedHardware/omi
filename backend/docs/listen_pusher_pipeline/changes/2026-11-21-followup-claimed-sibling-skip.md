# Follow-up siblings coalesce on the claimant's live privacy proof

## What changed

Projection follow-ups for ready async siblings on the same discovery page and binding used to run one
read-only session and privacy check per sibling, and 60% of them then ended `coalesced` behind the sibling
that owns completion (SCA-3508). Now the first ready sibling for a `(page, binding)` key becomes the
claimant and publishes its privacy proof as soon as its own `read_persisted` succeeds. Other ready siblings
wait up to `CLAIM_PROOF_WAIT_SECONDS` (5 s) for that proof. A sibling coalesces only through the existing
C1 check on that proof: it must come from the same Firestore client, cover the sibling's own input privacy
ids, be unexpired and match the live privacy version. On any miss, including no proof, a timed-out wait,
a changed or cleared page marker, or a refused claimant, the sibling runs its own full check exactly as
before.

The skipped path makes no writes; the claimant keeps every completion fence. If the claimant ends without
itself registering the completion attempt, skipped siblings are re-queued once. A sibling that is already
queued (ordinary or targeted recovery) or running is not queued again, and the ordinary launch never
overwrites a running segment's task, so one task owns each segment's custody accounting.

Known window: a waiting sibling decides on hints read up to 5 s earlier. Neither path writes, and the
durable outbox re-offers the row, so this affects outcome metrics only.

## Rollout and flags

`BATCH_PIPELINE_FOLLOWUP_CLAIMED_SIBLING_SKIP_ENABLED`, a kill switch, default on. `false` restores the
original per-sibling check order exactly. Rollback: set it to `false` on backend-integration (one config key),
or revert the code. Activation needs David's approval on the release issue (SCA-3508).

## Readback

After serving on backend-integration, over 24 h against the 24 h before:

- Follow-up origin reads per run fall by at least 35%, and `omi_batch_pipeline_projection_followup_outcomes_total{outcome="claimed_sibling_skipped"}` is above zero.
- Privacy refusals per audio-second stay steady.
- Follow-up `completed` per hour stays at or above baseline, and the oldest projection-drain age does not rise.

## Evidence

- Design and measurements: SCA-3508 (goal-owner `DESIGN: OK` `01a1fcfa`).
- Regressions: `backend/tests/unit/test_batch_pipeline_projection_followup.py`.
