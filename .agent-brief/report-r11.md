# Round 11: Soniox diagnostics safe to enable

Public `BasedHardware/omi`, prescribed worktree
`/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-capture-window-coverage-upstream-keep-clean`,
branch `lane/soniox-capture-axis`. Started exactly at
`ba11eea4a186149af2e9d042696f181d03a4b02b`; new implementation commit
`49742983dbd0b28efc5644888a84c54dbc3c5a5c`, followed by collector typing fix
`bb8482c377c09ccd449c185eca716ed6e8ce8209`. No history rewrite, fetch/sync, push,
PR, deployment, cloud client/credentials, customer data or provider network call.
The supplied Round 9 review, Round 10 report/brief, original safety rules and
Round 3 network-guard ruling were read before changes. Forbidden paths and all
existing capture/axis/runtime settings are unchanged. This is diagnostic-only;
`SONIOX_CAPTURE_AXIS_DIAGNOSTICS` remains false by default in code and declarations.

## R9 findings repaired

**P2 isolation.** Raw construction and flag admission are guarded before transport
setup continues. Managed binding guards flag lookup, method lookup and invocation.
Initial idle binding and each reopened transport binding have their own guards,
so binding exceptions cannot enter idle's transport-failure handler. Each actual
raw socket owns a failure latch: the first failure clears its diagnostic object
and attempts one `event="diagnostic_error"` increment; later hooks are skipped.
A reopened socket can independently start diagnostics again. Error labels contain
no exception text, socket/session identity or dynamic cause. A broken event
collector cannot report its own failure, but still cannot affect transport.

The same socket boundary guards queue admission accounting, setting and clearing
inflight state, successful-write accounting and raw response processing. Getter,
malformed diagnostic-field, histogram/counter and sampled-log errors also disable
that socket's diagnostics. The real WebSocket await is outside these catches:
actual write/connect errors retain existing transport death and failure behavior.
No diagnostic await/network call or retry was added. Partial observations emitted
before a failure remain; `diagnostic_error` is a reason to distrust an incomplete
measurement population, not proof that all preceding observations were invalid.

**P2 drained cohort.** Both the joint counter and all seven delta histogram
references now include `queue="drained|backlogged"`, computed by exact sample
comparison `written == queued` at response receipt. It is independent of
`write_state="settled|inflight"`. The R9 example queued=ledger=10 seconds,
written=1 second now reads `ledger="equal",write_state="settled",queue="backlogged"`;
it is excluded from the conserved drained cohort. Use the **joint counter** with
`ledger="equal",queue="drained",write_state="settled"` to select exact conservation
and no queued/inflight PCM simultaneously. This proves our completed WebSocket
PCM writes, not remote decode acknowledgement. Controls add zero PCM samples.

Delta histograms have the same queue/write discriminator, including processing
fields and ledger delta. They remain **marginal distributions**: they cannot
additionally select same-response ledger equality. Do not combine their buckets
to claim a joint conserved elapsed-clock cohort. Exact joint compact-overshoot
rates are available from the comparison counter; same-response numeric logs and
known-audio manifests are required for the clock equation.

**P3 OFF exposition.** All four new metric parents use `registry=None`. One
registered collector reserves their names through `describe()` and exposes
families through `collect()` only when the diagnostic switch is ON. OFF scrapes
contain no new HELP, TYPE or samples, even after previous ON observations.
Existing collectors/data are unchanged. Socket admission remains pinned at
construction; OFF immediately hides these families but does not reclaim the
constant-sized state of already-enabled sockets. Restart/new sockets apply the
OFF admission. Re-enabling in the same process can reveal earlier samples;
production queries must use a window entirely after the fresh enabled rollout.
No special case in the metrics endpoint or global registry mutation is needed.

The committed PR-facing contract is `backend/docs/listen_pusher_pipeline.mdx`;
local metadata is `.agent-brief/pr-body-r11.md`.

## Bounded resources and privacy

