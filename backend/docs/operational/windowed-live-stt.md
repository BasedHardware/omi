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
risk to measure during the ramp. PTT, multi-channel, custom STT and BYOK do not enter
the new session path; the window experiment does not change their default model list.

## Capacity, audio and latency

One slot per one-process listen pod means at most 12 sessions at 12 replicas or
60 sessions at 60 replicas. Each session has one in-flight POST and at most 12
seconds of queued mono PCM16. Six-second chunks and a minimum six-second interval
between POST starts bound sustained full-window traffic to 2 or 10 requests/s,
respectively. Reconnects and initial flushes can burst up to the session cap; this
is **not** a fleet-wide global rate limiter. Replicas and worker processes multiply
these bounds. Default allocation zero is the production safety boundary; a cap of
one is the smallest nonzero process cap for the first measured ramp, not proof
that any 2–3 GPU fleet can sustain 60 synchronized requests alongside batch jobs.
Server overload rejection remains authoritative. Do not increase the cap without
measuring batch queueing, p95 latency and error rate under the actual pod count.

A 503, timeout (including waiting for the shared HTTP semaphore), malformed response
or transport failure kills the window leg, releases admission, and opens the
Parakeet serve-error circuit (existing default 180 seconds). A windowed socket
proves recovery only on its first successful POST; local construction cannot close
a half-open circuit. Generation-scoped callbacks release cancelled probes without
erasing a newer failure. There are no POST retries
or teardown retries against the failed provider. Local buffer overflow also kills
the session leg; local admission overflow does not poison provider health.

The new live path owns active VAD with a short TDT silence tail. Initial noise never
reaches TDT. VAD initialization failure skips TDT; inference failure closes its leg
before raw audio can escape. Silence boundaries flush subwindows, subject to the
same POST pacing, so repeated short utterances cannot defeat the per-session limit.
After the first POST, a short utterance can wait almost six seconds for its turn;
teardown may wait that interval plus the eight-second POST deadline. Cancellation
releases admission and cancels the outstanding request. Failed windows are not
replayed to a second provider: the normal offline capture/sync recovery still owns
that gap, as with existing mid-stream provider deaths.

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
A replacement is recovered only after a nonempty transcript, including TDT. A
successful empty TDT POST proves breaker health but does not settle failover recovery.
If every other leg is absent/open, one bounded primary probe can bypass its bench.
The flag-enabled preflight therefore leaves admission to the chain. The old path
retains its two-failover limit; the managed chain allows three hops across four providers.

Metrics: `omi_stt_chain_exhausted_total` increments once per terminal chain;
`omi_stt_leg_attempts_total{to_mode,outcome}` counts successful and failed actual
connections; shared `omi_stt_stream_close_total{provider,reason}` counts typed
budget/quota and authentication refusals at the provider boundary;
`omi_stt_window_sessions_active`, `omi_stt_window_sessions_capacity`,
`omi_stt_window_admissions_total{outcome}`, `omi_stt_window_posts_total{outcome}`
(success/empty/error/cancelled), and `omi_stt_window_post_seconds` expose TDT load.
No UID, transcript, URL or exception text is a metric label. The historical shared
fallback exhaustion metric counts legs and can exceed terminal session failures.

Grafana split `alerts/live-stt.json` and the combined export cover terminal chain
exhaustion, initialization failures versus accepted sockets, per-leg error ratios,
authentication deaths, overflow ratio, sustained cap occupancy and batch POST error ratio.
Traffic floors suppress ratio noise; saturation uses a dwell gauge. Existing
#15189 fallback alerts and #15218 budget/quota page remain; the auth rule excludes
budget refusals to avoid duplicate pages. New rules have no live Prometheus or notification
validation in this PR. Rollback: set allocation to zero to withdraw TDT only; restore
the old model list and disable the order flag to restore the complete legacy chain.
