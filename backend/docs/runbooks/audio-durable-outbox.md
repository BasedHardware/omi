# Durable live audio custody

`AUDIO_DURABLE_OUTBOX_ENABLED` is on by default. Only the literal `false`
selects emergency legacy behavior; empty or malformed values retain custody.
The rollout lead owns merge, coordinated listen/pusher rollout, alert activation
and any emergency rollback. This change does not authorize a production write.

## Lossless PCM storage (new writes)

`AUDIO_CUSTODY_PCM_COMPRESSION_ENABLED=true` is the default. Listen and pusher
share the same optional PCM16 representation helper before immutable commit.
It tries mono PCM windows from 32,000 bytes through 16 MiB, with one encoder
slot per process, one FFmpeg codec thread, a two-second cap for each
encode/decode subprocess, and a 0.4-second shared budget for the whole optional
step (0.08 s of it reserved for the decode check). Busy capacity, missing
FFmpeg, timeouts, an exhausted budget, invalid output or any sample mismatch
retain original PCM. Windows below the minimum, PCM8, native Opus, multichannel
originals and packs without a complete PCM identity proof keep their current
representation.
Only an independently decoded, byte-identical FLAC saving at least 5% is used.
Compression applies regardless of speech classification: quiet speech is safe.

This changes storage representation, not retention. No historical objects are
read, rewritten, expired, deleted or moved between storage classes. Mobile
original files and PCM projections are unchanged. Capture frame byte offsets
and hashes describe original decoded PCM; media SHA-256 describes the stored
plaintext container. Existing readers already support both formats. Custody
still requires both immutable object generations and the manifest before ACK.
A retry in the same configuration reuses content-addressed media and manifest;
a retry crossing a writer-switch change can leave both valid representations,
so neither representation may be treated as deletion eligibility.

Rollback: set `AUDIO_CUSTODY_PCM_COMPRESSION_ENABLED=false` on listen/pusher
through the release lane. This stops new compression without disabling custody
or reads of existing FLAC. No reader-first deployment or data migration is needed.

Release acceptance: deploy listen and pusher through their owned trains, record
each serving source SHA plus a fresh `omi_audio_pcm_storage_total{result="flac"}`
increment, and observe one full 30-minute window. Confirm custody commit/failure,
raw read checksum/decode/coverage failures and commit latency versus the prior
window; no new integrity failures, no sustained increase in custody errors or
latency. If errors or latency regress, disable compression on that surface.
The encoder outcome counter distinguishes `disabled`, `ineligible`, `busy`,
`deadline`, `not_smaller`, `encoder_error`, `mismatch`, and `flac`. Input/saved
byte counters count admitted encoding attempts, including retries before commit.
Input bytes exclude disabled, ineligible and busy candidates; saved bytes count
only savings verified by byte-exact decode for each attempt. These are not billed
storage savings. Use committed `omi_audio_archive_bytes_total{codec="flac"}` and
bucket growth to corroborate savings; an absent eligible PCM cohort is UNKNOWN,
not a successful savings measurement. No >90% silence claim follows from this.

The `omi_audio_pcm_storage_seconds` histogram times the optional representation
step, including fallback. Outcome counters initialize at zero. Check absolute
mismatch/over-budget counts as well as deltas to catch a first event before
the first scrape. The shared budget bounds the whole optional step at 0.4 s
(plus process startup/cleanup), so `deadline` means the pack did not fit the
surface's CPU rather than a codec fault; busy capacity falls back immediately
rather than queueing another encoder. Each `deadline` also records the shared
resilience fallback
`omi_fallback_total{component="audio_custody",from_mode="flac",to_mode="pcm16",reason="timeout",outcome="degraded"}`,
so the skip is visible outside the domain counter. A disabled surface still
times every call, so its p99 measures the disabled path and is not evidence
about encoder latency.

