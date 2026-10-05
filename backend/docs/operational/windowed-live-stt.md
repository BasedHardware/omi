# Windowed TDT live rollout

The September 2026 live-chain incident exposed three different contracts:
configured order did not govern connection fallback; account-state refusals were
retried as transient failures; the healthy batch TDT model was not a live leg.
This rollout uses `/v1/transcribe`, never the RNNT `/v3/stream` path for the
`parakeet-window` token. No language parameter is sent to the batch endpoint.

## Controls and default darkness

| Environment variable | Code default | Dev listen | Prod listen |
|---|---|---|---|
| `STT_CONNECT_ORDER_FROM_CONFIG` | `false` | `true` | `true` |
| `PARAKEET_WINDOW_ALLOCATION_PERCENT` | `0` | `1` | `100` |
| `PARAKEET_WINDOW_MAX_SESSIONS` | `1` | `1` | `16` |
| `PARAKEET_BATCH_PRESSURE_POOL_HOST` | empty (stand down) | `dev-omi-parakeet-headless.dev-omi-backend.svc.cluster.local` | `prod-omi-parakeet-headless.prod-omi-backend.svc.cluster.local` |
| `PARAKEET_BATCH_PRESSURE_MIN_REPLICAS` | `2` | `1` | `3` |
| `PARAKEET_WINDOW_POST_TIMEOUT_SECONDS` | `8` | `8` | `8` |
| `PARAKEET_WINDOW_DIARIZATION` | `false` | `false` | `false` |
| `PARAKEET_WINDOW_PACE_SECONDS` | `6` | `6` | `6` |
| `PARAKEET_WINDOW_MAX_CONTEXT_SECONDS` | `24` | `24` | `24` |
| `PARAKEET_WINDOW_FIRST_TEXT_DEADLINE_SECONDS` | `12` | code default | `12` |
| `PARAKEET_WINDOW_MAX_EMPTY_STREAK` | `4` | code default | `4` |
| `STT_ACCOUNT_CIRCUIT_COOLDOWN_SECONDS` | `1800` | `1800` | `1800` |
| `STT_CIRCUIT_HALF_OPEN_PROBES` | `1` | `1` | `1` |
| `SONIOX_CIRCUIT_FAILURE_THRESHOLD` | `3` | `3` | `3` |
| `SONIOX_CIRCUIT_COOLDOWN_SECONDS` | `30` | `30` | `30` |
| `STT_FAILOVER_RECOVERY_ENABLED` | `false` | `false` | `true` |

**Failover-recovery gate.** `STT_FAILOVER_RECOVERY_ENABLED` selects the session
mode once at listen-session start; the pin survives mid-session environment
changes, delayed component construction, successor legs, and spawned writer
tasks, so changing the value only affects new sessions or replacement pods.
**Off** (the code default and dev listen setting) runs the pre-recovery
paths: the 135-second capture cap and legacy reconnect budgets (3 total, 2 per
minute, 30s cumulative replay), plain `asyncio.Queue` provider send queues
without writer pacing, the legacy finalize/EOS order, legacy circuit
rejection semantics (429 records failure/selection bench; account protections
are unchanged), and the unmanaged `_finishing` latch. The new recovery metrics (`omi_stt_replay_wall_seconds`,
`omi_stt_replay_audio_seconds_total`, `omi_stt_replay_queue_high_water`,
`omi_stt_replay_skipped_seconds_total`, `omi_stt_replay_successor_closed_total`,
`omi_stt_recovery_attempts_total`, `omi_stt_connect_backoff_total`,
`omi_live_session_terminal_after_text_total`) still register but never emit
values in this mode; baseline metrics such as `omi_stt_replay_seconds_total`
and `omi_stt_reconnect_total` are unchanged. **On**, configured for prod listen
with `STT_FAILOVER_RECOVERY_ENABLED=true`, the recovery
state machine applies: `LiveRecoveryController`, the shared 60s
episode, 150s bounded replacement headroom, paced `AudioSendQueue` replay, and
release-not-bench 429 probe handling. **Every recovery description in this
document below applies only to flag-on sessions.**

For the pre-flip canary comparison, set
`${canary_pods:regex}` to the escaped exact enabled-canary pod names and
`${control_pods:regex}` to the escaped exact flag-off control pod names;
refresh those lists after replacement. These are proposed watches, not executed
production measurements:

```promql
sum by (source,successor) (increase(omi_stt_recovery_attempts_total{job="backend-listen-metrics",namespace="prod-omi-backend",pod=~"${canary_pods:regex}"}[15m]))
sum by (provider) (increase(omi_live_session_terminal_after_text_total{job="backend-listen-metrics",namespace="prod-omi-backend",pod=~"${canary_pods:regex}"}[15m]))
histogram_quantile(0.95, sum by (le,source,successor) (rate(omi_stt_replay_wall_seconds_bucket{job="backend-listen-metrics",namespace="prod-omi-backend",pod=~"${canary_pods:regex}"}[5m])))
sum(increase(omi_stt_recovery_attempts_total{job="backend-listen-metrics",namespace="prod-omi-backend",pod=~"${control_pods:regex}"}[15m])) > 0
```