Full static Cartesian **upper bound: 1,150 series/process including `_created`**,
versus R9's 606. Seven references x two phases x two write states x two queue
states = 56 histogram children. Each has 14 buckets (13 finite plus +Inf),
count and created, and no sum because the buckets include negative boundaries:
56 x 16 = **896**. Three wire states x four ledger states x two phases x two
write states x two queue states = 96 comparison children x 2 = **192**.
Six event children x 2 = **12**. Five normalized providers (`soniox`, `modulate`,
`deepgram`, `parakeet`, `unknown`) x five detail reasons x 2 = **50**.
896 + 192 + 12 + 50 = **1,150**. Some label combinations cannot occur, so this
is conservative. With created samples disabled it is **967**. OFF exposes zero
series from these families. Existing scrape labels multiply the fleet bound by
process/target count; they are not new application labels.

State remains O(1) per actual socket: existing numeric counters/anchors/getter/log
allowance plus one failure boolean. Response work retains its O(tokens) scan and
O(final tokens) temporary numeric list. Queue comparison is O(1). Sample logs
remain <=4 per socket and <=1/minute/process. No audio, text or identity is retained
or logged. No updated CPU/memory benchmark or fleet-load claim is made.

## Offline proof and verification

`test_soniox_capture_axis_r11.py` compares healthy ON diagnostics with injected
faults through the actual managed connector, wire writer/receiver, receiver,
transcript tick and StrictFirestore fixture. It compares exact configuration,
two accepted PCM frames, finalize/end, decoded persisted transcripts and all
exercised existing Omi counter increments. It asserts continued logical/raw
connection health and socket diagnostic disablement. Cases cover construction,
constructor/managed flag hooks, bind/method lookup, raw binding, queued/inflight
set and reset, sent/response, getter, histogram/comparison/event collectors,
logger and simultaneous failing construction/bind/sent/response hooks. When the
error collector works, exactly one error is asserted for each failed socket.

Initial and idle-reopened binding faults separately assert unchanged PCM, raw
and offset transcript times, successful reopen, no logical death, no
`idle_reopen_failed`, no idle-failure increment and one diagnostic error.
Existing genuine wire/reopen failure suites remain in the focused/full checks.
Three queue cases assert the joint labels and all seven histogram increments;
OFF-after-ON/unset scrape checks assert absence of metadata and samples; a full
static-label enumeration verifies the upper bound with `_created` enabled.

The red/green driver temporarily installs only the four owning production modules
from the supplied HEAD, invokes **only** `backend/test.sh` with an explicit file
list, and restores candidate bytes in `finally`, with verified SHA-256 hashes.
The network guard and local 0.30-second call-phase guard remain unchanged.
The completed terminal proof is:

```text
base ba11eea4a1: 24 failed, 13 warnings in 12.31s; runner exit 1
candidate:       24 passed, 13 warnings in 9.14s; runner exit 0
```

Evidence: `r11-base-red.log`, `r11-candidate-green.log`,
`r11-red-green-results.json`, driver `r11-red-green.py` and file list
`r11-new-tests.txt`. Initial cardinality verification failed because the harness
suppresses `_created`; the corrected test explicitly enables that client setting
within monkeypatch scope. The initial red proof also needed its owned pytest
process terminated when old unguarded inflight failure prevented a wire frame
from arriving. Test-only wire waits now have a 0.1-second timeout, and the complete
red/green rerun finished normally. Initial logs/results are preserved under
`r11-initial-*`; they are not counted as the completed proof.

A separate OFF parity probe widens the existing real-path receipt to **all existing
Omi metric data samples** (counters, gauges, histogram buckets/counts/sums),
excluding `_created` metadata and the four new diagnostic families. It freezes
monotonic time and UUIDs in the fixture, compares supplied HEAD and candidate,
and restores all six production modules plus the temporary test modification
byte-for-byte in `finally`. Both receipts run through the explicit `backend/test.sh`
file-list runner: **1 passed, 22 deselected**, exit 0 each. Decoded persisted
transcripts, exact wire frames, and all existing metric deltas match exactly:
`r11-base-allmetrics-off.json == r11-candidate-allmetrics-off.json`.
Results and restoration hashes: `r11-allmetrics-proof-results.json`; driver
`r11-off-proof.py`. This is fixture-level parity, not a production claim.

