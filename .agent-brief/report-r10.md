# Round 10: Soniox capture-window axis

Branch `lane/soniox-capture-axis`, public `BasedHardware/omi`, prescribed worktree
`/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-capture-window-coverage-upstream-keep-clean`.
The supplied branch already pointed at supplied `origin/main`,
`4bdcc56d0dd4701af04cc423a310eb7445810708`. No fetch/sync was performed: this is an
explicitly offline lane. Implementation/test/doc commit: `6ccbf9340b`.

Read the workspace/root/backend guides, `.agent-brief/prompt.md`, the network-guard
ruling in `prompt-r3.md`, the prescribed earlier metric/loss analysis, and R9's
proof/report. No production API, cloud client, credential, account data, browser,
provider network connection, push, PR or deployment was used. Tests use only
explicit `backend/test.sh` file lists and the canonical unit runner; the network
guard stays intact. Fake Soniox connection objects never reach a network.
Forbidden app/sync/merge/capture-evidence paths are untouched. Existing flags,
including the supplied dev `AUDIO_TIMELINE_V2=true` declarations, are unchanged;
declared prod remains false. No axis/placement setting was enabled.

## Decision: no offline proof of an elapsed axis

**The code proves the adapter's transformations and its actual PCM/control send
paths. It cannot prove Soniox's server-side timestamp clock.** `SafeSonioxSocket`
converts original final-token `start_ms` and `end_ms` to seconds, subtracting only
its configured `preseconds` (zero on the managed chain). It does not convert
elapsed time to compact time. A word/segment's original provider timing reaches
`ProviderEpochTranslator.translate` before the managed gate/public-time rebase.

Soniox's managed connector configures mono `pcm_s16le` with the actual sample
rate. `LiveLegSocket.send` forwards the gate's `audio_to_send`: receiver PCM,
including admitted pre-roll and the speech/hangover tail. With active VAD, quiet
input after hangover is buffered then evicted/withheld; no PCM zeros are synthesized.
Off/shadow/fail-open VAD forwards receiver PCM, including silence, and registers
its source spans. An empty `audio_to_send` never calls raw `send`.

The adapter aligns odd byte boundaries, queues accepted PCM, then writes it in
FIFO order. `send=True` proves local queue admission, **not** successful wire
write or remote decoding. Recovery pacing/expiry can prevent a queued packet
from being written. This distinction can reduce received audio relative to the
ledger; it cannot explain an unregistered extra silence waveform. New diagnostics
measure aligned queue admission and completed WebSocket writes separately.

There are no hidden keepalive **audio** frames in this path:

- The ten-second queue timeout sends text `{"type":"keepalive"}`.
- VAD/manual finalization queues text `{"type":"finalize"}`.
- Finish sends an empty **text** frame, after queued audio, if audio was sent.
- The WebSocket library's protocol pings are also not PCM.

Neither our code nor the supplied aggregate proves whether the remote server
advances an elapsed clock during those controls or gaps. No correction can be
justified from their presence alone. No proven missing managed-send registration
was found: with `LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS` ON, successful raw queue
admission is recorded before a later finalize failure; VAD output spans include
pre-roll/hangover, and raw replay prefixes use the merged accepted-send recorder.
The real-path fixture confirms byte/sample conservation on this path. It is not
a claim that every production session conserves samples.

## Reconnect/replay offsets and the shadow's limits

A new managed provider leg gets a fresh epoch/send map. Its raw socket starts at
its own provider origin. The capture mapper registers actual replay/live sends
onto their observed capture positions. For legacy public timestamps, managed
callbacks subsequently apply the gate remap and `session.audio_seconds` offset
and clamp to `last_end`. Same-provider recovery uses the replay origin and
stitches public times from translated capture samples instead. These later
public-clock changes do not establish the provider axis and cannot repair an
initial raw compact-map refusal.

