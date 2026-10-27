# Live STT routing

## Controls and evidence contract

Production merges in `STT_ROUTING_MODE=shadow`, `STT_ROUTING_ON_PERCENT=0`.
The configured fallback order is Parakeet window → Soniox → Modulate → retired
Deepgram. Parakeet allocation/capacity remain independently approved controls;
do not copy an older allocation percentage from this runbook. The static reorder
avoids exposing shadow and rollback sessions to the known Modulate brownout.
The active router still chooses the cheapest capable healthy target, with no
artificial diversification or expensive-provider probes.

`LiveLegOutcome.settle` emits a serving decision's fallback and router observation
once, synchronously. The source cause survives successor rejection and cleanup.
Liveness reads emit neither. Normal client/owner close is success if text was
seen, otherwise censored. Teardown snapshots the published death latch before
closing: an already-dead provider counts even if the monitor has not claimed it;
transport errors that begin after this fence remain censored. A provider death is counted without a speech minimum
when the serving owner replaces/rejects it or exhausts recovery. A pending hop
without successor text settles as degraded after 30 seconds, with no socket or
audio change. Established fallback reasons stay stable, including quota/auth;
health retains the corresponding typed account reasons. Soniox 408 uses censored `soniox_request_timeout`; 400 no-audio uses
`soniox_idle_timeout`. Neither opens a provider circuit for all users, including connect rejection.
Repeated Soniox 408 connect rejections deliberately do not create a cross-session
bench: this cause cannot distinguish a provider outage from client/input timing.
Each connection still falls through to the next provider. Accept that repeated
connect cost/latency risk; inspect its reason counter and transcript/latency SLIs
and withdraw the endpoint manually if the aggregate shows an outage.
Local VAD and other explicitly censored input/configuration failures also release
circuit admission without accumulating provider failures.
A Parakeet window whose own pump task listen cancelled (owner close, recovery
switch, teardown) reports the censored reason `cancelled`, not `connection_lost`,
so listen-side cancellation cannot bench Parakeet through the disruption gate.
A pump that ends on its own, or a POST/transport error, still reports a provider
reason (`connection_lost`, `provider_5xx`, `timeout`).

`omi_stt_cost_routing_settlements_total{target,outcome,reason,path}` is the
expected observation count from that seam (`path=close|failover|connect`). Its
sum over path must equal `omi_stt_cost_routing_observations_total` by
instance/target/outcome/reason. This comparison covers exactly the managed
router population; legacy/PTT fallback events are not extra router samples.
A direct acknowledgement from the observation writer feeds the single
`omi_stt_cost_routing_emission_ack_errors_total` counter; exceptions or missing
acknowledgements increment it. This checks acknowledgement only: neither this
counter nor the paired emissions detects omitted terminal paths or consistently
wrong classification, and neither proves Redis persistence. Redis drop counters and
`omi_stt_cost_routing_votes_total{target,scope,result}` prove whether classified
evidence reached shared state (`applied|user_cap|window_full|generation|stage`).

