# Projection: new owners before backlog owners (2026-11-13)

## What happened

On 2026-11-13 about 250,000 old results were committed in three hours. Projection drains one
owner at a time, `BATCH_PIPELINE_MAX_OWNER_DRAINS` (8) owners per process, from one FIFO queue,
and a turn runs up to 120 seconds. A sample of the pending results at 15:34Z: 74% captured over a
day earlier, 651 owners, the top 100 holding 82%. Those owners held the slots for two minutes a
turn and re-queued at the tail, so an owner with a handful of fresh rows waited behind all of
them. Of results committed 10-20 minutes earlier, 56% were unprojected (0.2% before). Half of the
waiting fresh rows belonged to owners with no backlog of their own.

## Change

`utils/batch_pipeline/projection_drain.py`, per process, no new read and no new state in the store:

- A newly requested owner's first turn runs `BATCH_PIPELINE_OWNER_DRAIN_FIRST_TURN_SECONDS`
  (default 15, about one step) instead of 120.
- An owner whose productive turn ends with rows left is a backlog owner. It keeps 120-second
  turns but waits in its own queue. Newly requested owners launch first.
- A backlog turn ends at its next step boundary when a newly requested owner is waiting and no
  slot is free: one backlog turn per waiting owner, never the last backlog turn running.
- If no backlog owner is running, one goes ahead after four rounds of new owners, so the backlog
  advances however many new owners arrive.

`utils/batch_pipeline/projection_discovery.py`: half of each assignment discovery page now comes
from the newest `BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS` (default 900) of commits.

- Why: discovery pages pending results oldest first, 100 rows a tick per process, and a GPU-route
  commit has no other wake. With 154,000 pending rows the fleet (35 processes) passed a given row
  about once in 15 minutes, which is the delay measured for fresh results.
- A second cursor walks from the window's floor to the newest row and starts again. A process's
  first pass starts at its stripe's point in the window. It uses the same query and index as the
  main cursor with a start point; the page is no larger, so a sweep reads no more rows.
- The main cursor gets the rest of the page and still visits every row.
- `0` restores the single cursor.

Order inside one owner is unchanged: the chain is still walked in commit order under the
assignment fence and the owner claim. An owner's fresh row behind that same owner's backlog still
waits for it.

## Off switches

`BATCH_PIPELINE_OWNER_DRAIN_FIRST_TURN_SECONDS=0`: one FIFO queue and 120-second turns, as before.
`BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS=0`: one discovery cursor, as before.

## What to watch

Share of results committed 10-20 minutes earlier that are unprojected, for captures under an hour
old; projected rows per minute (the backlog must keep draining); `owner_drain outcome=turn` lines
with `stop=yield`.