Planned `IdleSonioxSocket` reopen is different: it keeps the logical leg/ledger,
creates a fresh raw transport, and **before** the epoch callback adds the configured
resume provider offset (`last_send_provider_start` from the pending admitted onset;
cumulative admitted PCM is the fallback). It also clamps to the logical `last_end`.
An earlier overshooting final can therefore influence later clamping. Word ranges
receive the explicit offset too. This is a real offset to audit, not proof of an
elapsed axis. The checked-in production sources do not bind `SONIOX_IDLE_CLOSE_SECONDS`;
its code default is zero. Live overrides were not inspected.

`SONIOX_ELAPSED_AXIS` defaults to `shadow`. Compact placement/ownership remain
unchanged; a second send map hypothesizes provider-axis space equal to positive
`wall_strict(capture_start) - previous_accepted_wall_end`, rounded to samples.
The gap receives **no accepted span**. The first accepted send starts at zero:
leading withholding before that first send is not modeled. Capture/wall hiatuses,
replay/non-monotonic capture, unavailable compacted anchors, network pauses and
provider-specific controls are not mechanically equivalent clocks.

`off` omits the candidate map. `on` actually selects the hypothesis for Soniox
send placement; there is no automatic live-proof gate inside that setting. It
must remain unselected until the provider axis is independently proven. R10
changes only the misleading shadow comment/doc, not the map or its selector.
Existing elapsed-looking synthetic tests encode a hypothesis; they do not prove
remote timing. Expanding compact overshoot tolerance, treating withheld capture
as received, or promoting the shadow would fabricate evidence. All remain refused.

## Validator semantics and why unknown is largest

Each numeric Soniox segment translation in healthy shadow validates the candidate
elapsed-map interval; Modulate validates its compact map as a control. The receiver
compares that interval with the gate's retained raw input-chunk decisions:

- `on_speech`: full interval coverage; every covered chunk is marked speech.
- `on_silence`: full coverage; every covered chunk is marked non-speech.
- `partial`: speech and silence both contribute, or any overlapped chunk has the
  mixed-window marker `None`.
- `unknown`: candidate mapping returned no interval, no gate is available, the
  interval is nonpositive, or retained decisions fail to cover its complete span.

The history cap is **2048 chunks**, not a fixed number of seconds. Late finals,
missing source positions and eviction can leave it uncovered. Coarse per-chunk
VAD labels and buffered classifier windows do not prove sample-level speech;
`on_silence` alone does not prove hallucination or clock mismatch.

The supplied Soniox counters sum to 80,058 validation events, of which 41,249
(51.5%) are `unknown`. These are translated segment events, not distinct segments,
wire responses or whole sessions. The code explains why unknown is broad; the
supplied metric **does not identify which reason dominates it**. Neither the
29–34% distinct-segment loss nor 100% Soniox/managed/after-last geometry proves
elapsed-clock causation. We must measure the decomposition before assigning the
largest bucket a causal explanation. Modulate's different send/VAD policy is not
a controlled proof of Soniox's timestamp convention.

## Added: one default-off diagnostic switch

`SONIOX_CAPTURE_AXIS_DIAGNOSTICS=false` in code, base/dev/prod compose inputs,
regenerated runtime manifest, all four listen/pusher Helm values, feature registry
and deployment classification. The registry doc was regenerated. No new capture
behavior or schema is introduced.

`utils/stt/soniox_capture_axis.py` owns the state and metrics. Each enabled actual
socket retains constant-sized sample/control counters, two monotonic anchors,
a compact-ledger getter and a log allowance. No audio/text/identity is retained.
Admission is pinned at raw-socket construction; disabling the environment applies
to new sockets. Validation-detail admission is read at its call boundary.

Metrics:

- `omi_soniox_capture_axis_delta_seconds{reference,phase,write_state}`: raw original
  final-token maximum end in a response minus aligned queued/written PCM duration,
  adapter-construction/first-successful-write elapsed time; queued minus compact
  ledger samples; optional reported `total_audio_proc_ms`/`final_audio_proc_ms`
  minus written PCM. Processing-field meanings are not assumed. Signed histograms
  have finite static buckets and count/bucket samples; the Python client omits
  sums when negative buckets are configured. Use bucket distributions.
