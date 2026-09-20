# Windowed TDT live rollout

The September 2026 live-chain incident exposed three different contracts:
configured order did not govern connection fallback; account-state refusals were
retried as transient failures; the healthy batch TDT model was not a live leg.
This rollout uses `/v1/transcribe`, never the RNNT `/v3/stream` path for the
`parakeet-window` token. No language parameter is sent to the batch endpoint.

## Controls and default darkness

| Environment variable | Code default | Dev listen | Prod listen |
|---|---|---|---|
| `STT_CONNECT_ORDER_FROM_CONFIG` | `false` | `true` | `false` |
| `PARAKEET_WINDOW_ALLOCATION_PERCENT` | `0` | `100` | `0` |
| `PARAKEET_WINDOW_MAX_SESSIONS` | `1` | `1` | `1` |
| `PARAKEET_WINDOW_POST_TIMEOUT_SECONDS` | `8` | `8` | `8` |
| `PARAKEET_WINDOW_DIARIZATION` | `false` | `false` | `false` |
| `STT_ACCOUNT_CIRCUIT_COOLDOWN_SECONDS` | `1800` | `1800` | `1800` |
| `STT_CIRCUIT_HALF_OPEN_PROBES` | `1` | `1` | `1` |
| `SONIOX_CIRCUIT_FAILURE_THRESHOLD` | `3` | `3` | `3` |
| `SONIOX_CIRCUIT_COOLDOWN_SECONDS` | `30` | `30` | `30` |

The first flag gates all new routing/breaker behavior, including account cooldown,
last-resort primary admission and Soniox's own circuit configuration. With it off,
the existing fixed order, fallback breaker behavior, and Modulate-named Soniox
circuit env lookup remain unchanged. Production retains
`modulate-velma-2,soniox,dg-nova-3,parakeet`. Only bounded telemetry vocabulary is
corrected unconditionally. Dev explicitly sets `STT_SERVICE_MODELS=parakeet-window,soniox`.
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

## Capacity, audio and latency

One slot per one-process listen pod means at most 12 sessions at 12 replicas or
60 sessions at 60 replicas. Each session has one in-flight POST and at most 18
seconds (three 6 s windows) of queued mono PCM16. That extra window absorbs a
transient slow-but-200 POST (6–8 s) without killing a healthy session. Six-second
chunks and a minimum six-second interval between POST starts bound sustained
full-window traffic to 2 or 10 requests/s, respectively. Reconnects and initial
flushes can burst up to the session cap; this is **not** a fleet-wide global rate
limiter. Replicas and worker processes multiply these bounds. Default allocation
zero is the production safety boundary; a cap of one is the smallest nonzero
process cap for the first measured ramp, not proof that any 2–3 GPU fleet can
sustain 60 synchronized requests alongside batch jobs. Server overload rejection
remains authoritative. Do not increase the cap without measuring batch queueing,
p95 latency and error rate under the actual pod count. Do not add a second
in-flight POST per session — that doubles GPU load exactly when it is slow.

A 503 or a timeout on an *acquired* POST kills the window leg, releases
admission, and opens the Parakeet serve-error circuit (existing default 180
seconds). A malformed 200, HTTP 413, or a timeout spent waiting on the shared
STT semaphore is session-local: the leg dies, the process circuit does not.
Semaphore-queue timeouts increment `omi_stt_window_posts_total{outcome="queue_timeout"}`.
A windowed socket proves recovery only on its first successful POST; local
construction cannot close a half-open circuit. Generation-scoped callbacks
release cancelled probes without erasing a newer failure. There are no POST
retries or teardown retries against the failed provider. Sustained buffer
overflow (the 18 s cap exceeded) fails the leg with `capacity_full` **and**
opens the Parakeet serve-error circuit so new sessions on this pod skip TDT
for the cooldown — load shedding, not a reconnect stampede. Local *admission*
overflow (the process session cap) still does not poison provider health.