Release reads the following PromQL through the project's managed Prometheus
API with `ro-prod`, separately for `job="prod-omi-backend-listen"` and
`job="prod-omi-pusher"`, always with `namespace="prod-omi-backend"`. Pin the
evaluation time and use windows entirely after the serving readback. Replace
`JOB` with that one job, never a fleet-wide sum:

```promql
sum(increase(omi_audio_pcm_storage_total{namespace="prod-omi-backend",job="JOB",result="flac"}[30m]))
sum(increase(omi_audio_archive_bytes_total{namespace="prod-omi-backend",job="JOB",source="live",codec="flac"}[30m]))
sum(increase(omi_audio_pcm_storage_input_bytes_total{namespace="prod-omi-backend",job="JOB"}[30m]))
sum(increase(omi_audio_pcm_storage_saved_bytes_total{namespace="prod-omi-backend",job="JOB"}[30m]))
sum(omi_audio_pcm_storage_total{namespace="prod-omi-backend",job="JOB",result="mismatch"})
sum(increase(omi_audio_raw_read_total{namespace="prod-omi-backend",job="JOB",result=~"checksum_mismatch|decode_error|coverage_mismatch|decrypt_error"}[5m]))
sum(increase(omi_audio_custody_failures_total{namespace="prod-omi-backend",job="JOB"}[5m])) / clamp_min(sum(increase(omi_audio_custody_commits_total{namespace="prod-omi-backend",job="JOB"}[5m])), 1)
histogram_quantile(0.99, sum by (le) (rate(omi_audio_pcm_storage_seconds_bucket{namespace="prod-omi-backend",job="JOB"}[5m])))
sum(omi_audio_pcm_storage_seconds_count{namespace="prod-omi-backend",job="JOB"}) - sum(omi_audio_pcm_storage_seconds_bucket{namespace="prod-omi-backend",job="JOB",le="5.0"})
```

Before rollout, record the same custody-failure fraction over the immediately
preceding 30-minute window as `baseline_failure_fraction`. Wait for one full
five-minute window of the new serving state before evaluating guards. Disable
compression on that surface for any new sample mismatch or raw integrity
failure, or any observed optional step over five seconds. After at least 100
timed calls, disable it if optional-step p99 exceeds 0.5 seconds in two
consecutive complete five-minute windows. Also disable for a custody-failure
fraction above `min(0.01, baseline_failure_fraction + 0.001)` in two consecutive
complete windows. These are conservative compression rollback triggers; keep
custody itself on. Release records the actual observations and trigger.

The full 30-minute acceptance window must have at least 100 representation
calls, ten verified FLAC outcomes and positive committed FLAC bytes per surface,
with no rollback trigger. Insufficient traffic/metric coverage is UNKNOWN.
Verified FLAC outcomes prove actual byte-exact decode checks before write;
zero raw-read errors without successful read traffic cannot certify a separate
playback exercise. Record that distinction. The histogram measures the added
codec step, not total custody-commit latency. Total commit latency remains UNKNOWN
unless an independent metric is identified; record downstream backpressure
separately with existing custody meters. Net dollar savings remain
uncredited until actual eligible byte savings and compute cost are measured.

### Optional codec stage diagnostics

`omi_audio_pcm_storage_seconds` times the whole optional step, so it cannot say
which child consumed the time. Two diagnostic histograms split it. They are
diagnostics only: they never feed the p99 guard above, they are not an
acceptance denominator, and they cannot pass a canary.

| metric | labels | meaning |
| --- | --- | --- |
| `omi_audio_pcm_storage_stage_seconds` | `stage={encode,decode}`, `child_result={success,timeout,error}` | wall time of one child that actually ran |
| `omi_audio_pcm_storage_stage_timeout_overshoot_seconds` | `stage={encode,decode}` | only for a child killed by its own timeout: full stage wall time beyond the granted timeout |

`child_result` is that child's own outcome, not the call's terminal decision: a
`success` encode on a call that later keeps PCM still reports `success`. `error`
is the existing handled `OSError`/`SubprocessError` path. The overshoot span
contains startup, cleanup and any thread descheduling or timeout overshoot, so
it is an overshoot diagnostic, not a pure process-start cost and not a
wall-clock bound.