Final validation is pinned to implementation `bb8482c377`; exact source hashes,
commands, exit codes and durations are in `r11-validation-results.json`.

```sh
BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/r11-focused.txt" \
  PYTHON="$PWD/backend/.venv/bin/python" BACKEND_PYTEST_WORKERS=4 bash backend/test.sh
# From backend/, for k=1..4, canonical total/index syntax:
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/1
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/2
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/3
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/4
# From worktree root:
PYTHON="$PWD/backend/.venv/bin/python" scripts/pr-preflight --suggest
PYTHON="$PWD/backend/.venv/bin/python" scripts/pr-preflight \
  --metadata-only --pr-body-file .agent-brief/pr-body-r11.md
PYTHON="$PWD/backend/.venv/bin/python" \
  OMI_PR_BODY_FILE="$PWD/.agent-brief/pr-body-r11.md" make preflight
```

Focused **47 files: 2,167 passed, 3 deselected**, zero failures/errors; exit 0,
84.92 seconds. All four canonical shard results:

| Shard | Files | Passed | Failed/errors | Skipped | Deselected | Exit | Seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| 4/1 | 400 | 7,126 | 0/0 | 5 | 621 | 0 | 282.01 |
| 4/2 | 400 | 7,379 | 0/0 | 20 | 123 | 0 | 272.28 |
| 4/3 | 400 | 7,533 | 0/0 | 2 | 1,288 | 0 | 378.82 |
| 4/4 | 400 | 7,790 | 0/0 | 0 | 60 | 0 | 559.09 |

Total: **29,828 passed, 27 skipped, 2,092 deselected**, zero failures/errors.
Each shard includes dependency preflight and typecheck: **zero errors**, 12,914
warnings, zero information. Terminal-summary recount independently verifies
**1,600 unique files, each in exactly one shard**, with one terminal summary per
file. Counts exclude duplicate deselection numbers at collection. Evidence:
`r11-terminal-counts.json`, `r11-focused.log`, `r11-shard-{1,2,3,4}.log`.

PR suggest: exit 0, 2.06 seconds. Metadata: **four checks passed**, exit 0,
7.12 seconds. Full preflight: **45 checks passed**, exit 0,
694.43 seconds (693.95 seconds reported by the runner). Logs:
`r11-pr-suggest.log`, `r11-pr-metadata.log`, `r11-preflight.log`.

The first final-validation attempt passed all focused test assertions but exited
1 for two **unchanged** test timing failures: 0.34 seconds in
`test_live_replay_provider_pairs.py::test_managed_soniox_internal_finish_still_fails_over`
and 0.33 seconds in the existing rendered-pusher drift test, against the unchanged
0.30-second CPU guard. Its logs/results are `r11-first-validation-*`. The final
focused rerun uses four file workers (selection and guards unchanged); canonical
shards run sequentially with their own prescribed worker setting. No allowlist,
threshold, network guard or CI runner was modified.

The first canonical typecheck found that the gated collector worked at runtime
but did not inherit the client's declared `Collector` ABC. New commit `bb8482c377`
adds that interface plus `Iterable[Metric]` signatures for collect/describe, with
no casts or suppressions and no runtime exposition change. Failed pre-unit
attempts and the interrupted third shard are preserved as
`r11-collector-typecheck-*`. Red/green, OFF parity and full validation were rerun
after the repair; only completed final runs below count as acceptance.

## Exact production queries for the coordinator (not executed here)

Run against **production Prometheus**, after rollout/enablement to GKE
backend-listen and `SONIOX_CAPTURE_AXIS_DIAGNOSTICS=true`, with `SONIOX_ELAPSED_AXIS=shadow` and all capture admission unchanged.
The checked-in production scrape config supplies `job="backend-listen-metrics"`,
`namespace="prod-omi-backend"`, `pod`, and `listen_track` (canary versus stable).
Keep cohorts separate; these labels already exist on scrapes. Wait for a complete
15-minute window under the enabled image and new sockets. Query failure/availability
first. Absence is not zero, and zero denominator/NaN is not evidence of safety.

