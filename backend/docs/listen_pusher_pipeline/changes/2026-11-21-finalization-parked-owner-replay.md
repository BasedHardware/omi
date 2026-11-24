# Finalization replay probes owner-parked jobs instead of dead-lettering them

## What changed

Go rewrite lane 6c lets a conversation's finalization belong to another engine (Go). #25946 fenced Python's
finalization writers against rows owned elsewhere, and #25961 parked Python replay of a job whose smart-merge
survivor is owned elsewhere: the job keeps `finalization_waiting_on_owner` and the replay probe rechecks the
survivor's owner every `OWNERSHIP_RECHECK_INTERVAL` (1 h) until Python owns it again.

One path skipped that probe. The reconcile sweep's exhausted-requeue branch (`status` queued, attempts at the
maximum, at least one budget requeue, fanout incomplete) runs before replay and could terminalize and dead-letter a
parked job without asking whether its survivor had come back. Now:

- the sweep skips that branch when the candidate carries `finalization_waiting_on_owner`, so the parked job goes
  to replay, which probes the survivor in its transaction and only advances `reconcile_after_at`;
- `_terminalize_exhausted_requeued_job_txn` also refuses a job whose transaction snapshot is parked, covering a
  job that parked after the sweep read it.

A parked job that reaches the probe is not charged an attempt, not requeued and not dead-lettered. Unparked
exhausted jobs take the terminalization branch exactly as before.

## Reads and writes

Only parked jobs change path. On a sweep pass, a parked job's replay transaction reads the job; when its hourly
recheck is due it also reads the survivor row and, if the survivor is still owned elsewhere, writes
`reconcile_after_at` once. So each parked job costs at most two document reads and one write per hour, plus one job
read per other sweep pass. Previously the terminalize transaction read the job and wrote the terminal state plus a
dead letter. When the survivor is Python-owned again, the job clears `finalization_waiting_on_owner` and replays as
usual. No production row carries `finalization_waiting_on_owner` until lane 6c opens admission to Go, so today's
cost change is zero.

## Rollout and flags

No new flag. The behaviour is inert while the Go finalization cohort is empty. Slice C admission requires
#25946, #25961 and this change to be serving on every service that runs Python finalization (SCA-3578).
Rollback: revert the commit.

## Readback

After slice C admits its first cohort: zero dead letters for jobs that carried `finalization_waiting_on_owner`,
and parked jobs either resume after Python ownership returns or keep advancing `reconcile_after_at` hourly.

## Evidence

- Finding: omi-panel review of #25961, F1 (accepted); exact-head reviews on SCA-3551 and SCA-3578.
- Regressions: `backend/tests/unit/test_finalization_replay_exhaustion.py::test_exhausted_requeue_probes_parked_survivor`
  and the parked case in `backend/tests/unit/test_conversation_finalization_jobs.py::test_terminalize_refuses_fence_losses_and_committed_fanout`.