Both metrics use fixed buckets `(.005,.01,.05,.1,.25,.5,1,2)`. A pod exposes 88
new series here with the pinned client (`prometheus-client==0.21.1`):
eight pre-created children (`stage_seconds` 2x3,
`stage_timeout_overshoot_seconds` 2) at 11 series each -- eight buckets, `+Inf`,
`_sum`, `_count`. A client that also emits `_created` per child would make that
96; the owner's ceiling of 96 series per pod covers both. Children are
pre-created and never observed at
zero, so `increase()` can see a first burst without a fabricated sample. The
cost is two timestamp reads per invoked child -- stage start, and stage end
taken as the child returns or raises, before any byte comparison or saved-byte
accounting -- plus one local sample append, plus the flush after the slot is
released; disabled, ineligible and busy calls allocate nothing and observe
nothing. No per-request, content, size or account label is attached.

Read them with the same pinned endpoints, window and selector as the guard. The
per-surface scrape job labels are `pusher-metrics` for the pusher surface and
`backend-listen-metrics` for listen; keep `namespace="prod-omi-backend"` and
replace `JOB` below with exactly one of those, never a fleet-wide sum:

```promql
histogram_quantile(0.5, sum by (le) (rate(omi_audio_pcm_storage_stage_seconds_bucket{namespace="prod-omi-backend",job="JOB",stage="encode"}[5m])))
histogram_quantile(0.99, sum by (le) (rate(omi_audio_pcm_storage_stage_seconds_bucket{namespace="prod-omi-backend",job="JOB",stage="decode"}[5m])))
sum by (stage, child_result) (increase(omi_audio_pcm_storage_stage_seconds_count{namespace="prod-omi-backend",job="JOB"}[5m]))
histogram_quantile(0.99, sum by (le) (rate(omi_audio_pcm_storage_stage_timeout_overshoot_seconds_bucket{namespace="prod-omi-backend",job="JOB",stage="encode"}[5m])))
sum by (stage) (increase(omi_audio_pcm_storage_stage_timeout_overshoot_seconds_count{namespace="prod-omi-backend",job="JOB"}[5m]))
resets(omi_audio_pcm_storage_stage_seconds_count{namespace="prod-omi-backend",job="JOB"}[5m])
```

Stage series are empty on a surface whose compression flag is `false`, because
no child runs: absent stage data means no encoding was attempted, not a fast
encode. Missing observations, a scrape gap, a counter reset or a target that
stopped reporting are UNKNOWN, never a zero-valued pass. Do not read an
aggregate whole-helper-minus-stage difference as an exact admitted-attempt
overhead: the populations differ (the helper histogram also times calls that
spawn no child), the two histograms use different monotonic clocks, the stage
flush happens after the slot release, and scrape-window boundaries differ. Treat
any such difference as an approximate diagnostic. Final disposition is still
the guard above; return stage findings to the owner for behavioural design
rather than changing a threshold, a bucket, an eligibility rule or the guard
population here.

This switch is the sole custody kill switch. `AUDIO_ARCHIVE_LIVE_ENABLED`
controls legacy raw admission only after the outbox switch is set to `false`;
it cannot disable the default-on custody barrier. `AUDIO_ARCHIVE_READ_ENABLED`
continues to control raw playback reads independently.

`AUDIO_CUSTODY_FRAMED_PERCENT` defaults to 0 independently of
`AUDIO_ARCHIVE_PERCENT`. Its framed windows rejoin send pauses up to 60 seconds
of captured audio / 16 MiB, retaining each original frame position and sample
count. A frame table is not one continuous wall span. Both generations and
both plaintext hashes still gate each part's receipt; no ACK waits for an
entire conversation. Raw and projection discovery read the committed frame
table, never treating a media-only orphan as custody. Percent 0 restores the
per-pause writer while readers retain support for existing framed objects.