1. Target health and diagnostic errors/availability:

```promql
up{job="backend-listen-metrics",namespace="prod-omi-backend"}

sum by (listen_track, event) (
  increase(omi_soniox_capture_axis_events_total{
    job="backend-listen-metrics",namespace="prod-omi-backend"
  }[15m])
)
```

Verify fresh enabled pods expose the new families and `audio` observations, then
use `diagnostic_error` and `ledger_unavailable` to assess completeness. Errors are
at most one per failed actual socket; this metric has no socket denominator and
is not a per-socket failure percentage.

2. Joint same-response counts including excluded queue/ledger cohorts:

```promql
sum by (listen_track, phase, queue, write_state, ledger, wire) (
  increase(omi_soniox_capture_axis_comparison_total{
    job="backend-listen-metrics",namespace="prod-omi-backend"
  }[15m])
)
```

`queue="drained",ledger="equal",write_state="settled"` means
queued == written == ledger-origin, with no current write. `wire="past"` means
raw final-token maximum end > successful PCM duration + 100 ms **before** all
adapter idle/gate/leg rebases. `no_audio` is separate, not a compact control.
Backlog, inflight and unavailable ledger observations do not qualify.

3. Raw overshoot fraction in the exact conserved/drained cohort, by phase/track:

```promql
(
  sum by (listen_track, phase) (
    rate(omi_soniox_capture_axis_comparison_total{
      job="backend-listen-metrics",namespace="prod-omi-backend",
      ledger="equal",queue="drained",write_state="settled",wire="past"
    }[15m])
  )
  or on (listen_track, phase)
  (
    0 * sum by (listen_track, phase) (
      rate(omi_soniox_capture_axis_comparison_total{
        job="backend-listen-metrics",namespace="prod-omi-backend",
        ledger="equal",queue="drained",write_state="settled",wire=~"past|within"
      }[15m])
    )
  )
)
/
sum by (listen_track, phase) (
  rate(omi_soniox_capture_axis_comparison_total{
    job="backend-listen-metrics",namespace="prod-omi-backend",
    ledger="equal",queue="drained",write_state="settled",wire=~"past|within"
  }[15m])
)
```

The zero fallback uses only an existing eligible cohort; it does not manufacture
a population when diagnostics/traffic are missing. Read the absolute counts from
query 2 alongside this fraction. Positive overshoot in initial phase establishes
an upstream raw mismatch despite PCM conservation; it does **not** select an
elapsed mapping. A reopened-only change implicates transport reset/resume handling
for investigation. If raw within dominates but persisted outside-send refusals
remain high, audit later mapping/rebase or late-final-versus-current-ledger effects.

4. Drained/settled marginal signed distributions for all clocks, including the
optional processing fields and queue-ledger difference:

```promql
sum by (listen_track, phase, reference, le) (
  rate(omi_soniox_capture_axis_delta_seconds_bucket{
    job="backend-listen-metrics",namespace="prod-omi-backend",
    queue="drained",write_state="settled"
  }[15m])
)

histogram_quantile(0.5,
  sum by (listen_track, phase, reference, le) (
    rate(omi_soniox_capture_axis_delta_seconds_bucket{
      job="backend-listen-metrics",namespace="prod-omi-backend",
      queue="drained",write_state="settled"
    }[15m])
  )
)

histogram_quantile(0.95,
  sum by (listen_track, phase, reference, le) (
    rate(omi_soniox_capture_axis_delta_seconds_bucket{
      job="backend-listen-metrics",namespace="prod-omi-backend",
      queue="drained",write_state="settled"
    }[15m])
  )
)
```