New recovery counters and histogram observation counts must stay zero on
flag-off controls. Missing telemetry is not proof of darkness or health; the
coordinator must verify scrape coverage and actual per-pod flag configuration.
The stable enablement deploys through the normal listen Helm workflow,
`gcp_backend_listen_helm.yml` (`environment=prod`, `mode=deploy`). Roll back by
reverting the enablement PR and deploying listen, or use that workflow with
`mode=rollback` for an emergency Helm rollback. Enabling recovery also enables
the canary-only TAT metric fleet-wide; relax the canary-scoped alert selectors
from #20660 in a follow-up after the stable rollout. This config change does
not change those alerts.

The first flag gates all new routing/breaker behavior, including account cooldown,
last-resort primary admission and Soniox's own circuit configuration. With it off,
the existing fixed order, fallback breaker behavior, and Modulate-named Soniox
circuit env lookup remain unchanged. Production's configured order is
`parakeet-window,modulate-velma-2,soniox,dg-nova-3`. Soniox-first was tried on
2026-10-02 and rolled back within the hour: a Parakeet failover replays its
capture ring into Soniox's bounded send queue, which overflowed (`capacity_full`)
and ended the session. Dev retains its separately
configured order; never use dev to mutate health state (it shares production
Redis). The first token uses windowed TDT only for the allocated UID bucket;
everyone else retains the configured vendor tail. Streaming RNNT is outside
this chain. The cost-router evidence and independent on ramp are documented in
[live STT routing](../runbooks/live-stt-routing.md).
Runtime env source is `_base.yaml` plus overlays; regenerate the composed manifest.
With the flag enabled, the deployment validator accepts configured listen orders
whose tokens are all enabled by the streaming policy. With it off, canonical
production defaults remain enforced; a production ramp is an explicit values and
runtime-env rollout change, not a source-code change.

A stable SHA-256 UID bucket controls TDT allocation. Missing UID, allocation 0,
explicit `multi`/`auto`, unsupported requested language, missing batch endpoint,
or full local admission routes to the next configured provider. Multilingual mode
uses the requested base language for TDT's 25-language capability check; it does
not change the endpoint's automatic detection. A multilingual user whose requested
language is English may still speak an unsupported language: this remains a quality
risk to measure during the ramp. There is **no transcript-language check** after a
window POST — TDT will transcribe whatever speech the VAD admitted. PTT,
multi-channel, custom STT and BYOK do not enter the new session path. Those
excluded listen shapes drop only the `parakeet-window` token from the configured
list; they keep the rest of `STT_SERVICE_MODELS` (they are not rewritten onto
code-default Modulate).

## Production ramp: 1% → 5% → 25% → 50% → 100%

Deploy the Parakeet server revision and its 3–6 replica HPA first. Wait until
at least three ready replicas all expose `live_pending_requests` and
`live_oldest_pending_seconds` from `/batch/metrics`. Then deploy listen with
`PARAKEET_WINDOW_MAX_SESSIONS=8` and the pressure gate. During a mixed-revision
server rollout, replicas without valid live fields count as unknown unless they
still have a fresh cached sample. The quorum and conservative unknown-pod
accounting below decide whether listen admits the window leg. Unmarked HTTP requests
remain in the backfill lane; only the window client's explicit
`X-Omi-STT-Surface: live-window` header enters the live lane. Soniox stays on
the fallback chain. Keep the merged 5% allocation for this code release; a later
configuration rollout advances it only after the gates below pass.

The headless Service selects ready Parakeet pods. `utils/stt/batch_pressure.py`
polls each replica every five seconds with its own one-second HTTP and wall-clock
deadline. A failed fetch does not discard the other responses: each replica
keeps its last valid sample and original timestamp for **at most 15 seconds**.
Departed replicas are removed. DNS failure immediately stands down; admission
never performs DNS or HTTP. Poll/cache fan-out is bounded at **64 ready pods**,
well above the seven-pod HPA maximum; fleets above that bound still stand down.

Fresh telemetry must cover **both** `PARAKEET_BATCH_PRESSURE_MIN_REPLICAS` and a
strict majority (`floor(ready / 2) + 1`) of the current ready pool. Pressure is
measured as `(busy replicas + unknown replicas) / ready replicas`: by default,
**50% or more refuses admission**. Thus a six-pod pool needs at least four
replicas known healthy; one isolated hot pod or intermittent failed fetch does
not void healthy fleet capacity. Unknown replicas cannot supply headroom.
The existing per-pod thresholds still define busy; backfill pending alone does
not. Small two-pod pools retain the conservative one-hot-pod stand-down.

| Environment setting | Default | Meaning |
| --- | ---: | --- |
| `PARAKEET_BATCH_PRESSURE_MAX_LIVE_PENDING_PER_REPLICA` | `4` | Busy when live pending reaches this count |
| `PARAKEET_BATCH_PRESSURE_MAX_LIVE_OLDEST_SECONDS` | `0.75` | Busy when oldest live queue wait reaches this many seconds |
| `PARAKEET_BATCH_PRESSURE_BUSY_REPLICA_SHARE` | `0.5` | Stand down when busy plus unknown reaches this ready-pool share |

Invalid configuration stands down. Invalid, negative, non-finite or old-revision
responses leave that replica's timestamp unchanged; it becomes unknown after
its cached sample expires. Refusal labels stay `unconfigured`, `missing`,
`stale`, `pressure`. Refresh outcomes add `partial` for a usable quorum with
failed fetches, including when the remaining pressure decision stands down;
quorum loss is `unavailable`. The bounded gauge
`omi_stt_window_batch_pressure_replicas{state="fresh"|"ready"}` exposes coverage.
A stalled poller still stands down after 15 seconds.