For consented capture, listen retains original packs through capacity pressure,
upload errors and cancellation. Four commits can run at once; the fifth waits
before removing its active pack. LISTEN commits at the pack's own 60-second,
conversation/hour/size boundary, 4096-frame cap, or disconnect tail. The relay
path neither awaits uploads nor flushes an active window. Transcript
persistence and live STT delivery continue immediately; coverage ledger writes
and `capture_committed` events wait for the accepted original-audio checkpoint.
Snapshots coalesce per conversation (at most 32 queued conversations); overflow
withholds the optional coverage ACK and leaves the client's WAL retained.
A later window cannot release coverage across an earlier failed commit.
A transport send or transcript receipt
alone is never an audio archive receipt. Cloud-storage consent still applies;
users with storage disabled do not acquire a new archive obligation.
For those users, coverage follows the pre-custody transcript receipt contract:
only a successful durable transcript transaction permits coverage publication
and WAL release. It is never an audio-only receipt or proof of an immutable
audio archive. This preserves bounded client retention without inventing an
archive obligation. With storage consent, an empty archive cannot certify
coverage; its accepted-frame checkpoint must have committed original audio.

Pusher commits every incoming PCM run before trimming overlap or adding it to
any derivative buffer. Its queue holds at most 20 generation-pinned receipts.
The producer waits when it fills. Pending conversations hold bounded lists of
references; the 21st conversation flushes an existing projection rather than
evicting PCM. Hydration is serial and bounded by the 20 MiB projection budget.
Projection failures leave remotely archived audio recoverable by receipt;
positioned v2 captures also participate in `raw-live` playback discovery.
Legacy headers estimate arrival time, so their projections keep the previous
continuous, spanless batching. Their immutable originals are marked
`clock_source=arrival_estimate` and recover by receipt; raw playback discovery
does not invent capture positions for them. No projection deletes the original
or manifest.

Media is immutable under `raw-live/<owner>/<conversation>/...`; each receipt
also pins an `audio-outbox/<owner>/...` manifest generation and both plaintext
SHA-256 digests. The manifest records source root/channel/clock, ordered frame
sequence, byte offsets, sample counts, gap positions and a capture-end
checkpoint. The checkpoint means the end of this committed pack, not the end
of an entire device recording. Unavailable device positions stay explicitly
unknown. Silence, undecodable originals and multichannel captures still retain
their bytes; unknown/gapped clocks never certify continuous playback coverage.

Listen emits additive `audio_custody` events only after both objects commit,
when the peer opts in with the WebSocket query `audio_custody=1`.
The event carries the receipt and per-frame source mappings when supplied by
the client. Unknown mappings cannot release a device WAL. Pusher can emit
opcode 203 with the same receipt when the caller opts in with
`audio_custody=1`; legacy peers receive no new opcode. Capable phone builds journal receipts in shadow. Their
`custody_durable_audio_release` switch opts into synced retention once every local frame
matches durable evidence. A `capture_committed` range contributes only frames in its
explicit `audio_custody` binding. Earlier builds retain their existing upload path.
Windowed custody increases time-to-ACK and client WAL retention from roughly
one relay cycle to pack completion: up to an active 60-second pack plus storage
latency for audio-only receipts (or an earlier boundary). A coalesced coverage
snapshot can include frames from the next pack, so coverage-based WAL release
may wait into the following active window as well. A partial idle window stays unacknowledged until more audio
closes its window or disconnect flushes it. During outages, WAL retention lasts
through successful retry; there is no timed early release. A mid-window pod
loss has issued no audio or coverage custody ACK for that uncommitted window.

## Recovery and acceptance

After a record socket closes, inline finish waits up to 20 seconds for its
projection. The existing socket drain gets another 30 seconds. If durable work
still remains, pusher transfers that same worker to a tracked process owner
(`PUSHER_MAX_CLOSED_RECORD_DRAINS`, default 32, clamped 8..128; prod values 64).
No projection is restarted or certified
by the transfer. Queue accounting and close checks are per conversation;
a later recording on the socket cannot keep the earlier close waiting for
the whole socket queue to empty. Each pass consumes a bounded queue snapshot.

