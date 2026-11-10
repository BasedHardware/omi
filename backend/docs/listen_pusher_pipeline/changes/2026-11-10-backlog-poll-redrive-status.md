# Poll re-drive snapshots without post-write reads

PR: [#25012](https://github.com/BasedHardware/omi/pull/25012). The retained
re-drive and custody contract is in the
[backlog state-machine runbook](../../runbooks/backlog-state-machine.md).

The scheduler's transactional re-drive helpers now return the updated job
alongside the once-per-unit spent signal. Status polling builds its refreshed
response from that value, including the copy verified by the recovery fence,
without another transaction read after staging writes. Queue append also
finishes its queue, frontier and control reads before staging its writes.

The operator and nightly entry points keep their boolean acceptance contract
and publish spent transitions only from the successful transaction's result.
Refused re-drives retain the held status and long poll interval. No flag or
default changes; the fix applies on the existing re-drive paths.

The regression in `test_backlog_state_machine.py` uses a transaction double
that raises `ReadAfterWriteError` on every get after a put or patch. It checks
refreshed poll status for held and historical dead jobs, below and at the held
budget, with telemetry enabled and disabled. Existing refusal, aborted commit,
retry, operator and nightly tests retain their accounting assertions.
