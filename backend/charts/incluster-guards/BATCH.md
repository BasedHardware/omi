# Batch admission rollback

With `batch.enabled: true`, production values install a separate five-minute
CronJob, `prod-omi-incluster-guards-batch`, using a dedicated KSA with
annotation
`iam.gke.io/gcp-service-account: omi-batch-rollback-guard@based-hardware.iam.gserviceaccount.com`.
Production currently keeps `batch.enabled: false` until the deployer RBAC for
the `-batch` objects is approved (access change, David) and g2's producer
exists. Development never installs this writer. `batch.cloudRunRollbackEnabled=false`
removes the batch resources including its state ConfigMap; save state/audit
evidence before removing them. `dryRun=true` retains state but suppresses all Cloud Run writes,
including a previously pending rollback. Check active Jobs when stopping: new
values do not change a running Job. A batch Job has an 840s deadline and no
automatic Kubernetes retry; its durable intent allows the next scheduled Job
to resume a partial rollback. Keep its state ConfigMap across operator recovery.

## Permissions and scope

David approved `roles/run.developer` on **only** `backend`, `backend-sync`,
`backend-sync-backfill`, `backend-integration` in `based-hardware/us-central1`.
The lead creates the GSA, binds that role to each service, binds
`roles/iam.workloadIdentityUser` on the GSA for exactly
`based-hardware.svc.id.goog[prod-omi-backend/prod-omi-incluster-guards-batch]`,
and grants runtime-SA actAs only if required. No project-wide Cloud Run role,
operations role, service-account key, Firestore, GCS or secret payload access.
The reader uses GKE metadata tokens and direct Cloud Run v2 REST. A required
`iam.gke.io/gke-metadata-server-enabled=true` node selector prevents node-SA
fallback on Standard node pools; no metadata email-format assumption is made.

The Parakeet KSA has no cloud annotation. Batch Kubernetes RBAC only permits
get/patch on `prod-omi-incluster-guards-batch-state`. The aggregate input is a
read-only volume; this guard cannot update or list its source. Both Jobs retain
CPU-only affinity, non-root execution, read-only filesystem and bounded resources.
Network egress must allow DNS, GKE metadata, Kubernetes API and Run API; blocked
access fails the Job. Error logs contain exception types, never HTTP bodies/env.

## Serving state, rollback and interruption

Each reading verifies service reconciliation and all four **actual traffic
statuses**, fetches their serving revisions, and matches each template against
that revision. It currently supports one untagged 100%-traffic revision per
service; splits/tags/unserved templates fail closed. It never updates an
unserved concurrent train. The identity hashes serving revision names, admission
percent and all other template config. Every identity change starts a fresh full
30-minute arming window **after** all four readbacks, including release changes.
Mixed percentages fail closed. Already-zero admission is NOOP.

A proven hard trip persists all four pinned configuration hashes and unique
candidate revision names before any write. For each service independently:

1. Re-read service/traffic and check the pinned configuration and serving revision.
2. Deep-copy containers and modify only the unique `BATCH_PIPELINE_PERCENT` entry
   to `0`. Other env entries, secret references, sidecars, image artifact, resources and
   other container settings are preserved, equivalent to `--update-env-vars`.
   Mutable template image tags are pinned to the digest reported by their
   verified serving revision, preventing a changed registry tag from shipping
   different code during rollback.
3. PATCH with service etag and narrow update mask, pinning traffic to the old
   serving revision while the named candidate is created. No operations.get is
   needed: bounded service GETs wait for reconciliation.
4. Verify the candidate's configuration and percent, then PATCH only traffic with
   another etag to explicitly promote it. Read actual traffic/revision again.
5. After all independent attempts, re-read the whole fleet and require actual
   serving zero on all four with the original non-percent configuration hashes.

Any drift, API error or incomplete readback fails loudly. The intent remains
pending, even when the input disappears, so later Jobs retry the same named
candidates and continue the other services. A completed service is verified
without another mutation. An interrupted candidate creation resumes at promotion.
There is no transaction across four services; partial failure can temporarily
leave mixed percentages. Treat `ROLLBACK_FAILED` as an incident. There is no
automatic ramp-up, data deletion, recovery cancellation or held-custody mutation.

## Safety aggregate input (draft contract; producer required)

