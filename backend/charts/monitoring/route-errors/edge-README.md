# Held same-LB-log storm partition

These four new project-level log counters and the held plan prepare a future
Grafana-only routing change. They do not change, mute or inhibit either existing
warning. No active Grafana rule, Monitoring policy, GCP call, auth dependency or
apply mode is included. Run the offline checker from the repository root:

```bash
python3 backend/scripts/check_edge_storm_preparation.py
```

Each pair partitions **the same emitted LB request-log stream**, rather than
subtracting a Cloud Run poll counter from an LB or Armor counter:

| Family | Base | Storm | Nonstorm |
| --- | --- | --- | --- |
| `4xx` | Status 400–499 | Base AND exact storm predicate | Base AND NOT (exact storm predicate) |
| `armor_deny` | Enforced backend/edge policy DENY, or documented denial status detail | Base AND exact storm predicate | Base AND NOT (exact storm predicate) |

For each family, the sets are disjoint and their union equals the base. Armor
DENY 429 is also a 4xx event: the two families overlap and must never be added to
one another. All metrics have **zero custom labels/extractors**. The monitored
resource supplies infrastructure labels such as `backend_service_name`; route
identity is encoded in the metric definition, never a raw path/ID label.

The exact storm predicate is GET, status **429 only**, and HTTPS host
`api.omi.me` with path `/v2/sync-local-files/<canonical-lowercase-UUID>` (an optional
query string is allowed but never extracted). The fixed displayed route is
`/v2/sync-local-files/{job_id}`. `sync.py` and `database/sync_jobs.py` create UUID
job IDs; the status route is defined in `routers/sync.py`. Unknown/legacy IDs,
encoded paths, wrong hosts, HTTP URLs, extra segments, fragments, other methods
and other statuses conservatively remain nonstorm. No 403 assumption is made.
This classifies a request cohort, not proof that its caller is benign or that
all matching requests belong to the historical client bug.

`NOT` wraps the **whole exact predicate**. Do not replace it with separate `!=`
or negative-regex field comparisons: missing method/URL fields must remain in
the nonstorm set. A missing status cannot qualify as a known 4xx, so it is
outside that base; an Armor denial with missing status is still in the Armor
nonstorm set. Missing required request metadata also needs a telemetry-integrity
check before cutover. Preview-only policy decisions are not enforced denials.

## Source and field evidence

The definitions pin `resource.type="http_load_balancer"`, project
`based-hardware`, and `logName="projects/based-hardware/logs/requests"`.
Google's [LB logging documentation](https://docs.cloud.google.com/load-balancing/docs/https/https-logging-monitoring)
defines this resource and backend-service labels; its
[troubleshooting query](https://docs.cloud.google.com/load-balancing/docs/https/troubleshooting-ext-https-lbs)
pins the `requests` log name. [Cloud Armor request logging](https://docs.cloud.google.com/armor/docs/request-logging)
documents backend/edge `outcome="DENY"` and denial status details. The union
covers both explicit DENY shapes and the two documented denial fallbacks;
it deliberately does not use `configuredAction="DENY"`, since THROTTLE can
produce an enforced DENY too. No live payload inspection was performed here.

Existing evidence in `obs-investigations/errors/report.md` describes the
10–12k/min denial storm and missing route attribution. The checked-in
`cloud-armor-denied-requests.json` dashboard uses the LB enforced-policy DENY
shape; `memories-fetch-resilience.md` independently records throttle DENY 429s.
These establish a plausible source shape, not live equivalence of these new
filters to the existing global metric.

Generation sampling and storage exclusions are separate. Google documents that
[Armor logs inherit LB generation sampling](https://docs.cloud.google.com/armor/docs/request-logging).
[Project-level user metrics count received entries despite sink exclusions](https://docs.cloud.google.com/logging/docs/logs-based-metrics),
so a 10% `_Default` retention exclusion does not imply these counters are 10%
sampled. Actual backend `logConfig.sampleRate` still limits emitted events.
Read-only evidence previously described 10% LB sampling; source configuration
must be refreshed per backend. Do not multiply by ten or carry the old 20/s,
12k/min or proposed 15k/min values into these counters without a same-population
calibration receipt. No backfill occurs for logs received before metric creation.

## Held routing and escalation contract

`edge-storm-plan.json` leaves every numeric threshold and backend selector null.
The two existing warnings remain unchanged until a separate reviewed cutover:

1. Map the backend warning's current Cloud Run service scope to its exact LB
   backend resources. Cloud Run status counts and LB status counts have different
   coverage; this is a semantic migration requiring evidence, not a subtraction.
2. Replay the corresponding LB nonstorm warning with a newly calibrated
   threshold. Reconcile the existing Armor filter against the new DENY union.
   Keep unknown routes/methods and unrelated 401/403/409 requests pageable.
3. Add a dedicated fixed-route storm signal from the storm counters. Any future
   warning suppression/routing may affect **only that exact storm instance**;
   neither nonstorm/security nor escalation nor service/desktop 5xx/long-504
   alerts may depend on a storm-wide inhibitor. No such routing is activated here.
4. Keep an uninhibited escalation above the **same-stream observed storm ceiling**.
   The positive calibrated storm floor must be <= the observed ceiling, and
   escalation must be strictly above both. The old observed ceiling is historical
   context; the old metric's units/sampling cannot be assumed interchangeable.
5. Verify canaries, fixed-window counts, source health, and independently received
   Grafana notification/resolve receipts, including an unrelated attack/failure
   while the storm instance is present. Retain existing warnings through acceptance.

An optional local receipt check uses `--receipt <file>`; it never grants admission
or applies anything. The receipt must match the exact metric/filter fingerprint,
LB stream, project-level scope, enabled backend source inventory/sample rates,
sampling fingerprint, reviewed floor/ceiling/escalation, and a fixed >=24h aware
UTC window. Coverage and partition identities must be explicitly verified from
the new metric population, not Cloud Run counts or stored sampled log searches.
The checker can validate a receipt's structure/consistency; a human reviewer must
establish the truth and completeness of its evidence. Empty counters remain
unknown without independently proven ingestion/source health.

The threshold values used in unit fixtures are synthetic validation cases.
Committed production thresholds remain null and the plan always stays held.
Tests exercise Boolean partition algebra and adversarial request shapes; they
are not proof that Google's filter engine accepted the definitions or that
production ingestion, query semantics or notification delivery work.

Parent creation/verification instructions are appended to `.agent-notes/route-errors.md`.
Do not change sink exclusions, LB sampling, IAM, retention or BigQuery as part of
this preparation. Rollback a future routing batch by restoring its saved Grafana
objects and retaining the original global warnings; preserve metric history.
