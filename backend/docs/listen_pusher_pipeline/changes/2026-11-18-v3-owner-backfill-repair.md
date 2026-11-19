# 2026-11-18: per-owner v3 backfill and repair runs (default off)

Runbook: [Backfill and repair (per owner)](../runbooks/conversations-v3.md#backfill-and-repair-per-owner).

## Why

The v3 backfill on main could not be used for spot checks or repair. It used a fixed 30-day window
and refused any owner with more than 128 conversations in it. Its conversion cleared the legacy
`structured` notes, and it had no undo. Its notes ran under the silent-backfill recovery trigger. That
trigger keeps every row, skips speaker resolution and meeting context, adds recovery guards and only
writes notes above 600 words, so backfilled notes did not match live v3. Deleting a backfilled row
also armed the audio purge on the legacy row it came from.

## What changed

- An operator plans a run for one owner and a configurable window (default 2 days). The plan cuts
  the window at five-minute silences, the live hard boundary. A Firestore run ledger records each
  partition's counts and outcome, and a dedicated `conversations-v3-backfill` queue runs one
  partition at a time.
- Derive passes take their own `backfill-builder` lease and a `v3_backfill_process_pending` notes
  marker, so they never make the owner's live builder busy and never ride the live queue or sweep.
- Notes for backfilled rows use the live `CAPTURE_END` path. `process_conversation` withholds only
  derived effects (memories, tasks, apps, folders, vectors, notifications, duplicate-capture links,
  created webhooks) for rows that are `v3_derived` and `backfilled`.
- Legacy rows keep their notes. The conversion is recorded per field in `v3_backfill_prior`, and
  `undo` restores it exactly. Re-derive mode rebuilds backfilled rows in place.
- A legacy manual stop (`relevance_decision.trigger == client_finalize`) becomes the v3 manual end.
  Discarded and imported legacy rows are not converted.

## Rollout

Nothing runs until `CONVERSATIONS_V3_BACKFILL=on` and an operator plans a run. The queue is declared
in `backend/deploy/ops/{prod,staging}.yaml` and the config-train creates it. The first run is the
coordinator's spot check on a named owner, after a dry-run.

## Rollback

`CONVERSATIONS_V3_BACKFILL=off` stops new steps; `undo --run` restores an owner's run.