**Do not retire P90 yet.** Existing worker metrics contain only a historical
queue-age proxy. They cannot prove the P90 new-projection/custody/speech signals.
The approved Cloud Run IAM does not grant customer metadata access. This PR
implements the strict aggregate consumer and rollback, not a new database/GCS
reader or an aggregate producer. Lead must assign and verify a trusted producer
and alert delivery before relying on this as the sole unattended safety owner.
Missing or stale input is BLIND, never CLEAN or an invented hard trip.

Publish numeric aggregates in ConfigMap `prod-omi-batch-ramp-safety`, data key
`snapshot.json` (override `batch.safetyConfigMap` only to an approved producer).
The producer reads guard state (`identity`, `since`) from the batch-state
ConfigMap. `arm_since` must equal that state `since`, the all-serving observation
clock. The snapshot `since` is the lead's actual **first ramp-write** clock,
which can precede all-serving confirmation; it is bound on the first valid input
that is complete (or independently proves a trip after arming), and cannot move
within the identity. An incomplete or unknown snapshot stays BLIND and cannot
pin that clock, including during arming. Measurements include partial-apply admissions,
and custody covers retained obligations from prior steps as in P90. The producer
scopes measurements to those clocks and the exact serving fleet. It
must invalidate data on serving drift. No env, account/job/object identifiers,
transcript or media content belongs in either ConfigMap or logs. The identity
is an opaque SHA256; the algorithm lives in `snapshot()` and `digest()`.

Schema `incluster_batch_safety_snapshot_v1`:

```json
{
  "schema_version": 1,
  "identity": "<identity from batch-state>",
  "since": 0,
  "arm_since": 0,
  "observed_at": 1800,
  "read_completed_at": 1800,
  "custody": {"missing": 0, "unknown": 0},
  "proven_terminal_loss_speech_seconds": 0,
  "proven_failed_held_speech_seconds": 0,
  "since_t0_projection_obligations_over_15m": 0,
  "since_t0_stuck_jobs_over_30m": 0,
  "terminal_unrecovered_speech_unknown_units": 0,
  "since_t0_failed_held_unknown_duration": 0,
  "terminal_unrecovered_speech_vad_fallback_units": 0,
  "since_t0_failed_held_vad_fallback_units": 0
}
```

The timestamps are Unix seconds, not the RFC3339 strings emitted by the scratch
P90 sampler; its producer adapter must convert them and attach the verified
identity/epoch. Example numbers above are illustrative, not a deployable sample.
Require `0 <= since <= arm_since <= observed_at <= read_completed_at <= now` and observation age
<=600s. Missing/changed first-write clocks, wrong arming epoch/identity, negative, nonfinite, boolean, denied or
stale safety values remain BLIND. Before the full new-state 30m window, valid
input is WARMUP. After it, positive pinned-custody missing, per-unit proven
terminal/failed-held VAD speech, new projection obligations older15m, or new
stuck jobs older30m trip. Independently proven trips win over other unknowns.
Fallback VAD/duration and missing safety evidence hold clean assessment; quality
p95/first-summary/log errors remain WATCH and do not auto-trip. Blindness does
not itself roll admission back (P90 fast-mode ruling).

The producer owns the P90 missing-object fresh-state race check, positive per-unit
VAD proof, released/privacy-erased custody exclusion and exact new-job scope.
These cannot be reconstructed from the historical queue proxy. A current input
does not qualify a clean two-hour ramp or a later ramp stage by itself.

## Activation and rollback checklist

Lead applies the reviewed IAM packet, then deploys this independent release from
the merged source SHA using the existing workflow. Verify the actual batch
KSA/GSA token identity, source script, ConfigMap updates, trusted aggregate
producer, thirty-minute clock reset, and a complete four-service readback. Prove
Grafana delivers failed/missing-job alerts; the existing failed-job expression
also matches the `-batch-` Jobs. Record runtime evidence before retiring P90.

For an access incident, stop batch scheduling and verify active Jobs ended,
disable (never delete) the dedicated GSA, remove the four per-service grants and
its SA-level actAs/WIF grants. Disabling the GSA rejects existing access tokens
and prevents new ones ([Google IAM disable API](https://docs.cloud.google.com/iam/docs/reference/rest/v1/projects.serviceAccounts/disable)).
Preserve state/audit artifacts before removing the release resources.
Removing the guard does not undo an applied percent-zero rollback.

See Google's [env update semantics](https://docs.cloud.google.com/run/docs/configuring/services/environment-variables),
[service etag/traffic API](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.services),
and [GKE WIF binding procedure](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity).