- `omi_soniox_capture_axis_comparison_total{wire,ledger,phase,write_state}`: same-response
  joint evidence. Wire is `no_audio|within|past` (>100 ms beyond written PCM);
  ledger is `equal|queue_ahead|ledger_ahead|unavailable`, with **exact** sample
  conservation, no edge tolerance. That 100 ms is diagnostic only.
- `omi_soniox_capture_axis_events_total{event}`: successful audio/keepalive/finalize/end
  writes, missing ledger and diagnostic errors. Text adds zero samples.
- `omi_audio_timeline_elapsed_validation_detail_total{provider,reason}`: hierarchical
  `map_refused|no_gate|invalid_interval|vad_uncovered|classified`. Map refusal has
  precedence if both map and gate are absent. Existing validation counters retain
  their names, labels and increments.

`phase=initial|reopened` separates actual idle transport reset. Reopened compact
ledger comparison subtracts the exact configured resume offset. Initial phase
also includes new managed recovery/failover legs. Elapsed-axis `on` intentionally
makes the compact-ledger getter unavailable. `write_state=inflight|settled`
marks a write currently awaiting completion; settled can still have queued backlog.
Compare queued AND written samples, not only a no-inflight state.

On raw overshoot, a numeric-only `soniox_capture_axis_sample` log holds the same
response's raw end, rate, queued/written/ledger sample counts, ledger origin,
relative monotonic times and successful control counts. Bound: **four logs per
actual socket and one log per minute per process**. No session/UID labels or
transcript/audio dumps. Exceptions in diagnostic response processing, getters,
metrics or logging do not suppress token parsing. Successful write accounting
is outside the transport error domain; write failures remain real transport failures.

The diagnostic population is original-final-token **responses**, not persisted
segment IDs. A response with several finals uses their maximum end once; replay
can recount. Processing-only responses can add processing histograms without
adding token comparisons. These rates cannot be substituted into distinct-segment
coverage denominators.

## Exact production measurement / proof plan (not executed)

After the coordinator chooses to deploy and enable diagnostics on listen, keep
`SONIOX_ELAPSED_AXIS=shadow` and all capture admission unchanged. Aggregate by pod/
cohort externally using existing scrape labels, without adding metric identity:

```promql
sum by (phase, wire, ledger) (
  rate(omi_soniox_capture_axis_comparison_total{write_state="settled"}[15m])
)
sum by (reason) (
  rate(omi_audio_timeline_elapsed_validation_detail_total{provider="soniox"}[15m])
)
sum by (reference, phase, le) (
  rate(omi_soniox_capture_axis_delta_seconds_bucket{write_state="settled"}[15m])
)
```

Measure:

1. At matched numeric samples, is `queued == written == ledger - origin`? If
   successful written PCM exceeds that last quantity, there is real missing
   accounting to trace. Queue backlog or failed writes are not extra received
   audio. The deliberate missing-ledger real-path regression proves the detector.
2. With conservation and no in-flight write, are raw token ends still >100 ms
   beyond written PCM? If yes, the mismatch exists **before** our idle/gate/leg
   rebases. If initial raw responses remain compact but outside-send losses occur
   on reopen, audit idle offset/clamping separately. Quantify initial vs reopened
   and compare processing clocks. Unavailable/error observations are not proof.
3. Break old unknown into map refusals, absent gates and uncovered retained VAD
   history. Give each reason its own denominator. A large classified speech share
   in the hypothesis does not establish an exact timestamp equation.
4. To prove an exact translation, use an independently authorized controlled
   session with non-customer known audio and a receiver send manifest: A speech,
   then 5/9/34 seconds of withheld silence, then B speech. Repeat fresh sockets
   at actual configured rates; contrast captured-withheld input with no incoming
   audio, and control/finalize boundary variants, then idle reopen and paced replay.
   Record exact admitted sample spans and completed wire byte counts, and raw A/B
   token times before offsets. Correlate the same-response numeric sample with
   known source/time positions; allow provider recognition latency separately.
   Compact duration, captured elapsed duration and socket elapsed duration must
   be varied independently. Exact known-audio token deltas must follow the proposed
   equation across pauses and resets, not merely correlate with speech labels.