Transient close metadata errors keep retrying at the drain's one-second cadence,
including after the old three-attempt limit. Permanent projection/tail failures
retain their producer token. A `producer_pending` seal refusal means another
producer remains; the successfully drained caller has already released its own
token. At closed-drain capacity, cleanup cancels the worker as before. With
`PUSHER_ABANDON_EVICTED_TOKENS` on (anything except `off`), one of at most four tracked coordinators
waits for the worker and every socket storage/barrier executor future, then marks
each exact owned token `abandoned_at` and forgets its recovery hint. The immutable
receipts and token remain for repair. Inherited pending clears from another socket are excluded because its writer settlement is not proven by this eviction. Admission refusal/failure retries with
bounded exponential jitter while the process lives. Abandonment proves stoppage,
never tail durability: repair still requires archive discovery, retained-tail
validation and its privacy transaction gate. A reconnect's new token stays live,
and normal clears cannot remove abandoned tokens. SIGTERM cancels tracked drain
owners and workers; process death retains the existing pod-death proof fallback.
Overflow coordination is independently bounded by
`PUSHER_MAX_ABANDON_RECORD_DRAINS` (default/prod 4, clamped 0..16; invalid uses 4).
At capacity, no new coordinator starts: `outcome=abandon_overflow` leaves the
durable token fenced for the existing process/pod-death proof.
Refusal removes its local recovery hint, preventing a later producer from
certifying it while the evicted writer is still running. Slots return only when
coordinators finish, including metadata retries.

Durable custody, PCM reads, uploads and projection refresh use the original
shared `storage_executor` (128 workers) and its existing queue behavior. There
is no separate recording pool, routing override or pool-specific refusal before
ACK. Socket future tracking shields queued and running storage work from caller
cancellation and waits for actual settlement before abandonment. The closed-worker
and coordinator count caps do not establish a PCM byte bound or pod RSS bound.

### Pusher PCM storage byte admission (default off)

`PUSHER_STORAGE_PCM_BUDGET_MB` is an integer in MiB, default **0**
(off / kill switch). Enabled deployment values must be **at least 27 MiB**:
ceil(20 MiB x4/3) lets the 75% live lane admit the largest socket window even
when otherwise idle. Smaller positive values are rejected by deployment
validation; an unvalidated invalid startup value selects off, as malformed
values do. All committed chart and manifest values remain 0. A
positive value bounds only PCM submitted to `commit_pcm_window` through the
shared storage executor, queued plus running, per process. No executor pool,
projection read/upload, record barrier, seal, failure marker or abandonment
admission changes. Live windows may use 75% of the limit; disconnect / shutdown
tails can use the remaining 25% as well, always within the total limit. A large
tail burst can still refuse: the reserve is headroom, not a durability promise.

A full budget **returns without submitting storage**. It never raises, closes a
socket or sends opcode 203. There is no receipt and no commit callback. Original
socket PCM, owner, start time and exact frame checkpoints stay charged to the
existing 20 MiB per-socket budget; boundary callers cannot erase or rebind them.
The **first live refusal immediately pauses intake** in the same receive task.
It probes non-waiting admission every 50 ms without reading another frame until
that window commits. Refused windows therefore cannot accumulate toward the
socket byte limit. There is no detached retry task or global admission waiter
list. Enabled windows also cap at 4096 checkpoints.

The pause is cancellable, including cancellation of the outer socket handler.
Cancelling this pause does not retry storage in cleanup, whether the peer is
connected or already disconnected: no tail receipt or ACK is produced, and the
producer fence stays held for client WAL replay. Cleanup therefore cannot wait
on a new PCM storage call or its retries. A storage call already submitted before
cancellation keeps its reservation until actual settlement and cannot send a
late ACK. Normal receive-finalization tails still bypass the pause and try the reserve;
a full tail budget retains the producer fence without selecting an error close.
Known-deleted retained owners use the existing gone-owner disposition before
retry. Close, abandon and marker operations remain ungated on their metadata
executor. No ACK means the source WAL must retain and replay. This does not
measure listen's re-offer cadence or certify installed client WAL behavior.

