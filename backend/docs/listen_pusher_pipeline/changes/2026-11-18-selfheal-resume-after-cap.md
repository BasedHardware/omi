# Self-heal resumes after the last row it acted on

Follow-up to `2026-11-18-recovery-admits-placeholder-stub.md`. After that change admitted about
1,200 stale placeholder stubs, the legacy self-heal scan drained them at about one row a minute.
Each tick considers at most `MAX_ELIGIBLE_PER_TICK` (25) eligible rows and admits at most
`MAX_HEAL_ADMISSIONS_PER_TICK` (10). The status-only scan then resumed at its scan tail, up to
`MAX_SCAN` (2000) rows later. So eligible rows past either cap were passed over until the cursor
completed a whole rotation of the `in_progress` population.

Changed, with no flag and every cap unchanged:

- In heal mode the legacy scan stops at the eligible cap and resumes after the 25th eligible row, as
  the content-due scan already did.
- When the admission cap or the verification capacity defers a row, the tick resumes after the last
  row it acted on, so the deferred rows come first on the next tick. If capacity deferred the first
  row, the cursor stays where it was.
- A row the admission transaction refuses counts as acted on. A prefix of permanently refused rows
  is passed once per rotation, and the cursor always moves forward past the rows a tick acted on.

Detect, nudge and dry-run ticks keep their previous cursor behavior.

Evidence: `tests/unit/test_selfheal_sweep.py`.
