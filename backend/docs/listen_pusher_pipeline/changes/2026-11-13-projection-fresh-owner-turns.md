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

`utils/batch_pipeline/projection_discovery.py`: each assignment discovery tick also reads up to
half a page from the newest `BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS` (default 120) of
commits.

- Why: discovery pages pending results oldest first, 100 rows a tick per process, and a GPU-route
  commit has no other wake. With 154,000 pending rows the fleet (35 processes) passed a given row
  about once in 15 minutes, which is the delay measured for fresh results.
- The read has no cursor. Each tick it starts at a random point in the window and reads oldest
  first. Replicas draw their points independently, so they can land on different rows. A process
  offers a row from this read once per run; the entry is kept for two windows, longer than the row
  stays there. That memory is per process: a restarted process can offer a row once more. A row
  that stays pending is then left to the main cursor, which offers it only when it reaches it.
- Rows read here count against the page: the main cursor gets the rest (at least half). The page
  holds no more rows than before. The tick makes one more query than before.
- A main cursor that has not reached the newest row for 30 minutes starts again: one time in
  eight at the oldest pending row, otherwise at a uniform random point between it and now. Without this, when rows arrive as fast as a cursor
  reads, the rows before every process's start point wait for a wrap that never comes. That gap
  exists before this change too, at twice the arrival rate.
- `0` restores the single cursor and removes the 30-minute restart.

Order inside one owner is unchanged: the chain is still walked in commit order under the
assignment fence and the owner claim. An owner's fresh row behind that same owner's backlog still
waits for it.

## Off switches

`BATCH_PIPELINE_OWNER_DRAIN_FIRST_TURN_SECONDS=0`: one FIFO queue and 120-second turns, as before.
`BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS=0`: one discovery cursor and no restart, as before.

## What to watch

Share of results committed 10-20 minutes earlier that are unprojected, for captures under an hour
old; projected rows per minute (the backlog must keep draining); `owner_drain outcome=turn` lines
with `stop=yield`.