Using a pool share follows the scheduler: live requests have priority at each
dispatch, with one aged backfill turn after four live batches. An isolated wait
can be one non-preemptible backfill inference; it is not proof of fleet-wide
saturation. The majority-of-healthy-pods rule retains conservative headroom,
while the existing per-session deadlines and replay handle a slow individual
POST. Queue-wait, POST latency and actual refusals still gate traffic ramps;
this change does not guarantee the production refusal target without a bake.

`/batch/metrics` is already an async event-loop snapshot of bounded queue state;
it does not wait for GPU inference or take the batch lock. Inference runs on the
GPU worker thread. A real-engine ASGI test holds inference and the batch lock
while the endpoint reports the queued live request. Offloading this snapshot
would not remove Python GIL contention and would complicate its event-loop
ownership. The admission fix needs **only a listen image**, with no Parakeet
runtime change or separate Parakeet deploy.

The batch engine selects live requests before backfill at each GPU dispatch.
An aged backfill item (5 s) receives one turn after four live batches; this
prevents indefinite starvation without forming a long mixed batch. Prod GPU
dispatch is limited to one in-flight batch so backfill cannot queue ahead of
live work inside the GPU worker. An inference already running cannot be
preempted, so a long historical recording can still affect a live POST; the
live queue-wait and POST p95 gates must catch this before a ramp step.

At each bake, compare `omi_stt_window_canary_transcript_outcome_total`
`arm=window` with `arm=control`: the rate of `transcribed / (transcribed +
no_transcript)` must not drop for the allocated arm. The 95% fleet SLO is shown
on the Backend-listen dashboard; a separate page fires below 90% with its
volume guard. Inspect `omi_stt_window_session_outcome_total{outcome="no_text"}`
over sessions with VAD speech, and the `capacity_full` ratio from
`omi_stt_window_admissions_total{outcome="overflow"}`. Require no sustained
capacity overflow or no-text increase relative to the control SLI. First-text
p50 and p95 come from `omi_stt_window_first_text_seconds_bucket`; p95 must
remain below 30 seconds and p50 must not drift upward through the bake. This
histogram measures from the session's first VAD speech, so sparse quiet gaps
can push elapsed first-VAD-to-text beyond 12 seconds without indicating a
stall; the p95 threshold remains the bake gate.
Compare `omi_stt_window_sessions_active` with the summed process caps, TDT
POST p50/p95 from `omi_stt_window_post_seconds_bucket`, and
`DCGM_FI_DEV_GPU_UTIL`/free GPU memory on the Parakeet pool. The same GPUs
serve sync backfill, so require visible headroom and no sync-batch queue or
latency regression before ramping. Use the Parakeet GPU dashboard for the
batch queue and memory panels. Read each metric by time and load, not a single
snapshot.

The Telegram batch pages fire at four pending requests for two minutes, batch
queue p95 at one second with five observations for two minutes, and prerecorded
Parakeet error rate at 2% with ten requests for two minutes. Prerecorded traffic
includes sync backfill and excludes live-window POSTs by their request header,
so read these alongside the sync job queue before ramping. All three batch
rules treat missing telemetry as Alerting and use the existing Telegram route.
The page action is **Parakeet canary: set PARAKEET_WINDOW_ALLOCATION_PERCENT=0**
in the prod chart and runtime overlay, then recompose the runtime environment.

After the merged 5% bake, advance allocation to **25%, 50%, then 100%** of
eligible sessions within roughly 24 hours, with an observation gate between
each step. Require live POST p95 below ~2 s, no first-text p50 regression from
the measured 7.5 s, stable transcript-success and no-text ratios against the
control arm, no sustained admission overflow, and acceptable GPU utilization,
OOM/error rates, and backfill queue age. At each step, compare the summed
window active sessions against eight times the ready listen pod count, the
per-lane GPU queue waits, and the per-replica live pending/oldest metrics.
Do not advance on missing telemetry. Change allocation in both the prod listen
chart and prod runtime overlay, then recompose the runtime environment.
Rollback sets allocation to `0` in those sources; that removes the window
leg while leaving Soniox available. This PR does not deploy or change the
existing 5% allocation.

## Why windows are sentence-anchored

`nvidia/parakeet-tdt-0.6b-v3` returns HTTP 200 with empty text when a clip starts
mid-utterance: from the decoder's start state, blank beats the best token on every
frame, so greedy TDT never emits a first token. This is a property of the weights
(same on FP32/BF16, NeMo strategies, and the MLX port), not of the Parakeet
server. Fixed 6 s slices that cut at an utterance onset come back empty; slices
that start 2.5 s into an utterance empty far more often. Whole short utterances
are fine. The live leg therefore posts `[anchor, now]` instead of a disjoint 6 s
slice, emits completed sentences, and re-anchors at the end of the last emitted
sentence so the next POST starts on a sentence boundary.

The last sentence is held on a paced POST unless it ended ≥1.2 s ago with
terminal punctuation (`.?!`). `finalize()` from the live VAD gate (300 ms hangover)
is a **soft** pause POST: `[anchor, now]` with `force=False` as soon as pacing
and the single in-flight slot allow. Managed windows enable this pause and
the normal idle paths once unresolved VAD-admitted speech reaches one second.
Sub-second fragments retain the five-second capture-silence flush and the
three-second cumulative answered-empty startup budget documented in the
listen pipeline. On that pause POST the last segment is
emitted only if it already ends with `.?!` — there is no 1.2 s gap, because
the gate has already stripped silence from the timeline. Treating every
`finalize()` as a forced cut re-anchors at a breath and the next POST starts
mid-sentence, which is the empty-clip failure mode.

