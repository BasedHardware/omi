# Legacy Home: a kept sync piece held for notes is a Processing row

Prod, 2026-11-18. A batch-only live capture stayed `in_progress` for over 30 minutes
because speech never paused for 120 s. Its phone-WAL sync piece already had speech and a
server-minimum title. Its notes were held: `sync_processing_hold.held=True`, and
`sync_bridge_pending` named the open live row.

`is_settling_fragment` hides every completed server-minimum row until two hours after
`finished_at`. A growing piece keeps moving `finished_at`, so on the legacy Home list the
piece stayed hidden for as long as the capture lasted. The live row is not listed either,
so legacy Home (App Store 1.0.592 and older, Android) showed neither row.

## Change

`fragment_visibility.held_for_notes` names the piece. It applies to a completed
legacy-layer row (no `recording`, no `v3_derived`) with intake's `sync_relevance='keep'`
and `has_content`, whose quiet hold is `held` or whose live bridge has a target.
Discarded, rule-discarded, blocked, below-floor, already-summarized and merged rows never
qualify. The wait
counts from the hold's `last_content_at`, falling back to `finished_at`, and ends at
`SETTLING_MAX_HOLD_SECONDS`, so a lost obligation cannot keep a row processing.

The exemption is opt-in (`show_held`). Only `GET /v1/conversations` passes it, for the
default Home view of an owner for whom `conversations_v3_enabled(uid)` is false. That is
the same gate `/v1/conversations/live` uses to tell the app it is a v3 account. There,
`is_settling_fragment` lets the piece through and `home_step.classify` returns
`writing_notes`. Every other reader, filtered views and v3 owners keep the previous
behavior. The Home list's slim select gains `sync_processing_hold`; the other evidence
fields were already selected.

`keep` only means the deterministic rules did not classify the piece as filler. A piece
that already carries a summary receipt never qualifies, because a standalone run leaves
`sync_bridge_pending` in place. On a Redis error the v3 gate reads false for its 120 s
cache window, and `/v1/conversations/live` then tells the app to show legacy Home too.

The 10-minute `sync_bridge_pending` window is unchanged.

## Several pieces for one live row

All are listed. When the live row closes, the bridge merges every unprocessed piece into
it (`utils/sync/bridge.py` `_finish_pending_live_bridge`). Released Home clients fold every
`transcribing`/`writing_notes` row of a day into one Processing row
(`app/lib/pages/conversations/home_rows.dart` `foldProcessingRuns`).

## Not changed: notes before the live row closes

When a processed piece meets the closed live row, the bridge refuses it, because
`SYNC_BRIDGE_CONTAINED_DONOR_MERGE_ENABLED=off` in prod. Assignment also keeps processed
rows as protected identities. So the live row's own transcript would make a second Home
row for the same speech.