State uses `omi:live-stt:cost-v8:<stage>:<32-hex identity>:<target>:<bounded-language>`
with recovery lease keys under the same cost prefix. Fleet keys split two
`omi:live-stt:fleet-v2:<stage>:<32-hex identity>` scopes: selection bench,
recovery probe and score keys digest the family, actual endpoint and
credential, while the account bench key digests only family and credential, so
the credential-wide quarantine spans every custom endpoint but survives an
endpoint rotation that resets selection/score/probe and cost state. Registry
targets with a custom `endpoint` write and read their own endpoint-scoped
selection/score/probe partitions — a sibling endpoint's serve deaths, connect
refusals and transcript outcomes never bench the configured default or other
siblings, while the credential-wide account bench still protects all of them.
With `STT_ROUTING_MODE=off` snapshots answer a neutral score and merge only
family account deadlines, ignoring but not erasing selection state. The stage
comes from `OMI_ENV_STAGE` (unrecognized values map to `unknown`, never prod;
`PROVIDER_MODE=offline` still yields `offline`);
a changed endpoint, credential or stage starts its scoped state
with no migration or backfill of older namespaces, which are never read. Raw
URLs and keys never appear in Redis paths, logs or metrics. A pod's in-memory
health views reset when that identity changes. Process-local selection
breakers differ: they retain connect/serve outage evidence across credential
rotation for an unchanged endpoint — credential rotation clears
account/quota state only, an endpoint change starts fresh selection state
while the unchanged credential's account protection remains, and a stage
change starts fresh scoped state. A custom endpoint's serve death opens
that endpoint's local target breaker and does not bench the family default. Do not
reuse older-namespace evidence. At stage 100, one hashed user contributes at most three
success/failure outcomes in a five-minute Redis-time window. Windows hold at
most 2,048 ordinary fingerprints (above 1,500 at 10x 1,800 sessions/hour),
plus an eight-fingerprint outage reserve. At saturation, eight distinct new
users failing without an intervening classified success bench the target. Every
success resets this reserve, even if its normal vote is capped; one repeated
caller cannot fill it, and it cannot fill without benching. This reserve does
not feed failure-only samples into CUSUM or refill existing user budgets. Any
`window_full` remains a rollout stop because normal brownout evidence is sampled. Healthy
state keys expire after 900 idle seconds; benched/trial state persists to prevent
expiry bypassing staged recovery and holds no healthy-window fingerprint list. Raw observation counts remain uncapped for
reconciliation. Trials retain their separate user votes, generation fences,
5→25→100 shares, and exponentially increasing cooldown. Trial promotion needs
30 admitted outcomes from at least 10 witnesses after 300 seconds for the 5%
step, and 60 admitted outcomes from at least 20 witnesses after 600 seconds for
the 25% step; a completed admitted window before the dwell holds at its stage.
Recovery re-benching uses two tiers of **admitted, non-censored outcomes in
the current trial window**. Ordinary rejection needs at least 100 outcomes,
the same CUSUM burst evidence as stage 100, broad failure witnesses, and a
user failure share above the gate. A fast path for a truly broken provider
needs at least 20 outcomes, at least 25% attributable failures, and broad
failure witnesses. One or two timeouts in a tiny trial do not qualify.
The former 30/60-outcome rate-only rejection is removed. Promotion, dwell and
bounded trial windows (120/240 outcomes) are unchanged; completing the clean
5→25→100 ramp clears the consecutive failure history. The default-on
`STT_ROUTING_RECOVERY_SAMPLE_GUARD_ENABLED` switch restores the former rules
when explicitly set to `false`, `0`, or `off`.
To retain the chronic-provider disruption budget with the larger recovery
sample, a guarded re-bench advances two cooldown exponents (instead of one)
and caps the wait at six hours. After a first full-traffic bench, successive
failed recovery trials wait 20 minutes, 80 minutes, 320 minutes, then six hours.
A single false bench still starts its first 5% recovery after five minutes.
Stage-100 detection/cooldowns are unchanged. The deterministic 17,900-session,
61%-failure daily replay retains its original bounds: fewer than 100 failed
sessions including the initial detection allowance and fewer than 200 trials.
Redis CAS enforces all
of this fleet-wide. Bench writes are one atomic Lua update — an active account
quarantine rejects a selection write, same-kind writes keep the longest
deadline — and expired cleanup is a compare-delete that re-checks the observed
value inside Redis before removing it, so a renewed bench survives a read/delete
race. Shared snapshots refresh off connect, normally every five
seconds, under a 75 ms deadline; local fallback retains known benches.
Every refresh reads all registry targets across the closed supported-language
vocabulary plus `all`, so a language bench is honored on its first request even
without prior interest. Freshness is per `(target, language)`; an unread
language raises `CostHealthUnavailable` instead of reporting stage 100, which
the chain treats as a fail-open: non-canary sessions keep the filtered static
order, while canary sessions keep their permitted registry target routes with
the exception's conservative states demoting known restricted entries (a
generic router error carries no snapshot and keeps configured order).
Per-target language
comparisons are counted in
`omi_stt_cost_routing_language_state_total{target,comparison}` with
`agree|language_restricted|global_restricted|unknown|stale`.

Every dial — proposal candidates, last resorts and the static fallback in all
modes — passes the same permission filter: actual engine match, capability for
the requested and expected languages, sticky registry ramp (including the
`parakeet-window` minimum of registry percent and window allocation), and
active account quarantine. If filtering empties the chain the connect raises
`ProviderChainUnavailable` with a bounded retry and counts
`omi_stt_cost_routing_no_permitted_target_total`. An invalid registry cannot
prove permissions, so a managed session gets the typed chain-unavailable and a
`router_error` fail-open rather than a default that could reopen a withdrawn
target.