Forced flush (emit everything, re-anchor at `now`) happens only on close /
`drain_and_close()`, ≥1.5 s of non-speech bytes after speech (ungated
callers), or **wall-clock idle**: no audio accepted by `send()` for ≥2.0 s
while ordinary unemitted speech remains after the anchor. An empty managed
idle answer retains its anchor, PCM and replay; only the long-silence path
settles empty-answered accounting. Idle fires once per idle
period, but only after a forced job that reached `received`; a capped idle
POST leaves `_idle_flushed` false so the pump takes another paced forced job
for the remainder. Under the gate no audio arrives during silence, so the
pump waits on `asyncio.wait_for(self._wake.wait(), timeout=…)` when held
audio exists and does not arm a timer when nothing is held.

Max-context (default 24 s, clamped to [6, 30]) is **not** a force flush:
`decide_window` owns the cap. Two or more segments behave like a paced POST
(emit all but the last, plus trailing-complete) and re-anchor at the last
emitted sentence end. A single run-on segment is emitted and the anchor
moves to that segment's end (not `now`); an empty cap response slides the
anchor forward by one pace interval instead of discarding the clip. Those
one-segment and empty cap paths count `omi_stt_window_forced_cuts_total`.
An empty model response that is not at cap keeps the anchor so a later POST
can recover the text. The same `[anchor, end]` context is not POSTed again
unless the request is forced. After a true force flush the next context
starts at the next speech onset with ~0.3 s of lead-in.
Pure non-speech never extends a context and is never POSTed. Segment
`start`/`end` are anchor + relative times, clamped into `[anchor, now]` and never
earlier than the previously emitted end. Only emitted segments run speaker
embedding (diarization stays off by default); PCM is sliced relative to the
posted context.

## Capacity, audio and latency

Eight slots per one-process listen pod allow 216–320 concurrent window
sessions at the measured 27–40 listen pods. Each session has one in-flight
POST. With the production 24 s max context and 6 s pace, the PCM buffer cap
is `2×24 + 2×6 = 60` s of 16 kHz mono PCM16: **1,920,000 bytes**. The
reproducible local probe (`scripts/benchmark_parakeet_window_capacity.py`)
created eight sockets, eight real Silero VAD states, and eight idle pump tasks:
~11 KiB objects and task per session, ~1.92 MB buffer per session, and ~17.4
MB process traced peak for all eight filled buffers (RSS high-water growth
~14.1 MB after warming the shared model). One simultaneous 24 s
AGC POST raised that peak to ~20.8 MB. Conservatively allowing that ~3.5 MB
POST transient for every session gives **~45 MB**, about **1.3% of the
3.5 GiB prod listen pod memory limit** (requests: 1.5 GiB). The same local
probe measured ~73–78 ms of CPU per session per 10 s of audio for real Silero
inference plus ingest AGC on 512-sample chunks, or ~5.8–6.2% of one core for eight
continuously active sessions. This excludes HTTP/serialization and other
listen work and is a local CPU result, not a pod RSS or production p95 measure.

The 60 s cushion absorbs a catch-up burst while one POST is in flight. Before
its first emitted text, a window leg has a 12-second rescue deadline. The
deadline is retired after an answered-empty short episode: less than 1 s of
admitted provider audio followed by at least 5 s of silence. Retirements share
a cumulative 3.0 s budget of answered-empty admitted audio; only emitted text
resets it. Once that budget is exhausted, the deadline remains armed. The
timer also fires during a slow POST or after four consecutive speech-containing
empty POSTs, whichever comes first. The existing listen death monitor selects
the next vendor and replays the untranscribed capture from the 90-second ring;
the failed Parakeet leg is excluded for the rest of that session. Session
recovery is bounded by one target-and-time budget — at most 20 unique targets
inside the shared 60s episode — for managed and legacy listen alike; PTT
retains its existing two-failover limit unchanged. Once text has been emitted, these
startup bounds are disarmed. No sentence anchor or emitted text is changed.
`omi_stt_window_session_outcome_total` retains
`outcome=text|no_text` and adds bounded `reason=none|first_text_deadline|empty_streak`;
the matching recovered failover uses the same reason on `omi_fallback_total`.
The 90-second replay ring follows the window's last emitted sentence anchor.
The accepted-send map translates that provider anchor to a capture sample, so
VAD-gated gaps cannot shift the cut. Audio before the anchor is already text;
speech from the anchor onward stays available even while a POST is in flight.
The ring never evicts that pending span solely because capture time passed.
Speech-free capture can still roll off, and the current chunk must fit. The
`omi_stt_window_replay_safe_trims_total` counter records actual anchor and
speech-free trims. If pending audio itself exceeds the ring, the leg fails
with `capacity_full` and replays from the anchor onto the next vendor.

