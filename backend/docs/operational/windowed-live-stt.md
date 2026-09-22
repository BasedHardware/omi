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
| `PARAKEET_WINDOW_PACE_SECONDS` | `6` | `6` | `6` |
| `PARAKEET_WINDOW_MAX_CONTEXT_SECONDS` | `24` | `24` | `24` |
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
and the single in-flight slot allow. On that pause POST the last segment is
emitted only if it already ends with `.?!` — there is no 1.2 s gap, because
the gate has already stripped silence from the timeline. Treating every
`finalize()` as a forced cut re-anchors at a breath and the next POST starts
mid-sentence, which is the empty-clip failure mode.

Forced flush (emit everything, re-anchor at `now`) happens only on close /
`drain_and_close()`, ≥1.5 s of non-speech bytes after speech (ungated
callers), or **wall-clock idle**: no audio accepted by `send()` for ≥2.0 s
while unemitted speech remains after the anchor. Idle fires once per idle
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

One slot per one-process listen pod means at most 12 sessions at 12 replicas or
60 sessions at 60 replicas. Each session has one in-flight POST. The PCM buffer
holds two max-context windows plus two pace intervals of cushion: default
`2×24 + 2×6 = 60` s of mono PCM16, **≤ ~1.9 MB at 16 kHz**. That cushion absorbs a
catch-up burst while one POST is in flight without killing a healthy session.
The at-cap job already drains backlog 24 s per paced POST. Growing
windows re-post overlapping context as `now` advances, so GPU audio per session
is about **2.0×** fixed 6 s slicing. A minimum `PARAKEET_WINDOW_PACE_SECONDS`
(default 6) interval between POST starts still bounds sustained traffic; delivery
lag in simulation was p50 4–5 s, p90 7–11 s at 6 s pacing. Reconnects and initial
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
releases admission and cancels the outstanding request. Failed windows are not
replayed to a second provider: the normal offline capture/sync recovery still
owns that gap, as with existing mid-stream provider deaths.

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
(success/empty/error/cancelled/queue_timeout), `omi_stt_window_post_seconds`,
`omi_stt_window_context_seconds` (posted context duration), and
`omi_stt_window_forced_cuts_total` expose TDT load. `empty` means the posted
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
