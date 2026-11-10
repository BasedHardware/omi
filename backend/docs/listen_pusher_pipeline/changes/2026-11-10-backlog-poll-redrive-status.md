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

The single-unit regression in `test_backlog_state_machine.py` pins the returned
job API by rejecting additional wrapper reads after puts. This is stronger than
the Firestore rule: `FirestoreTransaction.put`, `patch`, and `defer_set` buffer
their values. `FirestoreStore.run` calls `flush` after the callback returns;
flush finishes privacy reads before issuing raw sets and updates. The recovery
fence and scheduler re-drive helpers do not bypass those buffering primitives.
Thus later units can safely read after an earlier unit's buffered puts.

Multi-unit coverage runs the real store, wrapper, scheduler, recovery fence and
flush against `StrictFirestore`, which raises on every raw read after a raw
write. Two- and three-unit polls exercise fresh raw reads after buffered puts,
including commit-fence reads. Mixed polls refuse active-token or receipted units
while queueing eligible siblings; the tests verify the refreshed status, queue
links, retained refused job and once-per-unit spent telemetry on and off.
Existing aborted commit, retry, operator and nightly tests retain their
accounting assertions. No production ordering change is needed.