The windowed TDT leg owns forced-active VAD with a short silence tail. Initial
noise never reaches TDT. VAD initialization failure skips TDT; inference
failure on that leg closes it before raw audio can escape. Non-window legs on
the managed chain behave like today's `GatedSTTSocket`: they honour
`vad_gate_override` / `VAD_GATE_MODE`, and a VAD inference error fails open to
raw send. Flag-on with allocation 0 therefore changes chain order and breakers
only, not audio gating. Silence boundaries flush subwindows, subject to the
same POST pacing, so repeated short utterances cannot defeat the per-session
limit. After the first POST, a short utterance can wait almost six seconds for
its turn. Teardown skips that pacing delay for the final flush and releases the
admission slot as soon as drain starts; the final POST may finish without
holding the slot. Cancellation releases admission and cancels the outstanding
request. Failed windows are not replayed to a second provider: the normal
offline capture/sync recovery still owns that gap, as with existing mid-stream
provider deaths.

There is no overlap. Each PCM sample advances the provider timeline once; boundary
words may be split. Acoustic accuracy and overlap/dedup tradeoffs need real speech
qualification before a production ramp. Local tests are not WER evidence.

Each replacement has a fresh gate and a session audio offset. Timestamps are remapped
once, clamped within TDT windows, then made monotonic across provider epochs. Old
callbacks are fenced after a replacement is adopted. Existing `SpeakerProviderEpoch`
scopes provider speaker labels. TDT clustering reuses the existing online embedding
policy, defaults off, and when enabled embeds at most once per window with a one-second
embedding deadline. Disabled clustering uses speaker zero; several voices in one
window can share a label. `include_speech_profile` and downstream voiceprint matching
remain independent and no segment is claimed as the owner merely because TDT emitted it.

Speech seconds are recorded on the actual serving provider per send, with
`provider=parakeet` for TDT. The session VAD ledger retains speech deltas across
failover for existing fair-use/usage flushes; periodic metering does not double-count.

## Chain and alerts

Each configured provider is attempted once per session, including failed connects.
Account failures (Deepgram 401/402/403; typed Soniox account errors) use the longer
cooldown and a single recovery probe even when other circuits allow N probes.
`force=True` never bypasses an account-state cooldown. Last-resort never re-dials
the windowed TDT leg while its circuit is open for capacity or 5xx shedding.
A replacement is recovered only after a nonempty transcript, including TDT. A
successful empty TDT POST proves breaker health but does not settle failover recovery.
If every other non-TDT leg is absent/open, one bounded primary probe can bypass a
non-account bench. The flag-enabled preflight therefore leaves admission to the
chain. The old path retains its two-failover limit; the managed chain allows three
hops across four providers.

Metrics: `omi_stt_chain_exhausted_total` increments once per terminal chain;
`omi_stt_leg_attempts_total{to_mode,outcome}` counts successful and failed actual
connections; shared `omi_stt_stream_close_total{provider,reason}` counts typed
budget/quota and authentication refusals at the provider boundary;
`omi_stt_window_sessions_active`, `omi_stt_window_sessions_capacity`,
`omi_stt_window_admissions_total{outcome}`, `omi_stt_window_posts_total{outcome}`
(success/empty/error/cancelled/queue_timeout), and `omi_stt_window_post_seconds`
expose TDT load. No UID, transcript, URL or exception text is a metric label.
Non-terminal configured-chain skips and failed legs emit
`record_fallback(..., component='stt_selection', outcome='degraded')` plus the
leg-attempt counter. `outcome='exhausted'` on `stt_selection` is emitted once,
only when the whole chain cannot serve. That is what #15189's
`omi-stt-chain-exhausted-warn` / `-page` already watch
(`omi_fallback_total{component="stt_selection",outcome="exhausted"}` over
accepted sockets, 35% warn / 60% page). Per-leg degraded events do not move
those ratios.

Grafana split `alerts/live-stt.json` and the combined export cover terminal chain
exhaustion, per-leg error ratios, authentication deaths, overflow ratio,
sustained cap occupancy and batch POST error ratio. Traffic floors suppress
ratio noise; saturation uses a dwell gauge. Existing #15189 fallback alerts and
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
