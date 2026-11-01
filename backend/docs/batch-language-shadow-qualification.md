# Batch language shadow qualification

The batch language gate needs matched self/vendor decisions on the same bounded
audio before enforcement. Existing GPU shadow does not run that comparison;
raising its percentage alone produces no language qualification pairs.

`BATCH_PIPELINE_SHADOW_LANGUAGE_ONLY=true` replaces the GPU-shadow upload handoff
with a pair-only qualification task. It uses the existing salted owner selection
from `BATCH_PIPELINE_SHADOW_PERCENT`, excluding current batch owners, BYOK and
native record owners. The first canonical decoded unit of each new immutable
legacy upload is sampled. Its effective input language matches batch intake:
only an explicit single-language preference supplies a declared language;
otherwise the input is `multi`. Declared languages do not require a probe.

Qualification accepts only whole uploads within eight files, 2MiB encoded,
4MiB codec-aware decoded working audio, 60 total audio seconds and4,096 frames.
The shared backfill validator applies this stricter resource profile before
reservation/copy and again immediately before canonical decoding. Oversized
uploads are counted and skipped in full; no truncated prefix is silently
substituted for a canonical unit. PCM rate/width and Opus maximum decoded
frame size participate in the expansion proof. Ordinary backfill bounds and
serving uploads are unchanged. This restricted sample population must remain
explicit in the rate and coverage review.

There is no GPU transcription/diarization, artifact upload, serving job, route,
projection, transcript or allowance/usage write. Legacy owns its original files
and processing. Only private temporary copies belong to the task; canonical
decode closes after the first unit and temporary files are removed on every
outcome. The upload waits at most one second for the tracked best-effort offer.
A late offer may fail to copy an already-cleaned legacy file; it never changes
legacy custody or retries an external call.

The qualifier runs self-LID and the vendor detector against identical PCM WAV
bytes, bounded to the first30s, with their existing finite timeouts and no
client retry. It ignores the language-enforcement cohort, so even a future
enforced cohort cannot silently stop the vendor half of qualification. The
existing shadow-call kill switch remains authoritative.

## Safety and spend bounds

The hourly attempt setting is
`BATCH_PIPELINE_SHADOW_LANGUAGE_PROBES_PER_HOUR`: default500, maximum500, and
zero/malformed denies. One durable reservation permits at most one self call
and one vendor call for that immutable upload. Reservations survive duplicate
delivery and UTC-hour rollover; a lost commit response is refusal, not permission
to repeat. There is also a fleet-wide minute cap of `ceil(hourly_cap/60)` and
two occupied slots with120s authorization deadlines. Expiry denies further
external calls but **does not free occupancy**: a decoder/request still running
keeps its slot until its completion path releases it. A crashed owner therefore
causes HOLD rather than overlapping detector requests. Inspect aggregate occupied/
expired counts when reservations stop; the lead/operator may reset stale control
slots only after qualification is off and the old owners/requests are proved
drained. Never recycle solely because a timer elapsed. Consumed probe intents
remain consumed. A duplicate late release cannot revoke another occupant.

Every reservation transaction checks privacy; each external detector call
checks current privacy/generation and ordinary batch funded dispatch again.
No GPU availability or idle-worker rendezvous is required. Actual self-LID
uses the existing Parakeet service and its queue; this does not authorize a new
GPU node or raise the16-node batch limit.

Only hashed intent keys, reservation timestamps and aggregate budget counts
are stored, in `batch_pipeline_{stage}_shadow_lid_probes` and
`..._shadow_lid_spend`. No raw owner/conversation identifiers, audio, transcript
or detector outputs are persisted. Both tables have7-day expiry fields; apply
their TTL declarations from `deploy/batch-pipeline/retention.json` before
activation. These are qualification-control tables, independent of serving jobs
and the existing GPU-shadow jobs.

## Candidate and measurements

The shared backend/worker and Parakeet long-probe support floor is now0.985,
the same conservative floor as short probes. The observed shadow candidates
`self=en,P(supported)=0.9757,vendor=vi,confidence=0.982,duration=30.0s` and
`0.9700/0.969/16.7s` are rejected by this candidate. Neither observation proves
which detector is correct. A stricter floor is not a complete quality proof;
measure supported-language leakage and multilingual/short-clip coverage.