A durable dispatch that fails or is cancelled before its receipt has no known
storage outcome. That socket settles exactly one terminal disposition instead of
raising on every later flush: the fence closes, the retained window and its
producer token stay unacknowledged for WAL replay, and the socket closes once
with `1011` (`event=pusher_receive_failed`) rather than ending in a repeated
unhandled `custody commit unresolved` traceback per tail. Later flushes and the
shutdown tail return without rerunning storage or emitting a second record. The
disposition is `event=durable_custody_commit_disposition disposition=unresolved
stage=commit|window_tail exception_type=<class> raised_by=<frame>`, counted once
in `omi_audio_custody_failures_total` and `omi_audio_custody_would_drop_total`
under the same stage. A refusal (a known non-commit) is not a disposition and
keeps its existing no-error-close behavior. The disposition is socket-local; it
is not persisted and no other service reads it.

`omi_pusher_storage_pcm_inflight_bytes` measures submitted custody PCM. When
admission is enabled, accounting and capacity remain held until storage actually
settles, including a caller cancelled while its queued/running thread continues.
An acquire accounting error rolls back its partial mutation and admits using the
flag-0 dispatch path and emits the shared `omi_fallback_total` signal
(`pusher`, `storage_pcm_budget` -> `unbudgeted_storage`, `gate_unavailable`,
`degraded`). Its local error log remains rate-limited. A release error retires exactly its reservation and is
swallowed. Neither reaches socket failure handling. Both are counted in
`omi_pusher_storage_pcm_errors_total{reason="acquire|release"}` and logged at
most once per reason per minute. Late post-cancellation storage failures use the
same counter/log path with `reason="late_storage"`.

Flag 0 preserves successful PCM bytes, frame checkpoints, receipt/opcode-203
bytes, and the previous storage-await/cancellation dispatch and observational
gauge semantics. It does **not** restore every prior failure-path behavior:
the new `finish_receive` finalizer holds all unresolved owner fences and can
defer inline finish after genuine storage failures even with the flag off.
`omi_pusher_storage_pcm_budget_limit_bytes` reports the configured limit (zero
means off). `omi_pusher_storage_pcm_refusals_total{stage="live|tail|unknown"}`
counts pre-submit refusals. The agent-tier chart alert
`omi-pusher-storage-pcm-refusals` fires for rate >0 sustained 30 minutes (fresh
pusher samples only). Refusal means delayed custody, never evidence of storage.

Proposed enabled size: **512 MiB**, with 384 MiB for ordinary admission and
128 MiB reserved headroom. For sizing context, 128 storage workers each holding
60 seconds of 16 kHz PCM use about 234 MiB (128 x 1,920,000 bytes). This is a
planning calculation, not a live measurement or an RSS guarantee. The byte
limit excludes per-socket buffers, projection debt, GCS client buffering and
other process memory. Real socket counts, 48 kHz window prevalence and tail
size distribution still need measurement before enablement.

Enablement is a separate PR / approved train, owned by uicleanup
(omi-lifecycle): dev chart first, then **one canary pod for 15 minutes**. Require
socket kills <=15/15min and pod memory p99 <75% of the 3.5 GiB container limit;
inspect live/tail refusal rates, GCS errors and capacity/abandon outcomes. The
owner expands to the fleet within one day of a clean canary or records the
failed gate. **Rollback: chart value `PUSHER_STORAGE_PCM_BUDGET_MB=0`**, applied
through the ordinary chart rollout; no image rebuild, object deletion or token
clear. This PR does not enable any environment or authorize that rollout.