The [architecture](../../utils/stt/ARCHITECTURE.md#serving-owned-health-evidence-cost-v8)
has the taxonomy, registry and second-endpoint example, exact gate, and
reproducible calibration. The gate stays 8%. In gate simulation, every
realistic-floor row has zero false benches in 400k sessions; 40%/60%/100%
provider errors bench at median 20/13/8 and p95 48/21/8 sessions. At 62 sessions
per five minutes that is about four minutes at the 40% p95, plus settlement
and cache delay. The rate must be representative admitted votes, not one
client's repeated reconnects. These are synthetic bounds, not prod acceptance.

## Audited operator cost-gate reset

After a confirmed false bench, an authorized operator may reset **one registered
target** using the deployed backend image and its existing runtime environment.
Complete the rolling deployment first so old pods cannot reconcile pre-fix local
fault evidence. This action writes cost-routing state, not user/account data.
It does not change account quarantines, endpoint circuits, admission capacity,
language capabilities, or allocation. No runtime config change is required;
leave `STT_ROUTING_RECOVERY_SAMPLE_GUARD_ENABLED` unset or `true`.

Run from `backend/` in that environment, first without `--apply`:

```bash
python scripts/reset_live_stt_cost_gate.py --target parakeet-window --environment prod --reason sttbench-20261027-06z
python scripts/reset_live_stt_cost_gate.py --target parakeet-window --environment prod --reason sttbench-20261027-06z --apply
```

The explicit environment must match `OMI_ENV_STAGE`. Both commands print only
the target, environment, change identifier, stages and generations by language.
Apply uses one Redis WATCH/MULTI transaction for `all` and every supported
language: clears evidence/strikes, sets stage 100 and advances each generation.
Generations advance into a new Redis-time reset epoch to also supersede
unreconciled pod-local fault generations. Every dial captures that epoch before
awaiting the handshake; connect failures may follow ordinary gate changes but
cannot cross an operator reset. A separate content-free generation floor
persists under the target identity, so expiry of the normal 900-second healthy
evidence key cannot re-admit a long-lived pre-reset session's votes. Refresh
and cold writers seed missing evidence from that floor. The reset epoch carries
no user/fairness data; the normal fairness-data TTL remains unchanged.
A competing health update retries the entire reset, at most five times.
The same transaction writes a content-free audit receipt under the target's
endpoint/account namespace for 30 days; stdout and the warning log contain
the receipt and its `audit_id`. Retain the output in the operator's train record.
This is a one-time reset; subsequent real failures can immediately bench again.

After the next shared refresh (normally five seconds), verify stage 100 on every
fresh pod and check language state, timeout counters, transcript success and
first-text latency. A transport interruption after submission can make the
command's result uncertain: use the pre-submit log's `audit_id` to read that
target's `operator-audit:<audit_id>` receipt through the same runtime namespace
and inspect fresh stage telemetry before retrying. A repeated apply advances generations
again, so do not run it as a recurring job.

To reverse the release, use the same command with `--stage 0`, a new reason and
`--apply`: it benches the target for five minutes and then resumes normal staged
recovery. Removing the command or changing the guard switch does not undo a
committed reset. A malformed scope aborts the entire transaction, preserving all
existing state. Healthy state retains the normal 900-second idle TTL; a reversed
bench persists until normal recovery advances it.

## Minimum shadow go/no-go (normally 60–120 minutes)

Start the observation window after every listen pod runs the same new image and
has been scraped. Do not reset shared state mid-window. Require at least 60
minutes plus the following positive coverage; elapsed time alone never passes:

1. At least 500 proposals, 100 settled classified Parakeet legs, and 100 Soniox
   legs. Inspect every observed language group and all provider-failure reasons.
   The new seam's real-parser/receiver tests must be green on the deployed SHA.
2. No persistent opened-minus-settled-minus-open lifecycle gap; exactly zero
   emission acknowledgement errors, evidence exceptions, unavailable
   proposals and all-degraded selections. No Redis result drops, saturated
   evidence windows, router/cache errors or unknown/stale snapshots.
3. Parakeet and Soniox global stage 100 on every fresh pod, with no unexplained
   language bench. Proposal shares match current allocation and capabilities;
   no healthy admitted Parakeet primary is diverted to a costlier target.
4. Modulate either demonstrates its bench/5% recovery on real fallback evidence,
   **or is explicitly withdrawn with registry `ramp_percent=0` in the on config**.
   Static Soniox-first order can legitimately yield too little Modulate traffic
   to warm its new namespace. Unknown/untested Modulate is not permission to
   send it new primary traffic. Do not manufacture probe traffic to qualify it.
   A complete registry override must retain Parakeet and Soniox entries; after
   active selection their registered Modulate sibling cannot reappear as a
   static tail. Router-error fail-open keeps permitted registry targets for
   canary sessions and the filtered static chain otherwise.
5. Transcript-success, no-text share, first-text latency, window capacity and
   GPU pressure remain within the conditions below. Confirm the existing
   transcript-success alert is evaluated and routed to the live contact point.

If low-volume coverage is missing after two hours, keep that target withdrawn
or remain shadow. This is a bounded first canary, not 24-hour reliability proof.
A new Modulate endpoint later enters through its own registry ID and 5% ramp;
its evidence must never reuse the old endpoint's identity or state.

## Exact PromQL

Use `job="backend-listen-metrics"`, and a window containing only the new image.
The **emission acknowledgement check** below must be zero; it is not an
independent correctness oracle. Missing metrics are failure of coverage, not zero.
The paired-counter difference is also useful by instance/target/reason, but a
scrape reads separate collectors at slightly different instants: a transient
difference during active settlement can be a scrape race. Require that the
one-minute minimum paired difference is zero, and investigate any persistent
mismatch; do not mistake `increase()` extrapolation or a first scrape for lost
evidence.

```promql
sum(omi_stt_cost_routing_emission_ack_errors_total{job="backend-listen-metrics"})
min_over_time((sum(abs(
  sum by (instance, target, outcome, reason) (omi_stt_cost_routing_settlements_total{job="backend-listen-metrics"})
  -
  sum by (instance, target, outcome, reason) (omi_stt_cost_routing_observations_total{job="backend-listen-metrics"})
)))[1m:15s])
sum(increase(omi_stt_cost_routing_evidence_errors_total{job="backend-listen-metrics"}[1h]))
sum by (target, path, outcome, reason) (increase(omi_stt_cost_routing_settlements_total{job="backend-listen-metrics"}[1h]))
sum by (from_mode, reason, outcome) (increase(omi_fallback_total{job="backend-listen-metrics",component="stt_live_session"}[1h]))
```

The last query includes legacy/PTT traffic and uses provider-family labels;
endpoint-specific equality is checked by the paired-counter difference. For managed failure
settlements, account labels map budget→quota and rejected-auth→auth. Connect
settlements belong to `stt_selection`, terminal deaths to `stt_live_session`.

Deaths are eligible at the first serving claim, not at a read-only liveness
poll. Explicit client/application disconnect, inactive state or shutdown at
that claim excludes the death and suppresses its fallback emission. A claim
already made with a connected client remains valid after later departure.
Existing text remains one success; otherwise the excluded leg settles as
censored no-text. Repeated claims/close/validation cannot revive a settled leg.
The backend cannot recover the ordering of an unclaimed raw death and client
departure retrospectively.

For a fixed accepted-socket cohort and bounded provider reasons:
`provider_failure observations = settled nonterminal hops + connected terminal deaths`.
Terminal deaths now also emit fallback to `unavailable`, so do not add their
session-level terminal counter to the whole fallback total again. Connect-chain
exhaustion remains a separate surface and can be zero for a serving terminal
Soniox death. Excluded deaths have no provider-failure or hop emission; read:

```promql
sum by (target, reason, boundary) (increase(omi_stt_cost_routing_ignored_deaths_total{job="backend-listen-metrics"}[1h]))
sum by (component, from_mode, to_mode, reason, outcome) (increase(omi_fallback_total{job="backend-listen-metrics",component=~"stt_selection|stt_live_session"}[1h]))
sum by (provider, outcome, phase) (increase(omi_live_stt_terminal_failures_total{job="backend-listen-metrics"}[1h]))
sum(increase(omi_stt_chain_exhausted_total{job="backend-listen-metrics"}[1h])) or vector(0)
```

The ignored counter covers a claimed death excluded by lifecycle, not every
late transport-close symptom. Its labels are registered target (<=16), bounded
reason vocabulary and boundary (`client_gone`/`owner_teardown`), preinitialized.
Require Modulate provider-failure counts to match the managed serving cohort
of selection plus live/terminal fallback emissions per reason before `on`.
The paired counters alone can agree while both classify client churn wrongly.
New `cost-v8`/`fleet-v2` state discards all earlier namespaces' post-client
failures and strikes; it does not migrate or backfill those samples. The
sequential 8% gate and healthy vote budgets stay unchanged; trial vote budgets
are tightened to admitted outcomes only.

Lifecycle accounting (2026-10-18 correction): `opened` counts handed-off
managed legs, `open` counts transports not yet released, and `settled` counts
terminal serving decisions. Transport release and settlement are independent.
A settled-but-open leg contributes -1 to `opened-settled-open`; a released but
unsettled leg contributes +1, and pooling can cancel them. The old absolute-gap
abort is invalid as a serving-loss oracle. Run 5b and routing-on control both
exhibited it; control included discrepancies already present for over eight hours.

Retain the difference per pod/target as an **accounting HOLD/investigation**
signal, recording both arms' carry-in baseline. It must not delete a canary or
roll back the fleet by itself. Retain all real outcome, latency, readiness and
telemetry-coverage safety gates. An unexplained accounting HOLD prevents automatic
qualification and needs an explicit recorded operator decision, not a silent pass.
The fleet rule with stable UID `omi-stt-leg-lifecycle-gap` now checks the valid
exactly-once invariant `settled > opened`, with Grafana `for: 2m`; it no longer
uses transport liveness to infer missing settlements. A separate warning,
`omi-stt-leg-settlement-omission`, catches a positive per-instance/target
`opened-settled-open` above its nonnegative carry-in one hour earlier,
sustained for **15 minutes** of Grafana pending time. Live legs are subtracted;
unchanged positive control carry-in and negative gaps do not trigger it. A
new instance without hour-old samples uses a label-matched zero baseline;
missing current components remain no data and require a coverage HOLD.
The rolling baseline detects new debt and ages it out after an hour; retain
the recorded discrepancy until investigated even after the warning resolves.
This warning requests investigation and HOLD, never a serving abort by itself.

```promql
# Accounting diagnostic only; never a serving abort or missing-settlement proof.
sum by (pod, target) (omi_stt_managed_legs_opened_total{job="backend-listen-metrics"})
- sum by (pod, target) (omi_stt_managed_legs_settled_total{job="backend-listen-metrics"})
- sum by (pod, target) (omi_stt_managed_legs_open{job="backend-listen-metrics"})

# Duplicate-settlement invariant, evaluated per process/target (not fleet pooled).
omi_stt_managed_legs_settled_total{job="backend-listen-metrics"}
- omi_stt_managed_legs_opened_total{job="backend-listen-metrics"} > 0
```

Complete omission detection needs direct low-cardinality released-AND-unsettled
counts and oldest age, with claimed/pending ownership and the enforced
recovery/teardown deadline plus scrape grace. The current counters cannot provide
that state. Do not infer it from a longer gap subquery. A `[1m:15s]` subquery can
contain only four samples spanning 45 seconds. Canary diagnostic timers must use
actual elapsed time with complete scrapes, resetting on gaps, absent targets or
counter resets; baseline old discrepancies separately from new incidents.

Coverage, admitted votes and health evidence:

```promql
sum(increase(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[1h]))
sum by (target) (increase(omi_stt_cost_routing_observations_total{job="backend-listen-metrics",outcome=~"success|provider_failure"}[1h]))
sum by (target, scope, result) (increase(omi_stt_cost_routing_votes_total{job="backend-listen-metrics"}[1h]))
sum by (target) (increase(omi_stt_cost_routing_observations_total{job="backend-listen-metrics",outcome="provider_failure"}[1h])) / clamp_min(sum by (target) (increase(omi_stt_cost_routing_observations_total{job="backend-listen-metrics",outcome=~"success|provider_failure"}[1h])), 1)
sum by (kind) (increase(omi_stt_fleet_health_write_dropped_total{job="backend-listen-metrics"}[1h]))
```

Global stage and snapshot integrity (minimum and maximum must agree; unknown
NaN is never healthy). A language transition can restrict one language without
changing the global gauge; inspect the separate transition scope:

```promql
min by (target) (omi_stt_cost_routing_stage{job="backend-listen-metrics"})
max by (target) (omi_stt_cost_routing_stage{job="backend-listen-metrics"})
min by (target) (omi_stt_cost_routing_state_known{job="backend-listen-metrics"})
max(time() - omi_stt_cost_routing_snapshot_timestamp_seconds{job="backend-listen-metrics"})
count(omi_stt_cost_routing_snapshot_timestamp_seconds{job="backend-listen-metrics"} != omi_stt_cost_routing_snapshot_timestamp_seconds{job="backend-listen-metrics"}) or vector(0)
sum by (target, event, scope) (increase(omi_stt_cost_routing_events_total{job="backend-listen-metrics"}[1h]))
```

Require snapshot age <15 seconds, no NaNs, known=1 for traffic-enabled targets.
A deliberately withdrawn unused target can remain unknown; exclude it explicitly
when evaluating that requirement. Series are preinitialized before traffic so
post-first-scrape transitions and observations are visible to `increase()`.

Would-have-changed-primary breakdown and guard counters:

```promql
sum by (agreement, static_primary, proposed_primary) (increase(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[1h]))
sum by (proposed_primary) (rate(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[1h])) / scalar(sum(rate(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[1h])))
sum(increase(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics",proposed_primary="unavailable"}[1h])) or vector(0)
sum(increase(omi_stt_cost_routing_all_degraded_total{job="backend-listen-metrics"}[1h])) or vector(0)
sum by (reason) (increase(omi_stt_cost_routing_fail_open_total{job="backend-listen-metrics"}[1h]))
sum(increase(omi_stt_cost_routing_no_permitted_target_total{job="backend-listen-metrics"}[1h])) or vector(0)
sum by (target, comparison) (increase(omi_stt_cost_routing_language_state_total{job="backend-listen-metrics"}[1h]))
```

`static_primary` is the configured eligible nomination before local circuit and
connect attempts, not the eventual serving provider. The pair metric runs in
shadow and on; read the actual runtime mode. Positive proposal coverage is
required before interpreting an absent/zero guard series.

User-facing SLIs and silent-provider detection:

```promql
sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome="transcribed"}[15m])) / clamp_min(sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}[15m])), 1)
sum by (provider, language, outcome) (increase(omi_stt_leg_transcript_outcome_total{job="backend-listen-metrics"}[15m]))
histogram_quantile(0.95, sum by (le) (rate(omi_stt_window_first_text_seconds_bucket{job="backend-listen-metrics"}[15m])))
sum(increase(omi_stt_window_admissions_total{job="backend-listen-metrics",outcome="overflow"}[15m])) / clamp_min(sum(increase(omi_stt_window_admissions_total{job="backend-listen-metrics"}[15m])), 1)
histogram_quantile(0.95, sum by (le) (rate(omi_stt_window_post_seconds_bucket{job="backend-listen-metrics"}[15m])))
```

No-text is a mandatory separate SLI, never gate failure evidence. An accepted
non-window provider that returns no words indefinitely has no new automatic
per-session rescue. Continuing speech triggers the diagnostic no-text deadline;
completed sessions feed `omi-live-transcription-success-low` (existing <90%,
>=50 counted sessions/5m, five-minute dwell page). Quiet unfinished streams do
not establish a vendor fault and remain outside this automatic detector.

## Historical router-on ramp and abort

After the checklist passes, configure `on` at **5% for at least 60 minutes and
100 classified canary sessions**, then **25% for at least 60 minutes and 300**,
then **100% with at least two hours of attended observation**. Count actual
router allocation with the new intent-to-treat cohort metric below. The arm is
captured before initialization: an on-arm session that fails open or cannot
connect still counts in the on arm. Custom-STT, BYOK and multi-channel sessions
are excluded. `too_short` remains visible but outside the success denominator.

```promql
sum by (arm) (increase(omi_stt_cost_routing_canary_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}[1h]))
sum by (arm) (increase(omi_stt_cost_routing_canary_outcome_total{job="backend-listen-metrics",outcome="transcribed"}[15m])) / clamp_min(sum by (arm) (increase(omi_stt_cost_routing_canary_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}[15m])), 1)
```

The bounded companion `omi_stt_routing_cohort_outcomes_total` uses labels
`routing_arm`, `signal`, `outcome`. Arms are `on` (sticky selected UID),
`shadow` (static session admitted in shadow mode), and `off` (off mode or an
unassigned UID in on mode). Capture precedes initialization and is pinned
through child tasks, replay, provider switches and flag changes. Terminal
attempt outcomes mirror `omi_live_stt_terminal_total`, including pre-audio
failure; transcript outcomes mirror the headline session counter for this
managed subset. Session-end `fallback_exhausted=yes|no` counts whether the
shared helper emitted any exhausted event for `stt_selection|stt_live_session`;
`terminal_after_text=yes|no` uses the existing recovery-gated predicate.
These booleans count each completed socket once, including too-short sessions.
Existing metrics and serving behavior are unchanged.

`omi_stt_routing_cohort_paid_audio_seconds_total{routing_arm,provider}` emits
accepted paid-adapter PCM seconds at the same session-end seam. Soniox,
Modulate and Deepgram admission includes replay, pre-roll and accepted idle
reopens; rejected sends and idle buffering are excluded until transport
acceptance. This is an admission proxy, not confirmed wire delivery or vendor
billing. All bounded children exist from process start. Compare uniform on/off
configuration, continuous scrapes and matched completion windows; never infer
cohort from pod track or pool shadow with off silently. The static-routing ramp below adds a companion window first-text histogram;
other provider first-text latency remains uninstrumented.

Extend dwell until the on arm reaches the exposure floor; do not substitute
shadow proposals or window-allocation counts for actual router canary sessions.

HOLD for an unexplained lifecycle accounting diagnostic. Abort to shadow/zero for
any emission acknowledgement error or evidence exception; any
unavailable/all-degraded proposal; sustained Redis/write/cap errors; or a
Parakeet/Soniox bench unexplained by actual provider failures. Abort for a >2
percentage-point drop in transcript success from the pre-ramp baseline over
15 minutes with >=100 counted sessions, or <95% absolute; first-text p95 >=30s;
window POST p95 >=2s; or >1% capacity overflow for ten minutes. Compare language
mix and absolute counts; use existing GPU/backfill capacity gates as well.
Apply the transcript abort to the on arm as well as the whole fleet; compare
with the control arm and the pre-ramp baseline. At small sample sizes these are
operational gates, not a statistical proof of non-inferiority.

Kill switch: set `STT_ROUTING_ON_PERCENT=0` or `STT_ROUTING_MODE=shadow` (`off`
also restores static selection; snapshots go neutral and read only family
account benches — a stale selection bench cannot shed the chain, and shared
account quarantine stays enforced in
every mode, so `off` never reopens a credential another pod withdrew). Apply
through the coordinator's config PR and
normal deployment; this is not an instant process-local env mutation.
`PARAKEET_WINDOW_ALLOCATION_PERCENT=0` independently withdraws the window leg.
Keep chart + prod overlay aligned, then regenerate `backend/deploy/runtime_env.yaml`
with `python3 backend/deploy/compose_runtime_env.py`. Do not write routing state
through dev: dev shares production Redis/Firestore.

## Static-routing cohort ramp (stage 1)

This sequence supersedes the historical router-on expansion above. Production
listen stage 1 uses `STT_ROUTING_MODE=on`, `STT_ROUTING_ON_PERCENT=90`: the
complementary approximately 10% of managed accounts use static selection. Keep
`PARAKEET_WINDOW_ALLOCATION_PERCENT=100`, `PARAKEET_WINDOW_MAX_SESSIONS=16`,
`STT_FAILOVER_RECOVERY_ENABLED=true`, and `STT_NO_TEXT_RESCUE_ENABLED=true`.
There is no provider, endpoint, GPU-pool, or admission-limit change. Custom STT,
BYOK, and multi-channel sessions remain outside the managed cohort.

Ship the instrumented binary with `STT_ROUTING_MODE=on` and
`STT_ROUTING_ON_PERCENT=100` first. Let that image serve on/100 for at least
**60 minutes** before the separate stage-1 allocation change. Pin `image_tag`
to that same immutable instrumented image for stage 1 and both arms. A source
rollback or a deployment workflow's overall completion time is not a flag-only
serving boundary. Verify
image convergence, Ready pods, public NEG exposure in every serving zone and
complete scrapes. Hold for an unobserved Ready pod or missing telemetry.

| Stage | `STT_ROUTING_ON_PERCENT` | Approximate static share | Minimum qualified observation |
|---|---:|---:|---|
| 1 | 90 | 10% | 2 hours, 150 classified static outcomes, 50 first-text observations per arm |
| 2 | 75 | 25% | Same floors, measured again at this stage |
| 3 | 50 | 50% | Full 24-hour cycle and the same sample floors |
| 4 | 0 | 100% | 2 hours and the static sample floors; retain the qualified 50/50 control receipt as a historical reference |

At the observed fleet pace, the 10% static cohort may need about 2.5 hours to
reach 150 classified static outcomes. Extend dwell instead of waiving sample
floors.
Stages 1–3 use concurrent on control; stage 4 has no concurrent on cohort, so do
not call its historical reference a concurrent comparison. The release operator
owns each expansion after reviewing its receipt, starting with a review within
24 hours of stage-1 activation. No automatic promotion. Each receipt records
image, actual arm counts, dwell, counts/denominators, zone mix, scrape coverage
and vendor usage. Missing data, stale vendor usage, unexplained accounting
signals or unmet floors are HOLD.

The added histogram is
`omi_stt_routing_cohort_window_first_text_seconds{routing_arm="on|off|shadow"}`.
`off` identifies the static cohort in mode-on; it does not prove global off.
It uses the existing Parakeet-window measurement: first VAD speech through first
emitted nonempty transcript, once per emitting window leg, including recovery
legs. It is not fleet-wide end-to-end first text, and excludes unmanaged sockets.
The arm is pinned when the window socket is constructed, before background
callbacks; later context/flag changes cannot relabel it. Existing global and
demand-cohort histograms keep their schemas and semantics. Only the closed arm
label is added; no account, session, endpoint or language label is introduced.

```promql
# Per-arm window p95 and observation counts; extend the window to stage dwell.
histogram_quantile(0.95, sum by (routing_arm, le) (rate(omi_stt_routing_cohort_window_first_text_seconds_bucket{job="backend-listen-metrics",namespace="prod-omi-backend",listen_track!="canary"}[30m])))
sum by (routing_arm) (increase(omi_stt_routing_cohort_window_first_text_seconds_count{job="backend-listen-metrics",namespace="prod-omi-backend",listen_track!="canary"}[30m]))

# Classified managed outcomes; exclude too_short from the success denominator.
sum by (routing_arm, outcome) (increase(omi_stt_routing_cohort_outcomes_total{job="backend-listen-metrics",namespace="prod-omi-backend",signal="transcript",outcome=~"transcribed|no_transcript"}[30m]))

# Session-end booleans: compare yes / (yes + no), not global accepts.
sum by (routing_arm, signal, outcome) (increase(omi_stt_routing_cohort_outcomes_total{job="backend-listen-metrics",namespace="prod-omi-backend",signal=~"terminal_after_text|fallback_exhausted"}[30m]))
```

Qualification requires static-arm transcript success **at least 95%**, with no
**greater-than-2-percentage-point decline** versus control; apply the retained
15-minute outcome guard at **at least 100 classified outcomes**. Window first-text
p95 must be **below 30s and no more than control +5s**, with the per-arm sample
floors above. Do not compute a passing p95 from absent or undersampled series.
Investigate any terminal-after-text or exhaustion excess immediately; a sustained
excess versus concurrent on control aborts the expansion. Keep booleans/counts
separate from attempt outcomes and account for completion lag.

Retain window POST p95 below 2s and the existing overflow guard (>1% sustained
10 minutes). No new GPU queue timeouts, sustained live queue p95 at least 1s,
admission-overflow rise, or restart/readiness regression may pass. Retain the
existing real outcome and lifecycle guards; accounting gaps are investigation
HOLDs, not automatic serving rollback. Watch the whole fleet and each serving
zone as well as the two arms. LB 101 share has a broad 403/429-inclusive request
denominator and is supporting evidence, not an exact session-open success SLI.

Rollback for this **static expansion** is `STT_ROUTING_MODE=on` and
`STT_ROUTING_ON_PERCENT=100`, with the same image, through the normal listen
configuration workflow. Keep chart, prod overlay and generated runtime manifest
aligned. This direction differs from aborting the historical router-on ramp.
Do not set global mode off for a partial ramp: it ignores the on percentage and
also suppresses shared health evidence. Keeping mode on preserves health
collection even in the complementary static cohort; a later global evidence-off
change needs its own evidence.

No additional capacity is requested. Planning incremental vendor cost at 5% is
about **$0.5–1/day** at the investigated volume, not a contracted bill. Measure
fresh vendor usage, include Modulate and Soniox, and separate replay-inclusive
paid-audio proxies from vendor invoices before expanding.

## Historical production routing-off rollout (2026-10-18)

The historical trial used `STT_ROUTING_MODE=off` (reverted by #22222);
the current static expansion is defined above. Off was the independent canary's only
routing override. Dev keeps its existing configuration. Static provider order,
recovery, capacity rescue, account quarantine and the routing kill switch stay
available; off does not disable fallback. No account cohort is added by this
rollout. Manage private cohorts outside this repository.

Rollback: **set `STT_ROUTING_MODE=on` in the prod listen values and prod runtime
overlay, run `python3 backend/deploy/compose_runtime_env.py`, then deploy through
the normal prod listen Helm workflow with the same image.** This rolls/drains
WebSockets. Do not roll back an entire old Helm revision and undo unrelated
capacity fixes. The routing-only config commit can also be reverted and deployed.

Before deployment, pin the serving image/release SHA, exact main pod set and a
30-minute pre-deploy baseline. After rollout, verify the reported release identity,
`STT_ROUTING_MODE=off` on every main pod, Ready pods, public NEG membership and
complete scrapes. Compare matched 15- and 30-minute windows with the baseline;
record numerators, denominators, language/provider mix and histogram counts:

| Watch | Baseline and post-deploy measure |
|---|---|
| Exhausted chains | `sum(increase(omi_stt_chain_exhausted_total[15m])) / sum(increase(omi_listen_accepted_total[15m]))` (repeat with `[30m]`) |
| Terminal after text | `increase(omi_live_session_terminal_after_text_total)` / accepted sessions |
| Transcript success | transcribed / (transcribed + no_transcript) from `omi_live_session_transcript_outcome_total`; exclude too_short |
| First-text p95 | `histogram_quantile(0.95, sum by(le)(rate(omi_stt_window_first_text_seconds_bucket[15m])))` plus its count |

Use `job="backend-listen-metrics"`, the prod namespace and exact escaped pod
sets for all watches, as in `listen-stt-canary-queries.promql`. First-text timing
covers Parakeet-window only; it does not measure Modulate/Soniox end-to-end
latency. Missing metrics are HOLD, never zero. Outcome completion lags accepts;
exhaustion and terminal events are not deduplicated session failure rates.
Watch through at least 60 minutes and 150 classified post-rollout outcomes.
Investigate any outcome-rate regression against the baseline immediately; use
the retained sampled latency and outcome safety gates, and routing-on rollback
for a sustained serving regression. Earlier single-run aborts remain historical;
the lead accepted pooled same-image/config runs 4b+5b (173 classified outcomes).

## Operator reset

After repairing a credential or provider outage, inspect the local and
fleet circuit metrics. Run `python3 backend/scripts/stt/reset_fleet_provider.py
soniox` in the intended environment for a dry run. An approved operator may
repeat with `--execute` to delete only that named provider's recent fleet
score, account/selection bench and recovery probe keys. This legacy reset
does not clear the new cost-gate namespace; let its staged recovery proceed
after repairing the provider. The script refuses
more than 1,000 matching keys and uses short Redis socket deadlines. It does
not reset process-local circuits; those recover on their existing cooldown,
or after an operator controlled listen restart. Never point the script at a
different environment to clear a production alert.


## Router-on readiness controls (default off)

`STT_PAID_SPILLOVER_BUDGET_ENABLED=false` preserves existing selection. When
true, router-on sessions encountering Parakeet capacity refusal must obtain a
fleet admission before promoting a paid route. Redis TIME and one atomic Lua
operation enforce a fixed UTC-minute budget across pods; all endpoints and credentials for
the same provider share the budget; rotations do not reset it. Defaults are 30 promotions each
for `STT_PAID_SPILLOVER_SONIOX_PER_MINUTE`,
`STT_PAID_SPILLOVER_MODULATE_PER_MINUTE`, and
`STT_PAID_SPILLOVER_DEEPGRAM_PER_MINUTE` (range 0–10000). Zero refuses
promotions. Malformed or out-of-range caps deny promotions before Redis access,
log once per provider per process without the raw value, and report `unavailable`.
Redis faults or budget denial restore the configured order and
emit `omi_stt_paid_spillover_admissions_total{provider,outcome}` with outcomes
`admitted`, `denied`, `unavailable`. This limits additional router promotions;
the static chain may still require a paid dial. A minute boundary can admit
two adjacent budgets in a short interval. Qualify paid concurrency, retry and
billing headroom independently before enabling router traffic.

`STT_NO_TEXT_RESCUE_ENABLED=false` preserves existing first-text handling.
Enabling it also requires `STT_FAILOVER_RECOVERY_ENABLED=true`; the choice and
`STT_NO_TEXT_RESCUE_SECONDS` are pinned when the managed session is created.
The default 60-second lease (range 5–120) bounds paid audio admission by wall time and paid
admitted audio, including replay and successor switches, for one ambiguous
no-text interval per listen session. Capture-mapped successor text overlapping the stalled interval records
evidence but does not renew the lease. Later or unmapped text is unproven. At expiry or audio-budget refusal, audio admission stops and the owner tries
windowed Parakeet once, retaining unanswered capture and applying the normal
replay/epoch fences. Transport cleanup uses the ordinary bounded abort; the admission deadline is
not an exact provider billing or socket-close timestamp. This policy retirement
never benches the paid provider.
If cheap permission/capacity is unavailable, recovery terminates explicitly;
it cannot quietly extend the paid lease. Returned cheap decoding suppresses
further first-text/empty-streak rescues for the session. Normal transport
failures still use the configured recovery path. Empty output does not establish
that audio is noise. Before a lease is spent, the gated window deadline rearms
after emitted text so later speech without progress can also trigger rescue.

`omi_stt_no_text_rescue_audio_seconds_total{provider}` measures admitted paid
rescue audio; `omi_stt_no_text_rescue_total{outcome}` counts starts and completed
intervals, distinguishing `interval_text` from `unproven`. Overlap is evidence of some
original-interval text, not a completeness or correctness claim. Starts from sessions
that leave before lease completion remain censored; these metrics are not an
invoice or a transcript-quality score. For a synthetic one-hour Soniox
remainder, the declared $0.0754/audio-hour rate implies $0.0754 without a
lease versus at most $0.001257 for 60 paid audio seconds, followed by cheap
processing. Billing increments and costs of genuine later transport failures
are separate. Existing production counters do not join deadline causes to
successor duration; do not claim historical savings from them.

The monitoring chart's `alerts/live-stt.json` and combined `alert-rules.json`
contain independent terminal-after-text, mid-session terminal, paid-capacity,
combined overflow/batch-pressure, POST-latency, replay-continuity, lifecycle,
persistence, snapshot and stage-readiness rules. Any-text headline success
remains its existing limited SLI. Deploy and test notification delivery through
the monitoring release process before rollout; committing rules does not make
them live. The live-STT import allowlist and coverage gate include these rules;
the monitoring import must precede verification of their live coverage. Lifecycle/replay rules document their configured-chain/recovery
prerequisites. The #20391 terminal-after-text emitter also requires the pinned
recovery flag. Production recovery is now enabled across all listen traffic, so its
dedicated alert scopes the volume floor, numerator and denominator to every
`backend-listen-metrics` series, including stable and former-canary series. Both
cohorts contribute to the 20-session floor and the terminal-after-text ratio. The
independent mid-session terminal rule covers every path. Never pool lifecycle
counters across instances or targets.

Local limiter qualification (disposable Redis, no cloud data):

```bash
printf '%s\n' tests/integration/test_paid_spillover_redis.py > .local/redis-tests.txt
OMI_OWNED_PID_FILE="$PWD/.local/owned-pids.txt" \
BACKEND_PYTEST_MARK_EXPR=integration \
BACKEND_UNIT_TEST_FILE_LIST="$PWD/.local/redis-tests.txt" bash backend/test.sh
```

Run from the repository root with `.local/` already created. The integration
test records its Redis PID and terminates only that owned process. Fast router
and receiver regressions remain in the normal hermetic unit suite.