Counters use the separate `surface=batch_shadow` on
`omi_stt_language_gate_shadow_total` and `omi_stt_language_gate_self_total`.
The eligible denominator is both routes available and `vendor_conf=ge90`.
Dangerous direction is self Parakeet while the vendor bucket is unsupported.
Report batch, batch_shadow and prerecorded separately, with duration/language
buckets. `omi_batch_language_shadow_total{outcome}` counts eligible, declared,
not_reserved, oversized, matched, unmatched, no_unit and error outcomes. Eligible is an
offer count; only reserved matched results qualify. Missing series are unknown.
Do not count duplicate uploads, pool the prerecorded population, import an
old-threshold window, or treat a silence-only interval as qualification.

For zero failures in2,995 independent pairs the one-sided95% binomial upper
bound is at most0.1%. Owner clustering, first-unit selection and missing language
buckets remain limitations; retain the lead's coverage review. Any dangerous
event holds qualification. This gate does not replace T4 route-proof coverage.

## Operator packet and dated ramp

Lead ruling8b33ec approves the source work; **the lead merges and approves
activation, op1 applies**. Source merge alone does not enable qualification.

1. Co-deploy compatible CPU intake and batch-worker support floors, reconcile
   current serving identities and apply the new qualification TTL declarations.
   Parakeet's reported threshold can follow in its normal roll: the backend
   independently derives the safety rule from its numeric output.
2. Prove synthetic qualification, unchanged user-visible state, duplicate and
   budget guards before production. Then select10% shadow owners with
   language-only mode, cap500/hour, two slots. Batch admission percentage and
   language enforcement percentage are separate and remain operator-owned.
3. Measure matched rates and normal LID/legacy latency for15min. Increase
   shadow selection to100% only if the measured matched rate is below the
   dated target and privacy, cost, error and queue gates remain clean. The
   hard attempt/concurrency caps never increase. Extra batch-worker nodes:0.
4. Target2,995 fresh candidate pairs by **2026-10-27 12:00Z**, with zero
   dangerous events and explicit bucket coverage. Required rate is
   `2995 / hours_remaining`; at22:00Z start it is213.93 matched/hour. At500
   attempts/hour that needs a measured match fraction≥42.79% plus adequate
   selected traffic in the bounded-upload population. Report the oversized offer
   fraction; do not import the old unrestricted arrival rate. The old batch6h
   match fraction256/362≈70.72% is a scenario
   only; transferring it gives353.59 matched/hour and8.47h, not a promise.
   A qualifying percentage cannot be inferred from a0%-serving baseline.
   Lead checks the first15min and hourly ETA; if100% selection still misses
   the target, report HOLD with the measured bottleneck instead of relaxing
   the gate or enlarging spend.
5. After accepted qualification, the existing language cohort5→25→100 with
   ≥30min per step still requires wrong-language, empty-ASR, upstream-error
   and multilingual-share checks. Stop pair-only qualification after this
   ramp and no later than **2026-10-27**; lead owns that dated decision.
   Keep compatible workers while previously admitted self-LID units drain.

At the [vendor language-detection list rate](https://www.modulate.ai/api-pricing)
of $0.01/sample-hour (checked2026-10-26), the
worst-case bounded vendor input is500×30/3600=4.167 sample-hours per hour:
**$0.0417/hour or$1/day** at full cap, excluding CPU/store and the existing
self-LID service.2,99530s accepted probes alone are about$0.25. These are
planning ceilings, not measured vendor spend; unavailable/low-confidence calls
consume the same attempt budget. Record actual vendor usage and self-LID
queue/compute measurements before booking costs or savings. No per-day cloud
dollar amount is established by request counts.

Rollback qualification with `BATCH_PIPELINE_SHADOW_PERCENT=0` on upload hosts
(or cap0); new reservations/calls stop, tracked tasks clean their own copies,
and consumed intents never retry. Do not set language-only mode false while
leaving an unintended GPU-shadow percentage active. Enforcement rollback is
the existing language percentage0; held/admitted custody remains preserved.
