# queuetest

Real-Postgres helpers for running a declared queue kind on real workers.

| Rule | Test |
| --- | --- |
| A scheduled post-commit claim fault is saved, replayed with four workers, and survives a store restart | `TestSavedClaimFailureScheduleRestartsSeveralWorkers` |

Use `OpenScheduled` to run a `fault.Schedule`; `Restart` closes and reopens the same database
while keeping the injector cursor. A fixture is a seed and point list stored under
`internal/queue/testdata/fault-schedules/`.
