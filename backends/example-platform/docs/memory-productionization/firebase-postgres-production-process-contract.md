# Firebase/PostgreSQL production memory process kernel

Status: production-neutral P8 lifecycle boundary. No listener or deployment is
activated.

## Boundary

`createPostgresFirebaseAuthorizedMemoryServiceProcess` is the only process
lifecycle wrapper around the canonical Firebase/PostgreSQL memory application.
It keeps the raw Hono application private and exposes only `start`, `fetch`,
`stop`, and a content-safe snapshot.

The constructor requires the exact closeable PostgreSQL pool already embedded
in the service options. Its readiness dependency must be minted by
`createPostgresProductionRuntimeReadiness` for that same pool and the exact
database-generation digest in the Firebase authorization composition. A
caller-supplied success callback, a readiness proof for another pool, or a
proof for another generation is rejected before app construction. Later
dependency mutation cannot retarget the process.

The sealed startup proof uses one read-only serializable transaction and one
fixed application-role function. It admits only PostgreSQL 18.4, the complete
compiled migration manifest with exact names and SHA-256 values and no extra
row, and an exact currently released database-generation head. The application
role receives no direct table read. Provider errors and malformed rows collapse
to unavailable without entering process state or output.

## Lifecycle

- Constructed and starting processes answer liveness but return fixed 503
  unavailable bytes for readiness and every domain request.
- Readiness becomes 200 only after the sealed PostgreSQL startup proof returns
  exact `true`. Failure or malformed success never opens admission.
- Stopping changes the phase synchronously, so no later domain request can
  enter. Requests admitted before that edge drain before the exact pool closes.
- A readiness callback completing after stop has begun cannot reopen traffic.
- Start and stop replay deterministically. Pool close runs at most once; a
  close failure is terminal `failed`, never successful shutdown.
- Stopped or failed process objects return 503 for both health and readiness.

The proof is intentionally a startup edge, not a cached authority grant. Every
request still revalidates the current generation release, retained account
tombstone, lifecycle, credential, grant, capability, and epoch through the
existing database functions. A process started before release remains
unavailable until explicitly restarted; this slice does not create an implicit
traffic transition or continuous readiness poller.

No timeout is inferred. The future process adapter must impose its ratified
shutdown deadline and terminate the host process if cooperative draining cannot
finish. This kernel preserves the exact requests already admitted so that
runtime qualification can measure, rather than assume, the deadline.

## Exclusions

This module imports no SQLite/QA store, dev token, QA control route, listener,
environment reader, signal handler, worker loop, or model. It does not decide
MCP credentials, query recall, port binding, pool capacity, OCI image/runtime,
secret loading, release, deployment, or traffic.
