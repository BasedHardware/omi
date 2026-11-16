# Fresh recordings have reserved seal-repair capacity

A Ready record-seal-worker may be deliberately idle. The production values keep
that worker disabled while the repair CronJob owns IO. The CronJob's persisted
recency sweep can spend hours walking older pending captures, and ordinary job
discovery waits 30 minutes. Neither supplies a bounded fresh-recording attempt.

The active CronJob now polls an independent newest-first, two-hour job window,
starting at 60 seconds of enqueue age. Fresh work can borrow up to half of the
existing row slots from ordinary execution capacity. It never shrinks either
discovery leg: pending jobs retain half the worker budget, including their
urgent-deadline priority and ordinary-job reserve, and conversations retain the
other half plus unused job capacity. The checkpointed initial worker group
starts first; queued fresh rows then take returned ordinary slots. Empty fresh
capacity is lent back to backlog with a 90-second row limit, while the initial
urgent/ordinary job leg retains its full configured row budget. New head
pages interrupt the frozen recent-tail pass. Attempts retry after two minutes;
90-second fresh row limits prevent slow proofs pinning those slots for 270
seconds. All children still use isolated processes, bounded IO and canonical
producer inventory, retained-tail, privacy and transactional seal rechecks.
No missing proof becomes authority, no obligation is discarded, and no provider
backlog release control or GPU image changes.

A successful fresh seal also sets the pending job's `available_at=0` in the same
transaction, placing it before ordinary intake retries. The job remains pending
until normal admission validates and stages it. Failed proof/privacy checks
leave the wake and seal unchanged. The wake intent is included in the plan digest.
Intake certifies its own retry clock with `record_intake_retry_at` only while
fresh repair and dead-letter handling are enabled. Claiming removes a previous
marker; repair rechecks the live clock inside the seal transaction and preserves
active or unmarked future claims. With fresh repair or dead-letter handling off,
ordinary deferrals add no marker. Previously stored markers are harmless to old
readers and are removed when a newer intake replica claims the row.

The chart changes production scheduling: minute ticks replace five-minute ticks,
with `Forbid`, pod resources, worker count and 1500-second run budget unchanged.
The continuous Deployment remains as configured; this change does not enable it.
No new Firestore index is required. Each fresh poll reads at most two 128-row
metadata pages, under a ten-second total deadline. It never uses hash-order
fallback when the recency index is unavailable; the legacy slots continue.

Contract and kill switch: [retained seal proof rules](../../listen_pusher_pipeline.mdx#retained-seal-proof-rules).
Rollback for new Jobs: `recordSealRepair.freshEnabled=false` and
`recordSealRepair.schedule="*/5 * * * *"`. The release owner stops an existing
Job if immediate rollback is required. No data migration or job redrive is needed.

Hermetic coverage: `test_record_seal_fresh_lane.py` covers ordering, frozen-tail
inflow, budget reservation, bounded retries, error containment, short deadlines
and reaping. `test_record_seal_repair.py` covers atomic fresh wakes and privacy
refusal. Existing seal/intake and Firestore query/index guard suites remain gates.
Production latency, image behavior and successful notes within five minutes must
be checked by the release owner after integration; no deploy is part of this lane.
