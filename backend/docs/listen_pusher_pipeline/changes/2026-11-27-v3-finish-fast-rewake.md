# v3 Finish: wake again in seconds after a moved or raced pass

Contract: [`CONVERSATIONS_V3_FINISH_FAST_REWAKE`](../../listen_pusher_pipeline.mdx).

## Why

The goal (David, 2026-11-27) is Finish to Home under 60 s at p90. A Finish writes to its recording at
least once more after the tap: the cut, and for a batch capture its fast transcript. When another
builder pass for the same owner is running at that moment, that pass either commits around the moved
recording (`source_moved`, about 15k passes per 6 h fleet-wide) or races (`raced`, about 3.9k per 6 h).
In both cases the Finish's own wake answered `busy` against the running pass. The Finish then waited
for the coalesced next-minute wake: a moved pass does not take its immediate re-pass. So a Finish that
overlapped another pass lost up to 60 s before its window was planned and its notes started.

## What changed

Only for a recording the owner finished in the last three minutes, a moved or raced pass also
schedules one wake about 3 s later. It is named by a 10 s slot, so one slot holds one follow-up per
owner. The next-minute wake is unchanged and stays the backstop. Live speech that moves a pass
behaves as before.

## Cost

- A moved pass whose loaded rows show no Finish reads at most 8 documents, Finish marker fields only.
  That is one read for a typical pass.
- A Finish that overlapped a pass adds one extra Cloud Task and one builder pass.
- There are no new writes, and no new model calls unless the earlier pass's outline was stale anyway.

## Rollback

Set `CONVERSATIONS_V3_FINISH_FAST_REWAKE=off` on backend-sync. The off path neither reads nor schedules.

## Readback

- Watch `omi_conversations_v3_finish_rewakes_total{reason}` after serving.
- The Finish-to-Home SLI (SCA-4489 readback) should show fewer Finishes in the 60 to 120 s band.
