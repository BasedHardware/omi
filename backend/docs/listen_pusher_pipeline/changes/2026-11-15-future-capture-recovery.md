# Recover implausible future-clock sync uploads

V2 admits well-formed capture stamps strictly more than 24 hours ahead of the
server receive clock with `SYNC_FUTURE_CAPTURE_CLAMP_ENABLED` on by default.
This margin is 144 times the normal 600-second skew allowance. The ordinary
skew allowance is unchanged; stamps between that allowance and 24 hours still
return typed HTTP 400 `invalid_capture_time`. V1 keeps rejecting future clocks.

Recovery reuses `early_capture_clock_offsets`, VAD origin propagation, batch
packing, and the existing `capture_received_at` admission metadata. Original
files, filename timestamps, content identities, source-frame maps, lineage
proofs and custody checks remain intact. Decoded untrusted spans pack in raw
source order, ending at the frozen server receive time; raw clock gaps are
not silence or proof of wall-clock time. Normal siblings retain their existing
clock policy and historical lookback limits. Untrusted spans use backfill
pacing and do not forward client clock bounds to generation matching.

`capture_time_trust=untrusted` is frozen on normalized batch WorkItems and
persisted on recovered conversations in both processing paths. Temporal
assignment/overlap cannot connect distinct identities when either clock is
untrusted. Explicit targets, committed source-frame ownership and exact retry
identity retain their independent checks. Energy/time coverage skips recovered
inputs; frame coverage may skip only positively proven same-source samples.
There is no receipt-clock assertion that other phone audio is covered.

Deploy all processing/projection and recovery roles before admission services:
old processors do not understand future receipt-clock recovery or its trust
marker. Observe `omi_sync_capture_time_total{outcome="accepted_future_clamped"}`
and the content-free `event=sync_capture_time` log. Roll back **new admissions**
with `SYNC_FUTURE_CAPTURE_CLAMP_ENABLED=false` on admission services. Already
admitted tasks and holds continue using the frozen anchor and trust policy,
independently of the switch and the worker's current time. Do not remove these
processing safeguards while admitted work remains. Client retries are still
subject to their existing retry schedule; no immediate phone resend is claimed.

Contract: [sync admission](../../listen_pusher_pipeline.mdx).
