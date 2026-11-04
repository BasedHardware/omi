# Cap-hold batch hand-off: paced, and the hold keeps its audio until projection

Applies once legacy sync is `draining` or `dark` for an owner. That is the only time
`cap_hold_admission.admit_held` runs (`enabled_for`).

## What changed

- **Custody.** The hand-off saves the hold as `batch_admitted` and no longer erases its audio at that point.
  `cap_hold_recovery.finish_handoff` erases it later, once `cap_hold_admission.handoff_projected` reads the batch
  content ledger as `completed` with a valid all-success result.
  - A `partial` ledger, a missing intake or an unreadable store keeps the audio.
  - The redrive sweep discovers `batch_admitted` holds on a `handoff` page of `HANDOFF_PAGE` (50). It uses the
    existing `stt_cap_holds.state` collection-group index.
  - Reselecting a hand-off through `recover_selected` applies the same check.
- **Pacing.** Each hand-off first spends the held-recovery budget, `cap_recovery_pacing.reserve`, which until now
  only `_recover_row` used.
  - A hold larger than the burst is charged one full bucket. An `oversized` refusal would otherwise strand it.
  - A hold with nothing left to transcribe is not paced.
  - A deferral or refusal keeps the hold `held` with `next_attempt_at`, the same fields legacy recovery writes.

## Why

Before projection, the staged batch object was the only copy left after the hold was erased. The prod batch bucket
was provisioned with a bucket-wide `Delete age 7` and soft delete 0. The rollout lead confirmed this from the
provisioning script on 2026-11-01; that script is not in this repository. So a hand-off that stayed quarantined or backlogged past 7 days would lose its only audio. Measured 2026-11-01
20:05Z: 166 quarantined batch units are older than 7 days (Firestore COUNT, aggregates only).

Pacing: legacy recovery ran at a peak of 8.1 audio-h/h against the 60 audio-h/h limit over 7 days. Hand-offs skipped
the limit entirely, so a surge of consented backlog could have entered batch unpaced (bounded by DEEP priority).

## Rollout

No flag. It is inert until an owner's legacy sync leaves `on` (today: everyone is `on`). Rollback is a revert.
Contracts are unchanged: no env vars, wire fields or payloads.
