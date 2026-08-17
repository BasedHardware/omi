# Dual-runtime Linux qualification contract

Status: pre-registered P8 gate; no image, runtime, or database activation is
claimed.

## Why this gate is not an image yet

The canonical executable currently has one real HTTP shell and one loopback
SQLite QA composition. PostgreSQL has checksummed schema and sealed repository
contracts, but no ratified client, pool, migration runner, real-database test,
or production service composition. Packaging the QA dev server would produce a
runnable image with the wrong authority, credentials, routes, storage, and
network boundary.

An exact production image starts only after one production composition exists.
That composition must use Firebase identity and application authorization,
the ratified PostgreSQL repositories, the production account-control source,
and no dev token, QA route, seed data, SQLite authority, or printed credential.

## Frozen comparison shape

- Target platform: Linux/amd64 OCI.
- Candidate: Bun 1.3.14.
- Temporary control: the then-current supported Node 24 Krypton LTS patch. As
  of 2026-08-11 the official release index names Node 24.19.0 (2026-08-03).
  The exact version and official image digest are frozen in the run manifest;
  they are not silently floated during comparison.
- Both images use the same source commit, migration manifest, production
  dependency closure, configuration schema, application routes, repository
  implementation, and acceptance workload.
- Runtime-specific code is limited to the HTTP/process adapter and PostgreSQL
  client adapter. The temporary Node adapter and dependency are deleted after
  selection unless Node wins.
- The final dependency layer is created with the frozen omitted-optional
  install and passes `qa:production-deps` after its last copy.

## Prerequisites

No comparison may start until all are true:

1. David ratifies the PostgreSQL major, dormant pgvector compatibility target,
   client driver, and managed local container path.
2. One production composition exists and its import graph excludes every QA
   store, route, dev credential, seed, and model fake.
3. The real PostgreSQL migration, privilege, TLS, pool reset, cancellation,
   backend termination, and tenant-isolation gates pass.
4. Forecast cohort request/work mix, latency objective, concurrency envelope,
   memory/CPU ceiling, shutdown deadline, and accepted connection budget are
   recorded rather than invented by the harness.
5. The candidate and control base-image digests and toolchain checksums are
   frozen before the first measured run.

## Required probes

### Correctness and authority

- Run the same HTTP, PostgreSQL, migration, Firebase boundary, durable-work,
  product-projection, deletion, restore, and experiment-isolation tests in both
  images.
- Exercise at least two accounts concurrently. Cross-account rows, connection
  settings, logs, metrics, traces, caches, AsyncLocal context, cursors, and
  retries must remain indistinguishable from absence to the other account.
- Re-run account epoch, idempotency, stale parent, stale lease, exact grant,
  lifecycle, and deletion-dominance adversarial cases against real PostgreSQL.

### Lifecycle and recovery

- Readiness stays false until migrations, dependency closure, Firebase
  configuration, control source, PostgreSQL TLS/pool, and required workers are
  usable; liveness never substitutes for readiness.
- `SIGTERM` stops new admission and leases, drains in-flight HTTP and work to
  the declared deadline, closes pools, and exits zero. A second signal is
  idempotent.
- Forced kill is injected before model output, after immutable result staging,
  before graph append, after graph append, and before outbox delivery. Restart
  must preserve total work outcomes, reuse staged results without a second
  model call, and never duplicate authority or effects.
- Cancellation and timeout discard or prove-reset PostgreSQL connections; no
  transaction-local account context reaches the next borrower.

### Diagnostics and capacity

- Emit only content-safe correlation, latency/error, pool acquisition and
  saturation, runtime CPU/RSS/restart, fence rejection, backlog age, lease,
  attempt, dead-work, and stale-fence measurements.
- Measure cold start, steady-state latency, CPU, RSS, pool occupancy, shutdown,
  and recovery under the same forecast workload and fresh-image schedule.
- Record raw machine-readable samples and exact commands. Aggregate comparison
  is paired by workload seed/run; no result from a different image, dependency
  closure, database state, or host load is compared as if paired.

## Selection rule

Any correctness, isolation, lost-work, stale-fence, context-bleed,
unexplained-crash, connection-reset, or unbounded-shutdown failure is a no-go.
One rerun is allowed only after pinning one explicit runtime patch; the original
failure remains in evidence.

If Bun passes every binary gate and both runtimes remain within the ratified
capacity/SLO envelope, select Bun unless Node has a measured operational or
resource advantage large enough to justify its additional adapter. If Bun
fails a binary gate after the one pinned rerun, select Node. Do not ship or
maintain co-equal production runtimes.

## Exclusions

- No Docker/Colima installation, image pull/build/publish, Cloud SQL, GCP,
  production credential, secret version, deployment, traffic, or cohort action
  is authorized by this contract.
- No real PostgreSQL claim may be derived from fake/static tests.
- No SQLite/dev-server image can satisfy this gate.
- No load target, SLO, connection budget, RPO/RTO, or data disposition value is
  inferred when its human/external decision is absent.
