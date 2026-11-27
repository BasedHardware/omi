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
schedules a wake about 3 s after it releases its builder lease, so the follow-up does not answer
`busy` against that pass. Recency is read from the Finish stamp (`v3_finish_requested.at`) when one
is stored, else from `finished_at`. Each Finish recording gets at most two re-wakes: the task name
is the owner, the recording and an ordinal (1 or 2), with no clock in it, and Cloud Tasks refuses a
name it already holds. A Finish whose passes keep racing, for example on a deterministic commit
guard that also answers `source_changed`, stops after two and falls back to the minute wake. The
next-minute wake is unchanged and stays the backstop. Live speech that moves a pass behaves as
before.

## Cost

- A moved pass whose loaded rows show no Finish reads at most 8 documents, Finish marker fields
  only, newest moved recordings first. That is one read for a typical pass.
- At most two extra Cloud Tasks and two builder passes per Finish, plus at most two refused
  task creates per later racing pass inside the 3-minute window.
- No new writes. Outline calls: none when the Finish's input did not change, because a raced pass
  keeps its paid outline on the lease (`save_outline`) and the follow-up reuses it; at most one per
  re-wake when the input did change, which the minute pass would otherwise have paid.

## Rollback

Set `CONVERSATIONS_V3_FINISH_FAST_REWAKE=off` on backend-sync. The off path neither reads nor schedules.

## Readback

- Watch `omi_conversations_v3_finish_rewakes_total{reason,outcome}` after serving; `capped` should stay
  a small share of `scheduled`.
- The Finish-to-Home SLI (SCA-4489 readback) should show fewer Finishes in the 60 to 120 s band.
