# Count why record barriers refuse admission

`record_pending` jobs are dead-lettered `record_barrier_aged` after 14 days of
`capture upload/finalization barrier not closed`, but the refusal never said
which clause of `require_record_audio_barrier` failed. Cause rates for the aged
cohort could not be read without opening conversation rows (SCA-3748).

The barrier now attaches two closed-vocabulary attributes to the same plain
`ValueError` and message: `barrier_blocker` (the first failing clause:
`owner_other`, `status_not_completed`, `producer_tokens`, `upload_failed`,
`partial_invalid`, `audio_not_closed`) and `barrier_token_kind` (the least
releasable producer token in `record_upload_sessions`: `bare`, `podless`, `pod`,
`abandoned`, `other`, or `none`). The blocker label uses its own fixed priority
(owner first). The decision, the exception type and text, every catch site and
every log line are unchanged. Classification never raises: on a malformed row the
attributes are omitted and counted as `unknown`.

The record drain counts them, from the row admission already read:

- `omi_batch_record_barrier_refusals_total{blocker,token_kind}`: refusal attempts
  (one row retries many times; not distinct records).
- `omi_batch_record_barrier_aged_total{blocker,token_kind}`: committed
  `record_barrier_aged` transitions, once each, beside the unchanged
  `omi_batch_record_dead_letter_total`.

No Firestore reads or writes are added, and no identifiers are exported. An
error that lacks the attributes counts as `unknown`. A metrics failure never
changes the drain.

`RECORD_BARRIER_CAUSE_METRICS` defaults on. `false`, `0`, `off` or `no` stops
only these two counters (the kill switch).

Readback: `sum by (blocker,token_kind)(increase(omi_batch_record_barrier_aged_total[24h]))`
gives the per-cause split of the daily aged inflow. It is the evidence for the
token-lease ramp (`RECORD_TOKEN_LEASE_MODE`, SCA-1765).
