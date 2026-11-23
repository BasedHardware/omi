# Held-account conversation deletes keep the data

## What changed

`DELETE /v1/conversations/{id}` now honors a legal hold without blocking the user (P7 Decision 4: a hold
blocks physical disposal, never product access). Before, a default `cascade=false` delete never read the hold
and physically erased the record, audio and frames, and a held `cascade=true` delete answered
`409 account_gate_busy`.

For an account with an active hold (`legal_holds/{uid}` `active=true`), both now answer 204 with
`X-Omi-Delete-Outcome: held_deferred`. One transaction writes the tombstone with `legal_hold_deferred: true`
and marks the row `deleted`, so every product read drops it at once. Nothing is erased.

- A cascade delete keeps its erasure obligation (`erasure_armed: true`). The existing obligation runner
  finishes it `held`, re-checks hourly and erases after release.
- A non-cascade delete arms no obligation (`erasure_armed: false`, unless an earlier accept already armed
  one), because the runner only performs cascades. `omi-support-ops hold release` lists these for follow-up;
  their erasure is owed after release (a `hold erase-deferred` command is tracked on SCA-3339).
- The hold is on the data-plane client and cannot join the tombstone transaction, so a non-cascade held
  accept re-reads the hold after commit. If it was released in between, the request falls through to the
  normal delete, and the marker is cleared only once that delete has succeeded.
- A held retry marks an existing tombstone and never un-arms erasure.

Unheld accounts are unchanged. The developer API conversation delete (`routers/developer.py`) does not check
holds; that is a tracked follow-up.

## Rollout and flags

Ships on, behind the kill switch `LEGAL_HOLD_DEFER_SINGLE_DELETE` (`ops_kill` in `config/feature-flags.yaml`,
default on). `false/off/0/no` restores the previous behavior: a held non-cascade delete erases and a held
cascade delete answers 409. Two accounts are held at the time of writing, so the user-visible change is
confined to them. Each delete adds one direct `legal_holds/{uid}` read.

After serving, `event=conversation_delete outcome=held_deferred` should appear only for held uids, and
`outcome=held_released_during_delete` should be rare.

## Evidence

- PR [#25883](https://github.com/BasedHardware/omi/pull/25883) and SCA-3339 (design, measurements, follow-ups).
- [Delete-route regressions](../../../tests/unit/test_conversation_delete_accept.py): held cascade, held
  non-cascade, release during the delete, failed delete after release, retries, kill switch.
- Operator runbook: [support-operator-cli.md](../../runbooks/support-operator-cli.md).