Fleet histograms can prove conservation failures/raw overshoot populations; they
cannot alone prove a per-word affine mapping or resurrect old missing provenance.
The controlled probe supplies that missing independent source/time reference.
Only then implement a mapping/send repair for future accepted spans, with its own
strict interval proof. Nothing in R10 grants windows to unproven audio.

## Real-path red/green and exact OFF parity

`test_soniox_capture_axis_r10.py` invokes the real `LiveChainSession.connect`
managed callback, `process_audio_soniox`/`_open_soniox` config, SafeSoniox queue and
wire writer/receiver, actual VAD state machine/remapper (only classifier decisions
are deterministic), epoch translation, receiver enqueue, transcript process loop,
and decoded StrictFirestore persistence. No parser-only shortcut or fake production
capture window. Cases cover compact/elapsed-looking/cross-gap timestamps with the
switch OFF and ON; correct compact `[7.2,7.8)` capture is asserted exactly to one
sample; elapsed/cross-gap text persists without a window.

Other regressions cover successful keepalive/finalize with zero PCM samples,
actual non-16k config, failed wire writes, all VAD classifications and retained
history gaps, idle reopen's exact ledger origin and raw-before-offset histogram,
and real-path missing-ledger/getter-error behavior. Existing Soniox idle/recovery
suites are included in the focused/full validation. All new tests use the default
0.30-second local call-phase guard, with no threshold/selection/network bypass.

`.agent-brief/r10-proof.py` temporarily installs only the exact five owning base
modules from `origin/main`, runs the same file list through `backend/test.sh`,
and restores candidate bytes in `finally`, verified by hashes. The diagnostic
utility is new; its direct utility tests can pass on base, while missing real-path
wiring fails. Final base: **13 failed, 10 passed**, no collection/infrastructure
errors. Candidate: **23 passed**. Red is evidence of missing diagnostics, not a
claim of repaired provider-clock behavior. `r10-proof-results.json` records the
commands, hashes and verified restoration.

A separate OFF test freezes generated UUIDs and compares the base and candidate's
complete decoded persisted transcript payloads (known and refused finals), exact
Soniox wire frames including config/PCM/finalize/end, and nonzero increments of
all existing Omi `_total` counters exercised by the fixture. They match exactly:
`r10-base-off.json == r10-candidate-off.json`. Process/GC collectors are excluded;
new diagnostic families are separately excluded, and OFF creates no diagnostic
state. Both receipts: **1 passed, 22 deselected**. OFF/ON behavioral controls and
all ordinary existing suites retain their actual assertions.

The final expanded OFF probe (`r10-allmetrics-proof.py`) runs that same real-path
receipt case with a frozen monotonic clock and widens the temporary fixture's
snapshot to **all existing Omi metric data samples**: counters, gauges, histogram
buckets/counts/sums. Collector creation timestamps are excluded as registration
metadata, as are the new diagnostic families. Base and candidate receipts match
exactly: `r10-base-allmetrics-off.json == r10-candidate-allmetrics-off.json`.
Each run: **one passed, 22 deselected**. The probe restores all five production
modules AND the shipped test byte-for-byte in `finally`; `r10-allmetrics-proof-results.json`
records verified restoration and source hashes. The original 23-case red/green
and counter-parity proof was rerun afterward and remained green/exact. None of
these fixture-only probes changes the validated commit or production clock.

## Validation

Validation is pinned to `6ccbf9340bbb930f4bafbcca86ec7ef9f89f6de2`. All 21 changed source/test/doc/
configuration files match that commit byte-for-byte at handoff; hashes are in
`r10-validation-results.json`. The report-only commit changes none of them.

