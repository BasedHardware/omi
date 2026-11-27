A keyed iOS transcript upload could spend its entire 25-second request budget
in notes and roll back its processing claim. The next upload reused the stored
transcript and restarted the same notes call under the same deadline.

Intake and replay use the DB pool. Only fresh or resumable keyed claims enter the
bounded enrichment pool, and the HTTP wait covers both pools. With the rollout
mode enabled, the admitted worker keeps its lease after the HTTP deadline and
finishes the same attempt with a separate processing budget. Pending retries
keep the device copy. Completed retries return the persisted conversation ID
even when the enrichment pool is full. A provider halt remains distinct from
the HTTP budget cut, and a retryable provider halt releases the retained claim
for readmission. If the process is terminated, the existing row and lease
provide the recovery boundary.

Rollout is off by default. Release must verify that the candidate can execute
after an HTTP response with no other request active, then qualify a cohort
before expanding. Measure valid-attempt 503 share, completed replays after a
budget cut, and two consecutive healthy route ticks in SCA-3846. Roll back the
cohort via the mode or revert the change.

The [pipeline contract](../../listen_pusher_pipeline.mdx#continued-ios-from-segments-processing)
lists the cohort controls and attribution tags. The route tests use a held notes
call to verify 503, claim retention, completion, and a 200 replay with one
processing invocation.