Chart alerts `omi-pusher-storage-queue-warning` (>256 queued storage tasks per
pusher target for 10m, agent) and `omi-pusher-storage-queue-critical` (>512 for
10m, page) sum all task kinds, including `other`. These are 2x/4x the 128 storage
workers. `omi-pusher-memory-working-set-high` pages above 75% of the 3.5 GiB
limit (2.625 GiB) for 15m, using the pusher dashboard workload selectors.
Each excludes samples older than 120s before aggregation; absent data is not
pressure. When they fire, compare queued/active storage tasks, the in-flight
PCM gauge, pod working set and GCS latency/errors; attribute the pressure to
the running release and escalate to the lifecycle lead for an approved rollback.
Preserve client WAL and custody objects. These chart definitions require normal monitoring
provisioning before they become live.

Rollback uses abandonment `off` and closed cap `32`. Coordinator cap `0` also
refuses all new abandonment coordination. Ship by pusher train with one canary
at 64 for 15 minutes: socket kills must be <=15/15min and memory p99 must stay
below 75% of the unchanged 3.5 GiB limit before fleet expansion. Also review
capacity/abandoned/abandon_overflow outcomes and repair `upload_pending`. These
production gates have not been measured by the local regression suite. Do not
raise prod to 128 without a retained-PCM byte budget.

`event=record_closed_finish` uses only closed outcomes: `retained`, `completed`,
`failed`, `cancelled`, `capacity`, `abandoned`, `abandon_overflow`. `completed` means the drain settled, not that
every seal succeeded; projection failures and seal refusals retain their existing
failure/refusal events. These events contain no recording or producer identity.

After a pod loss, list raw-live objects for the affected owner/conversation and
the corresponding immutable audio-outbox manifests. Fetch the pinned media
generation, decrypt under its owner, verify the plaintext digest, decode, and
verify PCM sample count/digest against the manifest. The raw playback index is
independent of the former pod's in-memory projection queue. A crash between
media and manifest commit issues no receipt; retry preserves the existing
immutable media. Never infer custody from a log, a transcript or readiness.

Release acceptance requires the fault suite (queue >20, 20 MiB budget, pending
overflow, four concurrent commits, failed uploads, cancellation, restart and
reconnect), plus the hermetic listen/pusher harness and an authorized staging
playback canary. Production acceptance additionally requires exact serving
revision identities and a visible new metric/log. Local tests alone do not
prove deployed playback or an installed client's WAL retention.

`omi_audio_custody_would_drop_total{stage}` counts averted loss paths;
`omi_audio_custody_backpressure_total{stage}` counts producer waits;
`omi_audio_custody_failures_total{stage,reason}` distinguishes commit and projection
failures; `reason` is `conflict` (deterministic projection mismatch, never retried),
`transient` (non-deterministic failure that exhausted its bounded requeue passes),
or `other`; `omi_audio_custody_commits_total` counts complete immutable receipts.
`omi_audio_custody_last_risk_timestamp_seconds` also exposes a refusal before
the first scrape, when a counter increase has no observed zero baseline.
The source Grafana rule `omi-audio-custody-pressure` alerts immediately on any
would-be drop or failure in five minutes. Provision split/combined alert JSON
through the existing approved monitoring path and verify Telegram delivery.

Windowed durable writes share the original pack boundaries, so Firestore
fence, tombstone and protection reads occur per committed window rather than
per relay cycle; no safety authority is cached across windows.
Measure GCS operation spend and listen latency during
the staging canary; tune batching only while preserving the custody barrier.
PCM custody writes preserve the original samples; eligible proven PCM may use
the optional lossless representation described above. Encoding/decoding failure
cannot prevent custody of even a one-sample frame.
Do not count savings or assume the rollout's extra cost is zero.

Emergency rollback: set `AUDIO_DURABLE_OUTBOX_ENABLED=false` on both listen and
pusher through a lead-approved train. This restores known lossy legacy caps;
retain all existing outbox objects and source WALs, record the incident ruling
and restore custody as soon as storage is healthy. Re-enable by removing that
override or setting it to `true`.
