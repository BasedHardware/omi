# Ruled integration canary for source 0714

This is the finite SCA-2283 Cloud Run path for application source
`0714c5198be8f0183c8fd7dd3810d53c91af17a4`. It is selected automatically by
the existing production `gcp_backend.yml` deploy job for that exact admitted
source. Other sources and development keep their existing deployment path.
There is no new public workflow or independent local writer mode.

The captain subsequently ordered GKE first. This Cloud Run implementation
does not dispatch, approve or change GKE, GPU workloads or the worker. It
does not offer a three-service image-deploy mode; the separate ops-env subset
fold restores configuration and cannot deploy a new application image.

## Admission and invocation

Before use, the release owner must have the complete exact-head source review,
green required checks, normal merge/admission and scoped release go-ahead for
these workflow controls. A review of the earlier offline temporal contract is
not a review of this executable implementation. Verify the installed/main
workflow controls contain the reviewed change before dispatching; the old
workflow sends integration directly to 100% and is unsuitable for this ruling.

Use the existing release-owner deployment wrapper for this exact application
source, with its recorded, scoped CPU-headroom waiver where required by the
captain's ruling:

```bash
bin/omi-deploy-prod cloud-run 0714c5198be8f0183c8fd7dd3810d53c91af17a4
```

The wrapper's mechanical holds, hold-clean window, active-lock wait, eligibility,
index-run, drift and headroom checks remain applicable. The workflow retains
its Firestore readiness dependency, protected production environment and shared
noncancelling `prod-train` lock. Break-glass eligibility or lock flags are
refused for this path. No direct helper invocation or caller-supplied boolean
replaces those gates. The helper's workflow/run checks prevent accidental local
use; they are not a new authentication or admission authority.

## Candidate preparation

After image build/source resolution and before the service deployments, the
controller captures all four actual serving revision definitions and a fresh
30-minute CPU/request baseline. The baseline's actual observation interval is
recorded and remains immutable through promotion; it is not an operator-supplied
time or share. Integration must serve the named rollback revision
`backend-integration-provfix-off1114` at 100%.

The renderer composes the existing native ops-fold key ownership from these
serving revisions into all four candidate inputs. It preserves fresh queue
bindings and literal/secret-reference representations. The ruled quality values
are true/86400/true for `HOME_TRANSCRIPTION_QUEUE_HOLD_ENABLED`,
`HOME_TRANSCRIPTION_MAX_AGE_SECONDS`, and `RECORD_SEAL_REPAIR_FRESH_ENABLED` on
all four services. Finish backoff is false on integration/sync and removed from
backend/backfill; provider backlog release stays false. Every candidate is
stamped with the exact application source.

Integration's candidate is cloned from its actual serving revision rather than
its potentially failed service template, preserving sidecars, service account,
secrets, resource limits, scaling and maximum instances. Its image is pinned
to the independently read registry digest/source. A resourceVersion CAS creates
the final named no-traffic candidate once; no subsequent sidecar attachment
creates another integration revision. The native readiness, runtime validation,
no-traffic Cloud Run candidate verification and serving-vector checks remain.

Do not run a subsequent integration ops fold or stamp/queue update after the
canary. Those settings are already in its candidate before the first traffic
move. Other services retain their normal deployment/traffic path.

## Traffic and health

Under the same workflow lock, the other three services move normally.
Integration refreshes its CPU/request preflight: actual whole-window CPU p95
must be <= .90 and request-weighted 30-minute 5xx share must be < 1%. There is
no scale adjustment to make this pass.

The controller CAS-routes the named candidate to 25%, retaining the rollback at
75%, and verifies both requested and actual traffic, readiness, source/stamp and
configuration. The five-minute hold begins only at verified 25% readback.
After the hold and fresh proof it CAS-routes to 100%, verifies again, and observes
twenty minutes. The controller runs in the foreground of the bounded workflow
step; it does not detach author-owned work. Steady observation polls are sparse.

After **each** verified move, disregard the first three minutes. A health
rollback requires a complete rolling ten-minute window entirely after that
warmup: request-weighted 5xx share strictly above
`max(1.5%, 2 * fixed_baseline_share)`, or CPU p95 >= .95 throughout all ten
minutes. CPU distributions are combined before calculating percentiles;
percentiles and per-minute request shares are not averaged. A five-minute
canary cannot establish that ten-minute window; immature evidence is reported
as such. Missing, stale, partial, malformed or failed Monitoring evidence never
becomes a healthy or complete result.

Native acceptance failures still fail the release. Integration rollback uses
the exact retained provfix target and CAS/readback, and refuses foreign drift.
An already completed rollback is idempotent. The other three services retain
the native traffic-snapshot restore even if integration recovery refuses.
No revision deletion or rollback-retention waiver is introduced.

## Evidence and failure recovery

The private journal lives under `RUNNER_TEMP` with mode 0600. It contains
configuration and secret references: never upload, print or copy its contents
to an issue. Durable mutation intent precedes every write; uncertain writes
are not blindly repeated. A failed or interrupted rollout needs release-owner
reconciliation through the normal workflow/recovery boundary, not a forged
local workflow environment or a helper flag bypass.

The existing evidence artifact includes `integration-canary-receipt.json`, an
explicit metadata-only projection: exact source/digest/revision, phase and
verified move clocks, baseline/health aggregates, and intent kind/status.
It excludes service/revision definitions, env values, secret references,
tokens and provider bodies. The native release-vector and traffic-snapshot
artifacts remain available. Successful local tests or CI source checks are not
production readback: the release owner still posts actual SERVING lines and
the captain's final +20-minute acceptance evidence.
