# Live STT routing and Soniox runway

## Controls and rollout

`STT_ROUTING_MODE=off` keeps configured order. `shadow` computes cost-order
selection and bounded primary agreement without changing connections. `on`
applies it to `STT_ROUTING_ON_PERCENT` of UIDs, default zero. Production stays
shadow/zero on merge. Roll out on at 5 → 25 → 100%, using the headline transcript
SLI and first-text latency. Return to shadow/off or on-percent zero to restore
static selection. Keep Parakeet's independent allocation at its approved value.

The [cost router design](../../utils/stt/ARCHITECTURE.md#cost-ordered-health-gated-live-routing)
owns the registry schema, second-Modulate example, sequential statistical gate,
shared 5%/25%/100% recovery stages, false-positive/detection measurements and
limits. `STT_ROUTING_TARGETS_JSON` is the complete target registry override;
`STT_ROUTING_DISRUPTION_GATE` defaults to 0.08. The old
`STT_ROUTING_PROBE_PERCENT` control is retired. Expensive providers do not
receive artificial probe traffic. New endpoints reuse an existing provider
protocol; a genuinely new protocol first needs an adapter.

The connection path reads cached memory. Redis state is refreshed off connect
with a 75 ms deadline and eight bounded result-write slots. Redis faults retain
known benches and use local evidence; pods do not independently reopen cost
gate trials. Completed text counts at close and attributable provider deaths as soon as
known. Plain no-text/deadline-only outcomes are censored and cannot advance
health or recovery. Connect failures have their own classified target outcome. First-text `text`/`no_text` metrics remain diagnostic and are
not double-counted into the cost health test. The static-path legacy score and
account state remains available for local resilience; it does not rank the
active policy. Fleet deadlines use Redis server time; opposite +/-60-second
pod skews cannot start recovery early. During a Redis outage local evidence
keeps routing usable, and pending local benches reconcile before re-entry.

Window candidates must match the session's actual engine choice, language
eligibility and hosted endpoint. Mismatches and empty proposals restore the
configured chain and increment `omi_stt_cost_routing_fail_open_total`.
Configured unregistered services remain at the tail, followed by health-skipped
trial/bench targets as last resorts. Health stages cannot empty an eligible
chain: all-degraded candidates are ordered by stage, observed error rate, then
cost. The terminal target has no health/trial share limit unless a cheaper
fully healthy candidate can serve this UID. Explicit ramp, engine/capability
and account exclusions remain hard. Read the all-degraded counter before on. Capacity signals and five-second local capacity
cooldowns exclude terminal legs and configured-default aliases when an
alternative remains. If all remaining candidates are capacity-blocked, dial
one least-recently-refused candidate through its normal account/circuit and
admission gates, at most once per session. This serves a sole candidate that
recovers inside its cooldown; it intentionally removes the process-wide
five-second dial bound in that case. A
`capacity_full` refusal releases the circuit probe and starts that target
cooldown without recording a circuit/health failure. Empty-proposal
last-resort forcing respects it; the one-attempt escape above is the only
capacity exception in the on cohort. Ordinary mid-session deaths exclude only the target;
quota/auth failures exclude its whole family.

The gate is an 8% Page CUSUM on **provider availability errors**, not an
anytime-valid probability test or a no-text quality gate. Errors are typed
serve/death/connect failures (`modulate_serve_error`, `connection_lost`,
`send_failed`, `provider_5xx`, `provider_429`, `provider_rate_limited`, `timeout`).
Completed text is passing evidence; plain no-text, first-text deadline/empty
streak, client/VAD, account/config/capacity and idle/rotation are censored.
Legacy transcript and deadline SLIs remain essential: this loses automatic
health-gate detection of a recognizer that connects but silently emits no words.
No successor/content join is performed. Shadow serving and diagnostics remain
unchanged; active routing no longer opens a local serve breaker for plain
no-text. Account and genuine provider breakers retain their fast protection.

At 5%/7%/10% no-text with zero provider errors, replays observe zero false
benches per 400k sessions at each floor. Conditional on that classification,
the probability is zero: no-text cannot raise a score. With a 10% censored
noise floor, 200 seeded runs detect 100% errors in 8/8 median/p95 sessions,
60% errors in 13/19 sessions (8/9 failures), and a 40% Modulate brownout in
22/47 sessions (9/15 failures). Wall time depends on observed classified
traffic and completion/cache delay. Sparse language breadth protection remains.

Promotion needs 30/60 **classified** trial outcomes and a passing user-vote
fraction; each user gets one majority-outcome vote and only the first three
outcomes contribute sequential evidence. Broad trial failures reject; held
windows reset at 120/240. Two always-failing users and 23 always-passing users
observed in each window (>=92% healthy observed users) promote within 360
classified outcomes. Censored noise does not advance this bound; healthy
users absent from the sticky cohort cannot establish recovery.

The v6 namespace starts fresh serving-only provider-error evidence. Do not
reinterpret v3/v4 misclassified history or v5 evidence polluted by deaths first
observed after client departure. Warm v6 shadow data before raising on-percent.

At 17.9k eligible sessions/day and 61% Modulate disruption, the delayed-result
trial replay averages 75.46 disruptions/day (p95 80; worst seeded run 83),
versus 545.95/day for an uninterrupted 5% trial. The deterministic replay bound
is below 100/day, including ten initial outage failures. This is conditional
on the documented workload/delay assumptions, not a hard production traffic
budget. Watch actual failovers and dropped writes before increasing the ramp.

## Read during rollout

Use the backend-listen Grafana dashboard and these PromQL queries:

```promql
sum by (provider, language, outcome) (rate(omi_stt_leg_transcript_outcome_total{job="backend-listen-metrics"}[15m]))
sum by (provider, outcome) (rate(omi_stt_provider_connect_total{job="backend-listen-metrics"}[15m]))
max by (provider, kind) (omi_stt_provider_circuit_open{job="backend-listen-metrics"})
histogram_quantile(0.95, sum by (le) (rate(omi_stt_routing_decision_seconds_bucket{job="backend-listen-metrics"}[10m])))
sum by (kind) (rate(omi_stt_fleet_health_write_dropped_total{job="backend-listen-metrics"}[5m]))
sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome="transcribed"}[5m])) / clamp_min(sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",outcome=~"transcribed|no_transcript"}[5m])), 1)
```

Cost state uses `omi:live-stt:cost-v6:<target>:<bounded-language>` (and `all`)
with atomic compare-and-set updates and trial-start leases. A full result-write
pool, deadline or CAS contention can drop a fleet sample and increments
`omi_stt_fleet_health_write_dropped_total`; local evidence still advances.
Monitor dropped writes before increasing traffic. New dashboard panels should
show `omi_stt_cost_routing_decisions_total`, `omi_stt_cost_routing_shadow_total`,
`omi_stt_cost_routing_benched`, `omi_stt_cost_routing_stage`, and
`omi_stt_cost_routing_events_total`, and `omi_stt_cost_routing_fail_open_total`.
Transition logs include counts, failure rate and CUSUM score.
The bench/stage gauges are **pod views of global target state**, including
local fallback during Redis faults. Every refresh observes all registry global
keys and republishes, even on idle/ineligible pods; unknown is NaN with
`omi_stt_cost_routing_state_known=0`. The snapshot timestamp is Redis server
time; NaN means never refreshed, whereas a finite old timestamp is stale.
The background loop refreshes registry targets even without session traffic.
Require fresh, known, converged views before interpreting min/max.
Counters record CAS transitions once at the writer with `scope=global|language`;
local Redis-down transitions remain logs. Target/event/scope series are
initialised at zero before traffic so first post-scrape transitions are counted.
Increments before a pod's first scrape cannot be recovered by `increase()`.
Transition rates are classified outcomes; promotion uses user votes.
Shadow labels remain at most 16 registry IDs plus fixed sentinels; no UID or
content. Drain old pods before using the v6 serving-boundary observation queries.

The `omi-modulate-failing-soniox` Telegram rule names the active spend lever.
The existing `Omi - Services Alerting (Telegram)` Grafana contact point must
reach David. The coordinator must verify this contact point and the live rule
evaluation after deployment; committed JSON alone is not delivery evidence.

## Exact router rollout queries

Global-state pod stage (0 benched, 5/25 trial, 100 available), filtering to
recent snapshots. Unknown NaN is not evidence of health:

```promql
min by (target) (omi_stt_cost_routing_stage{job="backend-listen-metrics"} and on (job, instance) (time() - omi_stt_cost_routing_snapshot_timestamp_seconds{job="backend-listen-metrics"} < 15))
max by (target) (omi_stt_cost_routing_stage{job="backend-listen-metrics"} and on (job, instance) (time() - omi_stt_cost_routing_snapshot_timestamp_seconds{job="backend-listen-metrics"} < 15))
min by (target) (omi_stt_cost_routing_state_known{job="backend-listen-metrics"})
max(time() - omi_stt_cost_routing_snapshot_timestamp_seconds{job="backend-listen-metrics"})
```

Global and language transitions over the last hour, with separate scopes:

```promql
sum by (target, event, scope) (increase(omi_stt_cost_routing_events_total{job="backend-listen-metrics",event=~"bench|unbench|stage"}[1h]))
```

Static/proposed primary shares and pair agreement:

```promql
sum by (static_primary) (rate(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[1h])) / scalar(sum(rate(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[1h])))
sum by (proposed_primary) (rate(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[1h])) / scalar(sum(rate(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[1h])))
sum by (agreement, static_primary, proposed_primary) (rate(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[15m]))
```

Audio-independent provider-error fraction, plus censored observations:

```promql
sum by (target) (rate(omi_stt_cost_routing_observations_total{job="backend-listen-metrics",outcome="provider_failure"}[1h])) / clamp_min(sum by (target) (rate(omi_stt_cost_routing_observations_total{job="backend-listen-metrics",outcome=~"success|provider_failure"}[1h])), 1e-9)
sum by (target, outcome) (increase(omi_stt_cost_routing_observations_total{job="backend-listen-metrics"}[1h]))
```

Reconcile classifications with settled source-leg failovers over the same window:

```promql
sum by (target, outcome, reason) (increase(omi_stt_cost_routing_observations_total{job="backend-listen-metrics"}[1h]))
sum by (from_mode, reason, outcome) (increase(omi_fallback_total{job="backend-listen-metrics",component="stt_live_session"}[1h]))
count(omi_stt_cost_routing_snapshot_timestamp_seconds{job="backend-listen-metrics"} != omi_stt_cost_routing_snapshot_timestamp_seconds{job="backend-listen-metrics"}) or vector(0)
```

**Before enabling `on`, require Modulate's provider-error counts to reconcile
across selection and live-session hops, by the socket's own reason.**
`modulate-velma-2` maps to fallback `from_mode="modulate"`; `parakeet-window`
maps to `parakeet`. Family fallback labels combine sibling endpoints; sum their
health counts if more than one endpoint is configured.

One accepted physical socket/managed leg has one observation slot, regardless
of repeated frames, send/death/finish observers, or connect-validation writes.
A new replay/reconnect socket is a distinct leg and can contribute a new death.
Provider availability needs no speech/audio minimum; completed text counts
without VAD. Only plain no-text requires one second of VAD speech and is censored.
A shared receipt prevents repeated local/Redis samples, including generation
changes and trial promotion; fresh connect evidence still obeys trial admission.

A death first observed with an active, connected client is evidence. A death
first observed after explicit client/application disconnect, inactive/shutdown
state or owner teardown is excluded, even if the raw socket already died before
cleanup began. The teardown poll checks client state before recording; an
already-dead socket with a still-connected client is valid pre-fence evidence.
The owner fence excludes later close-induced deaths. Evidence already observed
while connected is retained; the backend cannot reconstruct
whether an unobserved raw death preceded client departure. A censored receipt
also prevents connect validation from resurrecting that excluded evidence.
Text already produced by the leg still contributes one successful observation,
even when its later death is ignored; the valid denominator is retained.

For a fixed cohort of accepted sockets, after all hops settle, per reason:

`provider_failure = settled stt_selection hops + settled stt_live_session hops + connected-client deaths with no successor`.

Connect-time accepted serve errors now keep `modulate_serve_error` in selection
fallback telemetry, instead of generic `provider_5xx`. A rejected successor
settles the source's reason, never the successor's reason. Selection hops whose
source was already client/owner-censored are excluded too. Errors before any
managed socket exists are additional connect-attempt observations; compare
those against selection telemetry separately. Circuit/config/capability skips
have no accepted socket death and must not be included in that cohort. Settlement
and first-scrape boundaries can shift aggregate time buckets. Family labels also
include legacy/PTT paths, so compare the same managed serving scope.

A connected-client terminal Soniox death emits `stt_failed`/1011 and increments
`omi_live_stt_terminal_failures_total`. `omi_stt_chain_exhausted_total` counts
connect-chain construction exhaustion; it does not count a receiver that has no
replacement after an already-serving leg dies. Zero connect exhaustion therefore
does not rule out terminal deaths. The existing Soniox reconnect predicate
requires a raw `ws ` diagnostic prefix: a managed leg's bounded transport cause
does not pass that predicate and takes ordinary failover/terminal handling.
That serving behavior is unchanged here. Raw eligible reconnect paths use
`omi_stt_reconnect_total`; a settled same-family hop is `soniox` → `soniox`.
Finished/idle/rotation remain non-failures.

Read all these surfaces together (labels are bounded, with no socket/UID ids):

```promql
sum by (target, outcome, reason) (increase(omi_stt_cost_routing_observations_total{job="backend-listen-metrics"}[1h]))
sum by (component, from_mode, reason, outcome) (increase(omi_fallback_total{job="backend-listen-metrics",component=~"stt_selection|stt_live_session"}[1h]))
sum by (target, reason, boundary) (increase(omi_stt_cost_routing_ignored_deaths_total{job="backend-listen-metrics"}[1h]))
sum by (provider, outcome, phase) (increase(omi_live_stt_terminal_failures_total{job="backend-listen-metrics"}[1h]))
sum by (provider, reason, outcome) (increase(omi_stt_reconnect_total{job="backend-listen-metrics"}[1h]))
sum(increase(omi_stt_chain_exhausted_total{job="backend-listen-metrics"}[1h])) or vector(0)
```

The ignored-death counter exposes the excluded source reason and boundary
(`client_gone` or `owner_teardown`), once per leg. It has <=16 registered targets,
28 bounded reasons and two boundaries, preinitialized for first-increment
visibility. It never feeds health. Terminal metrics are session-level and lack
reason/target labels, so these aggregate queries diagnose differences rather
than providing an exact per-socket join. Do not infer how historical excess
observations split across paths from a partial aggregate table.

Use `omi:live-stt:cost-v6`: v5 contains invalid post-client/owner failure evidence,
so retaining its samples or backoff strikes would carry the biased history into
the new gate. Stored shape, thresholds, vocabulary, registry and serving policy
are unchanged. No history is migrated, reinterpreted or backfilled.

A socket-owned typed cause precedes a bounded raw cause, then the observing
send/monitor symptom. Unknown/free-text serving deaths become `connection_lost`,
or `send_failed` when observed directly on send; free text is never a label.
Window `first_text_deadline`, `empty_streak`, `capacity_full`, account refusals,
rotation/idle timeout and explicit client/VAD causes keep their own censored
reason. Normal completion uses `text` or `no_text`. Failed hops retain the source
cause instead of relabelling that source with the successor's rejection.
Budget/auth cost reasons are `provider_budget_exhausted`/`provider_auth_rejected`;
fallback metrics retain their established `quota`/`auth` aliases. Serving account
protection is unchanged. The closed vocabulary has 28 reasons, with up to 16
registry targets and three outcomes. No UID or diagnostic text is exported.

Unavailable proposals, degraded-only selection, dropped samples and errors:

```promql
sum(increase(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics",proposed_primary="unavailable"}[8h])) or vector(0)
sum by (target) (increase(omi_stt_cost_routing_all_degraded_total{job="backend-listen-metrics"}[8h])) or vector(0)
sum by (reason) (increase(omi_stt_cost_routing_fail_open_total{job="backend-listen-metrics"}[8h]))
sum by (kind) (increase(omi_stt_fleet_health_write_dropped_total{job="backend-listen-metrics"}[8h]))
sum(increase(omi_stt_cost_routing_shadow_total{job="backend-listen-metrics"}[8h]))
```

A zero unavailable delta needs positive traffic coverage and no proposal errors;
check absolute counters/logs too during pod startup because first increments
before the first scrape can be invisible. These comparisons run in shadow and
on; verify runtime mode before calling them shadow qualification.

## Shadow go/no-go before on

Keep `shadow`/on-percent `0` for at least a full 24h traffic/language cycle after
the v6 rollout. Do not increase the router percentage until all checks pass:

- Positive observation/proposal coverage for all configured targets; snapshot
  age <15s, known state, and converged pod min/max. No sustained write drops,
  Redis/cache errors, or unexplained language-specific bench transitions.
- **Zero unavailable proposals and zero all-degraded selections.** A capable,
  ramp-admitted, account-available target must keep a chain. Missing/withdrawn
  targets, account denial or malformed config must be understood first.
- **Soniox and Parakeet at global 100**, without noise-driven language benches;
  **Modulate benched or in bounded 5% re-entry**, never promoted on this error
  rate. Its stage may legitimately cycle 0/5 as backoff runs.
- Proposed Parakeet share matches the configured
  `PARAKEET_WINDOW_ALLOCATION_PERCENT` sticky cohort, without a health-driven
  reduction to 5%; no proposals divert a capable, admitted
  healthy Parakeet session to a more expensive target. Compare target shares
  and pair disagreement with static selection, accounting for language,
  actual window/RNNT engine eligibility, cohort repetition and capacity.
- **Reason reconciliation passes:** Modulate provider failures track settled
  provider-error selection/live hops plus connected terminal deaths, not censored
  outcomes. Explain ignored deaths and reconnect/terminal metrics; zero connect
  exhaustion alone is insufficient. Window deadline/empty/capacity
  failovers appear only as censored health observations; rotation/account/client
  reasons do too. No pod has a never-refreshed snapshot after startup warmup.
- Provider-error fractions for healthy targets stay around the observed
  0.3–1%, and no-text floors no longer affect benches. Headline conversation
  transcript success and first-text latency do not regress. Deadline/empty
  failures rescued by another provider deserve investigation even though
  they are censored by this gate.

The local aggregate replay is diagnostic evidence: it keeps Soniox/Parakeet at
100, Modulate in 0/5, and proposals nonempty. It cannot reconstruct real UID,
cohort, language-failure or successor joins. After passing the checklist, the
coordinator can ramp on 5 → 25 → 100 with a dwell at each step and the same
checks; shadow/off or on-percent zero is the kill switch. This PR does not
perform that rollout.

## Soniox runway

`SONIOX_MONTHLY_CEILING_USD` sets the monthly alert ceiling; zero disables
the poller. The production value is configured in the listen chart and
runtime env. No automatic top-up or hard paid-traffic cutoff occurs. The
hourly poller prefers Soniox's current-month `/v1/usage/summary` dollar cost.
The existing backend-listen `SONIOX_API_KEY` needs the Soniox **Usage and
limits** permission for this read. If the API read fails, the poller estimates
from Omi-metered Soniox audio seconds times
`SONIOX_ESTIMATED_USD_PER_HOUR`; that estimate can undercount if Redis was
unavailable or if Soniox charges for audio outside this listen path. Check
`omi_soniox_usage_source{source="vendor"}` and the sample timestamp before
acting on the amount. The 70% and 90% Telegram alerts explicitly say **top
up Soniox**. Compare the configured ceiling with the real Soniox account
balance during an incident; the ceiling itself does not fund the account.

```promql
max(omi_soniox_month_spend_usd{job="backend-listen-metrics"}) / clamp_min(max(omi_soniox_month_ceiling_usd{job="backend-listen-metrics"}), 1)
max(omi_soniox_usage_source{job="backend-listen-metrics"}) by (source)
time() - max(omi_soniox_usage_sample_timestamp_seconds{job="backend-listen-metrics"})
```

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