Replay coalesces contiguous capture spans into at most 16 KiB PCM packets and
paces each adapter at **1x real time**. The adapter declarations in Soniox and
Modulate and the conservative default for Deepgram/Parakeet share this ceiling.
[Soniox cadence](https://soniox.com/docs/stt/rt/error-handling#real-time-cadence)
requires real-time or near-real-time input and warns about prolonged bursts.
[Modulate streaming docs](https://docs.modulate.ai/api-reference/stt/streaming.md) and
[Deepgram streaming docs](https://developers.deepgram.com/docs/live-streaming-audio)
do not establish a numeric accelerated replay ceiling; 1x is our conservative
choice, not a claimed vendor limit. The owned Parakeet adapter has no documented
accelerated replay contract, so it also receives the conservative default.

Each replacement target gets a **5s per-target setup budget** (dial plus
serving check) and a **20s replay prefix wall**, both spent from the session's
single **60s episode** total rather than restarting per target. Unanswered
capture exceeding 20s is cut to the newest 20s (135s becomes 20s; 115s skipped),
with `omi_stt_replay_skipped_seconds_total{source,successor}` recording the loss.
Emitted capture prefixes remain excluded. This is an intentional bounded-loss
tradeoff; do not describe it as full-ring transcript preservation. Partial
replay rejection retains the remaining obligation for the next eligible leg.

Live ingestion does not await the failover lock. A supervisor-owned ordered tail
holds at most **26s PCM** (832,000 bytes at 16 kHz), behind the replay prefix.
At 1x live input the lag stays fixed until admitted audio actually pauses;
silence still forwarded as PCM does not let it catch up. The
healthy 20ms/packet test bounds delay by 20.532s after setup; allowing the full
5s setup budget gives **25.532s at 16 kHz** (26.044s at 8 kHz, because a 16KiB
packet represents 1.024s). This is audio delivery delay, not a vendor transcript
latency guarantee. A nonresponsive transport is rejected: the replay helper
admits at most two packets counting queued plus in-flight audio and waits at most 2s for space; prefix wall
admission also has a 20s deadline. Ordinary live sends retain the 2,000-item
queue. Setup timeout skips its requested family and continues within that
attempt budget. Cancelled/unadopted replay legs close both adapter tasks and
their websocket. An adopted live tail drains before EOS even after client
departure; cancellation, death, or its bounded drain deadline meters any
undelivered tail in the skipped-seconds counter.

Recovery lifecycle is owned by one `LiveRecoveryController` per receiver
(`utils/stt/recovery_state.py`): `serving → provider_died → recovering →
replaying → recovered`, terminal `exhausted` and `client_leaving`. A provider
death opens one **60s episode deadline** that covers every dial, replay prefix,
and first nonempty successor transcript within that episode; a successor dying
before proof shares it rather than restarting it. Two proofs release the
deadline to `recovered`: a nonempty transcript from the current candidate, or —
for an adopted successor that stays silent — the death monitor observing its
socket still connected **5s after adoption** (`RECOVERY_HEALTHY_CONNECTED_SECONDS`).
The connected-dwell proof is not transcript settlement: it clears only the
episode deadline and never settles a pending leg outcome as recovered. A
successor dying after the episode released opens a **fresh 60s episode**;
deaths inside one open episode share its remaining budget. A session is
bounded to **20 fresh episodes** (`MAX_RECOVERY_EPISODES`); opening a 21st
exhausts rather than dialing. The unique-target ledger (20 targets), dial
count, and the one transient Soniox re-entry grant are per-session state that
persists across episodes. Candidate adoption and transcript/health proofs
bind to the current candidate token, so a late callback from
a retired predecessor can never release the deadline. Client departure is a
monotonic latch taken only from explicit owner/session/websocket evidence —
never raw socket cleanup flags — and a disconnect/reconnect flap cannot
resurrect a departed receiver.

Each real dial gets `min(5s, remaining episode)` covering both connect and the
post-upgrade serving check; every target draws from the one 60s episode, so a
slow target spends shared budget rather than receiving a fresh allowance. Attempt accounting is by unique target
identity, capped at 20 (16 registry + up to 4 legacy protocols), reserved at
the real dial seam only: selector calls, circuit refusals, capacity skips, and
unavailable routes spend nothing. One transient same-provider Soniox re-entry
is the sole repeat grant. A typed `LiveChainExhausted` latches exhaustion so
concurrent send/monitor races cannot redial.

Recovery legs opt into per-leg writer pacing at the transport, not just
admission: the armed slot advances from the previously armed slot, so
sub-frame timer oversleep is compensated against the accumulated slot instead
of drifting, while a stall of one frame or longer rebases on the clock and
discards missed-slot credit (sustained ≤1x, no catch-up burst on a
stalled-then-resumed transport), with each `ws.send` bounded by `min(2s,
episode remaining)`. The observable burst
allowance is bounded queue+in-flight bytes (at most two 16KiB frames); that
bound never grows. Prefix delivery — replay enqueues plus the frozen transport
writes they owed — must complete inside the **20s prefix wall**, not just the
episode, so `REPLAY_WALL` measures actual prefix delivery. Live audio carries
first-admission birth time through tail→snapshot→successor; a bounded interval
`BirthLedger` (8192 entries, adjacent coalescing by earliest birth) prunes at
the retained ring head. Live-audio birth is the first capture acceptance,
preserved across retry; contiguous silence arriving as PCM does not itself
allow catch-up. Retained recovery-tail frames have a strict 28s maximum capture
age: expired cuts are metered, queued writes already past that age reject as
`capacity_full`, and intervals older than the bound are retired and metered
once rather than replayed again. Stalls or repeated failures do not promise
delivery of all audio or transcripts.

Scoped recovery memory bound (recovery PCM only): ring ≤4,800,000B + prefix
snapshot ≤640,000B + live tail ≤832,000B + replay queue 32,768B + in-flight
16,384B + window PCM 1,920,000B ≈ **8,241,152B per session**, a
conservative planning allowance of **125.75 MiB for 16 sessions at 16 kHz**
(**375.75 MiB at 48 kHz**). This excludes Python object overhead, VAD
state, POST transients, ordinary 2,000-item queues, and general process RSS —
it is not a pod memory claim. No recovery state is persisted; nothing survives
the session.

Metrics use only bounded source/successor families (`parakeet`, `modulate`,
`soniox`, `deepgram`, `unknown`), preinitialized across all combinations so a
first post-scrape event is visible to `increase()`/`rate()`:
`omi_stt_replay_wall_seconds`, `omi_stt_replay_audio_seconds_total`,
`omi_stt_replay_queue_high_water`, `omi_stt_replay_skipped_seconds_total`,
`omi_stt_replay_successor_closed_total`, plus
`omi_stt_recovery_attempts_total{source,successor}` on each real recovery dial
and `omi_live_session_terminal_after_text_total{provider}` once when a session
delivered text and still terminated on an STT failure. The wall histogram
covers the prefix pump including capacity waits and frozen-write drain, not
setup.

A Soniox `send queue full` can arise on ordinary send, finalize, or EOS when a
sender stalls, independently of replay. #20350 excludes deaths first observed
after client departure. An eligible earlier death remains health evidence,
but an unproven hop settled during owner departure is `degraded`, not
`exhausted`; genuine active recovery exhaustion still emits `stt_failed`/1011.
Aggregates alone do not prove which mechanism explains each production event.
Compare those fallback events with client-terminal counters and content-free
owner/client-state evidence rather than treating every `to=unavailable` as a
client termination.

Replacement ring headroom still grows by 15 seconds up to an absolute
150-second retained-PCM ceiling (4.8 MB at 16 kHz mono s16le); text progress
reclaims it. The prefix budget now trims that ring before replay. Synthetic
provider-pair tests exercise the real Soniox/Modulate queues and send loops,
slow consumers, concurrent live input, client teardown, and router-on with
Modulate benched. PTT has no replay ring, and its accepted 5 MiB frame can still
overflow the synchronous 30ms send loop. The PR describes the exact separate
frame-ownership/paced-delivery follow-up; PTT provider policy stays unchanged.
The window socket separately retains PCM from its POST anchor. Its VAD speech
spans are pruned on each POST-anchor advance; rapid speech/silence toggles
coalesce the closest adjacent spans at the 1,024-entry bound rather than
ending an otherwise healthy session. Coalescing retains every speech sample
and may conservatively include the short silence between two spans. The PCM
buffer's 60-second bound still fails over when un-emitted audio outgrows it.
Near the 60-second PCM buffer limit, a 24-second context with a short emitted
prefix followed by a long unfinished TDT segment is forced out if the prefix
would advance the anchor by less than one 6-second pace. Earlier windows keep
their sentence boundary, and windows with enough progress still hold the last
segment. This extends the forced cut already used for one unfinished segment.
Fallback logs keep `reason=capacity_full` and add a bounded `subtype` of
`buffer_cap`, `replay_ring_cap`, or `admission` (or `unknown`); the shared
fallback metric gains no new label.
Growing windows re-post overlapping context. A minimum 6 s interval between
POST starts bounds sustained requests to eight per listen pod per 6 s, with
up to 216–320 synchronized sessions fleet-wide at the current pod count.
The allocation bucket, per-pod cap, live pressure gate, and provider circuit
remain in series; allocation 0 sends no window traffic. Monitor real traffic
before every increase because local memory headroom does not prove GPU
throughput or transcript quality.

A 503 or a timeout on an *acquired* POST kills the window leg, releases
admission, and opens the Parakeet serve-error circuit (existing default 180
seconds). A malformed 200, HTTP 413, or a timeout spent waiting on the shared
STT semaphore is session-local: the leg dies, the process circuit does not.
Semaphore-queue timeouts increment `omi_stt_window_posts_total{outcome="queue_timeout"}`.
A windowed socket proves recovery only on its first successful POST; local
construction cannot close a half-open circuit. Generation-scoped callbacks
release cancelled probes without erasing a newer failure. There are no POST
retries or teardown retries against the failed provider. Sustained buffer
overflow (the two-max-context + two-pace cap exceeded) fails the leg with `capacity_full` **and**
opens the Parakeet serve-error circuit so new sessions on this pod skip TDT
for the cooldown — load shedding, not a reconnect stampede. Local *admission*
overflow (the process session cap) still does not poison provider health.

The windowed TDT leg owns forced-active VAD with a short silence tail. It keeps
the billed path's 0.65 start probability with no hysteresis gap, and differs
only in the tail: hangover is 300 ms rather than 4 s, because a growing window
re-posts its own prefix and does not need seconds of trailing silence to avoid
clipping a word. Quiet far-field is admitted by the level-corrected copy the
gate scores (below), not by a lower threshold — that copy lifts far-field
admission from 73.7 s to 91.7 s of a 120 s clip on its own, where a 0.5 / 0.35
hysteresis added only 5.6 s more and cost words on dense speech. Initial noise
never reaches TDT. VAD initialization failure skips TDT; inference failure on
that leg closes it before raw audio can escape.

The windowed leg splits bounded peak AGC into two jobs with the same knobs:
target 0.8 of full scale (the RNNT path's `AGC_TARGET_PEAK`), hard 4× (12 dB)
cap, session running-max of *incoming* PCM, fast attack, no release, never
attenuates, digital silence (peak 0) unchanged. **Admission** gains a copy
ahead of Silero so quiet far-field can start speech; per-chunk gain is safe
there because Silero scores frames independently. **Decoding** keeps the
stored buffer at original level and applies one uniform scale to each posted
window, taken from **that window's own peak** — but only below a **deadband**
of 0.4 of full scale (`WINDOW_AGC_DEADBAND_PEAK`, equivalently "never apply
less than 2×"). Audio already peaking above that is not quiet, and gaining it
costs accuracy rather than buying anything: gaining loud passages moved
substitutions from 27 to 37, and reverting the VAD threshold did not move them
back.

The deadband is judged per window, **not** on the session envelope. A clip
whose loudest moment is 0.54 still contains passages at 0.37; judging those by
the session peak denied them gain and dropped them entirely — two such
passages, 37 reference words — while every passage at 0.42 and above survived
ungained. Each POST stays internally uniform, which is the property #15566
established; different gains *between* windows were never the problem.
Admission is deliberately **not** deadbanded, so quiet far-field is still
admitted by its gained copy. Ingest cannot write gained
bytes into the buffer, so the 4× cap cannot compound to 16×. Overlapping
later POSTs of the same prefix may use a lower gain if the envelope grew;
each POST stays internally flat. Gain is not frozen after the first POST:
locking the early (higher) factor would clip later louder speech, and
freezing per-prefix would rebuild an intra-window ramp. Speaker embeddings
slice original-level PCM from the stored buffer. Direct
`WindowedParakeetSocket.send` (no ingest) still peak-normalises the POST.
The cap exists so a faint noise floor cannot be lifted by orders of
magnitude the way RNNT's `peak < 1` skip can.

Non-window legs on the managed chain behave like today's `GatedSTTSocket`: they honour
`vad_gate_override` / `VAD_GATE_MODE`, and a VAD inference error fails open to
raw send. Flag-on with allocation 0 therefore changes chain order and breakers
only, not audio gating. A VAD `finalize()` after the 300 ms hangover is a soft
pause POST, not a cut. Forced flush is reserved for close,
≥1.5 s of ungated non-speech bytes, and 2 s of wall-clock idle with held
speech. Hitting max-context re-anchors at the last emitted sentence (or
slides one pace when the model returned nothing); it does not treat the cut
as a new utterance onset. Repeated short utterances still cannot defeat the
per-session POST limit: pacing applies between POST *starts*, and teardown
skips that delay for the final flush. Admission is released as soon as drain
starts; the final POST may finish without holding the slot. Cancellation
releases admission and cancels the outstanding request. Failed live windows replay their un-emitted capture to the next provider as
described above. Offline capture/sync recovery still owns any gap after the
finite live chain is exhausted.

Posted contexts overlap by design (held sentence + new audio). Each sample is
still in at most one *emitted* segment: re-anchoring drops already-emitted
audio and timestamps stay monotonic. Acoustic accuracy still needs real speech
qualification before a production ramp. Local tests are not WER evidence.

Each replacement has a fresh gate and a session audio offset. Timestamps are remapped
once, clamped within TDT windows, then made monotonic across provider epochs. Old
callbacks are fenced after a replacement is adopted. Existing `SpeakerProviderEpoch`
scopes provider speaker labels. TDT clustering reuses the existing online embedding
policy, defaults off, and when enabled embeds at most once per POST with a one-second
embedding deadline. Disabled clustering uses speaker zero; several voices in one
window can share a label. `include_speech_profile` and downstream voiceprint matching
remain independent and no segment is claimed as the owner merely because TDT emitted it.

Speech seconds are recorded on the actual serving provider per send, with
`provider=parakeet` for TDT. The session VAD ledger retains speech deltas across
failover for existing fair-use/usage flushes; periodic metering does not double-count.

## Chain and alerts

Each configured provider is attempted once per session, including failed connects,
except for one bounded Soniox re-entry after a known transient transport loss
when its circuit is closed and no untried Deepgram rescue remains. Managed
rebuild attempts are independently bounded to three, including that re-entry.
Account failures (Deepgram 401/402/403; typed Soniox account errors) use the longer
cooldown and a single recovery probe even when other circuits allow N probes.
`force=True` never bypasses an account-state cooldown. Last-resort never re-dials
the windowed TDT leg while its circuit is open for capacity or 5xx shedding.
A replacement is recovered only after a nonempty transcript, including TDT. A
successful empty TDT POST proves breaker health but does not settle failover recovery.
If every other non-TDT leg is absent/open, one bounded primary probe can bypass a
non-account bench. The flag-enabled preflight therefore leaves admission to the
chain. Legacy listen shares the same bounded target-and-time controller; PTT
retains its two-failover limit.

Full local window admission is checked before constructing the window socket,
including static/shadow serving. Capacity refusals also engage the existing
five-second target cooldown in shadow. A refused window does not consume a
remaining non-account rescue provider's attempt. That rescue may relax its
selection bench while retaining the half-open probe limit and all account
protections; an occupied probe has a twelve-second bounded wait. Exhaustion
is latched per receiver, and ring-pressure exhaustion closes through the
ordinary terminal send path rather than repeating rebuilds per packet.

Metrics: `omi_stt_chain_exhausted_total` increments once per terminal chain;
`omi_stt_leg_attempts_total{to_mode,outcome}` counts successful and failed actual
connections; shared `omi_stt_stream_close_total{provider,reason}` counts typed
budget/quota and authentication refusals at the provider boundary;
`omi_stt_window_sessions_active`, `omi_stt_window_sessions_capacity`,
`omi_stt_window_admissions_total{outcome}`, `omi_stt_window_posts_total{outcome}`
(success/empty/error/cancelled/queue_timeout), `omi_stt_window_post_seconds`,
`omi_stt_window_context_seconds` (posted context duration), and
`omi_stt_window_forced_cuts_total` expose TDT load. The forced-cut counter includes
held tails cut at max context or when un-emitted capture reaches two thirds of
the 90-second replay ring. The latter is measured on capture time: VAD can admit
less audio to the provider while the replay ring still protects the full capture.
If a POST stalls or returns no usable text, the ring remains strict and fails
over before un-emitted audio is evicted. `empty` means the posted
context contained VAD speech and the model returned no text — not "we held the
last sentence". No UID, transcript, URL or exception text is a metric label.
Non-terminal configured-chain skips and failed legs emit
`record_fallback(..., component='stt_selection', outcome='degraded')` plus the
leg-attempt counter. `outcome='exhausted'` on `stt_selection` is emitted once,
only when the whole chain cannot serve. That is what #15189's
`omi-stt-chain-exhausted-warn` / `-page` already watch
(`omi_fallback_total{component="stt_selection",outcome="exhausted"}` over
accepted sockets, 35% warn / 60% page). Per-leg degraded events do not move
those ratios.

Grafana split `alerts/live-stt.json` and the combined export cover per-leg
error ratios, authentication deaths, overflow ratio, sustained cap occupancy
and batch POST error ratio. Traffic floors suppress ratio noise; saturation
uses a dwell gauge. The former `omi-stt-chain-terminal` rule was deleted
(2026-09-26): it read `omi_stt_chain_exhausted_total`, which the legacy
connect path never emits, so it sat unfirable through the whole 2026-09-26
prod incident; chain exhaustion is covered by #15189's
`omi-stt-chain-exhausted-warn` / `-page` on `omi_fallback_total` plus the
headline session-outcome page below.

2026-09-26 additions (live-transcription health):

- `omi_live_session_transcript_outcome_total{outcome}` — the headline SLI,
  emitted exactly once per backend-STT listen session at teardown
  (`routers/listen/runtime.py::_record_session_transcript_outcome`).
  `transcribed` = at least one nonempty transcript batch was delivered;
  `no_transcript` = session ended without one (including STT-terminal
  failures, which never get the short-session excuse); `too_short` = under
  ~10 s of audio or zero VAD speech on a clean teardown — excluded from the
  success ratio so quiet sessions cannot page. Custom-STT sessions are not
  counted. Unit = one accepted WebSocket: a client reconnect counts once per
  socket (the runtime cannot see the prior socket's transcripts without
  cross-connection state).
- `omi-live-transcription-success-low` — **PAGE**.
  `transcribed / (transcribed + no_transcript) < 0.90` for 5 m with a
  `>= 50 counted sessions / 5 m` volume guard. This is the alert the
  2026-09-26 incident did not have.
- `omi_stt_provider_connect_total{provider,outcome,error_class}` — recorded
  on every connect path (legacy order and configured chain) with bounded
  error classes `budget|auth|server_error|timeout|capability|other`.
  `omi-stt-leg-error-rate` now reads it instead of the configured-chain-only
  `omi_stt_leg_attempts_total`.
- `omi_stt_provider_circuit_open{provider,kind=selection|account}` — per-pod
  mirror of the process-local breakers; sum across the listen job for "pods
  with this provider benched".
- `omi_stt_provider_retired{provider}` — deployment config
  (`STT_RETIRED_PROVIDERS`, default `deepgram` per the 2026-09 cost ruling:
  hosted Deepgram is intentionally unfunded). The per-provider budget page
  and the leg-error rule subtract retired providers so an unfunded leg
  cannot fire forever.

The Backend-listen dashboard has a "Live transcription health" row: headline
%, sessions by outcome, per-provider sessions served and connect success %,
breaker-open pods, and connect failures by error class. Existing #15189 fallback alerts and
#15218 budget/quota page remain; the auth rule excludes budget refusals to avoid
duplicate pages. An initialization-terminal rule on
`omi_live_stt_terminal_failures_total{phase="initialization"}` is **not**
shipped: that series is 40–90% of accepted sockets in prod today, so it would
page on deploy; #15189 already covers the condition. New window/chain/leg rules
evaluate empty while the feature is dark (`live_metrics` is imported only from
the ramped modules; `noDataState=OK`). New rules have no live Prometheus or
notification validation in this PR.

Rollback: `PARAKEET_WINDOW_ALLOCATION_PERCENT=0` withdraws TDT only (the
configured chain, account cooldown, and last-resort remain).
`STT_CONNECT_ORDER_FROM_CONFIG=false` restores the complete legacy chain.
Allocation 0 with the flag on is **not** a no-op.