References are `token_minus_written`, `token_minus_queued`,
`token_minus_connected_elapsed`, `token_minus_first_write_elapsed`,
`queued_minus_ledger`, `total_audio_proc_ms_minus_written`, and
`final_audio_proc_ms_minus_written`. Use signed buckets/counts; no histogram sum
exists. Extreme values saturate finite buckets; quantiles are approximate.
Response-receipt elapsed includes recognition/network delay and scheduling after
the adapter-construction/first-completed-write anchors. The adapter anchor occurs
after WebSocket connection/config transmission, not at the captured source origin. Near-zero elapsed marginal deltas are only a hypothesis cue; they are
not same-response ledger-conditioned evidence or a captured-elapsed reference.
Negative token-minus-written deltas are expected for finals behind already sent
PCM. Reported processing clocks are not assumed to mean decoded PCM duration.

5. Decompose validator unknowns, retaining track separation:

```promql
sum by (listen_track, reason) (
  increase(omi_audio_timeline_elapsed_validation_detail_total{
    job="backend-listen-metrics",namespace="prod-omi-backend",provider="soniox"
  }[15m])
)

sum by (listen_track, outcome) (
  increase(omi_audio_timeline_elapsed_validation_total{
    job="backend-listen-metrics",namespace="prod-omi-backend",provider="soniox"
  }[15m])
)
```

`map_refused`, `no_gate`, `invalid_interval`, `vad_uncovered`, `classified` explain
availability, not provider clock causation. These are segment translation events;
the raw diagnostics count final-token responses. Do not divide one population by
the other or by distinct persisted segment counts.

## Decision: compact versus elapsed versus unresolved overshoot

Production metrics now directly answer whether raw overshoot persists on exact
conserved, drained writes, and separate backlog, accounting mismatch and reopen
phase. They cannot, by themselves, prove which server-side clock maps each word.
No response-time-only PromQL can decide that equation. Keep the elapsed admission
switch unselected until the following **independently authorized** known-audio
probe supplies source-time ground truth; this lane did not run it.

Use non-customer known speech A/B with known source/word positions. Independently
vary compact PCM duration, captured-but-withheld silence (5/9/34 seconds), a pause
with no incoming capture, and wire pacing. Repeat control/finalize variants, fresh
sockets at actual configured rates, idle reopen and paced replay. Save the exact
receiver admitted-span/sample manifest, successful wire sample totals, known word
positions and original raw start/end milliseconds before offsets. Match numeric
logs where sampled; preserve the response's written/queued/ledger-origin and
control counts. Recognition latency must be allowed separately from source time.

- **Compact supported:** raw A/B start/end positions follow compact emitted PCM
  offsets across withholding and independently paced no-input pauses; added withheld
  capture/no-input wall time does not move token coordinates. Low conserved-cohort
  overshoot supports this observation but alone does not prove it.
- **Captured elapsed supported:** A/B token offsets move by exactly the separately
  manifested withheld capture durations while compact writes are conserved, and
  independently varied no-input/pacing delays do not reproduce that change. Verify
  leading gaps, control behavior, resets and start/end intervals before proposing
  any translation; captured-withheld spans still must never become accepted audio.
- **Socket elapsed/other supported or unresolved:** token offsets move with independent
  wall pauses/pacing, controls, resets or provider-specific processing behavior rather
  than the known capture equation. Conserved raw overshoot confirms a mismatch, not
  permission to adopt captured elapsed. If evidence does not distinguish these cases,
  report unresolved and retain compact refusal. Histograms and sampled logs cannot
  recover unknown historical per-word provenance.

## Delivery and reviewer focus

Serving target for coordinator enablement is **GKE backend-listen** using the shared
backend image. Other hosts/pusher retain default-OFF declarations. No deployed flag,
revision, traffic, remote CI or production canary was inspected or changed here.
Implementation changes diagnose; they do not claim coverage recovery or repaired
server-side timestamp semantics. A report-only follow-up commit changes no validated
source/test/configuration bytes.

Reviewer focus: socket disablement/count-once boundaries (especially idle reopen
and real transport exceptions); exact response-time queue equality; OFF metadata
suppression and existing collector reservation; comparison versus marginal histogram
population limits; and the known-audio proof still required before elapsed admission.