Focused **46 files**: **2,143 passed, three deselected**, zero failures/errors/skips,
exit 0, **33.77 seconds**:

```sh
BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/r10-focused.txt" PYTHON=.venv/bin/python bash backend/test.sh
```

All four canonical commands ran sequentially from `backend/`:

```sh
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/1
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/2
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/3
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/4
```

| Shard | Files | Passed | Failed/errors | Skipped | Deselected | Exit | Seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| 4/1 | 400 | 6838 | 0/0 | 20 | 668 | 0 | 188.57 |
| 4/2 | 400 | 7502 | 0/0 | 1 | 91 | 0 | 220.27 |
| 4/3 | 400 | 7758 | 0/0 | 2 | 1286 | 0 | 208.67 |
| 4/4 | 399 | 7706 | 0/0 | 4 | 47 | 0 | 197.98 |

Total: **29,804 passed, 27 skipped, 2,092 deselected**, zero failures/errors.
Independent group/terminal-summary recount verifies **1,599 unique test files**,
each executed in exactly one shard; `r10-terminal-counts.json`. Terminal summaries
are counted once, excluding the duplicate deselection numbers printed at collection.
Each shard includes canonical dependency preflight and typecheck: **zero errors**,
12,914 warnings, zero information. No unit selection, timing or network guard was
relaxed. Logs: `r10-focused.log`, `r10-shard-{1,2,3,4}.log`.

After shards, local metadata and preflight ran from the worktree root:

```sh
PYTHON="$PWD/backend/.venv/bin/python" scripts/pr-preflight --suggest
PYTHON="$PWD/backend/.venv/bin/python" scripts/pr-preflight --metadata-only --pr-body-file .agent-brief/pr-body-r10.md
PYTHON="$PWD/backend/.venv/bin/python" OMI_PR_BODY_FILE="$PWD/.agent-brief/pr-body-r10.md" make preflight
```

Metadata: **four checks passed**, exit 0, 2.65 seconds. Full preflight:
**45 checks passed**, exit 0, **199.20 seconds** (198.99 seconds reported by its
runner). Draft cites `INV-MEM-4`, the validated failure class, and a two-line
receiver exception (2433 -> 2435) for the utility import/call. Logs:
`r10-pr-suggest.log`, `r10-pr-metadata.log`, `r10-preflight.log`.

An initial post-shard wrapper invocation exited 127 before any check ran because
the driver used backend-relative `.venv/bin/python` from the root. The finish
driver uses the absolute owned backend interpreter; all checks above then passed.
`r10-validation-driver.log` retains that infrastructure failure and the successful
rerun; `r10-validation-results.json` records the final successful commands.

Static runtime manifest/workflow validations also passed for dev and prod, using
`.venv/bin/python scripts/validate-backend-runtime-env.py --env <dev|prod> --check-workflows`
from `backend/`. Two existing deployment fixtures were updated with the new false
literal; they are green in focused and all-shard runs. The bare-pytest
`pre-deploy-check.sh` wrapper was not used because this lane restricts backend
execution to the hermetic runners; its runtime validator and fixture coverage
were exercised through the authorized routes above.

## Delivery and residual limits

This is an attribution/diagnostics-only commit. No coverage recovery or fleet
improvement is claimed. The exact provider clock, largest unknown cause, and
missing-accounting population remain unproven pending the measurements above.
Successful WebSocket writes establish our emitted PCM, not a provider decode ACK;
optional processing fields help expose that distinction without assuming semantics.
VAD decisions remain coarse and bounded. Logs are sampled, so absence of a sample
is not absence of an event. The histogram/response population differs from the
coordinator's distinct-segment population.

The serving target is **GKE backend-listen** (shared backend image). Cloud Run
backend shares the listen code if that surface serves it; sync/integration hosts
have inert default-off declarations. Pusher has an aligned default-off mirror but
is not the Soniox managed-chain capture producer. No image/revision/flag has been
published by this lane. No remote CI, deployed canary or production acceptance is
claimed. The local report commit follows source validation without changing the
validated implementation.
