# Firebase/PostgreSQL production memory process kernel

Status: production-neutral P8 lifecycle boundary. No listener or deployment is
activated.

## Boundary

`createPostgresFirebaseAuthorizedMemoryServiceProcess` is the only process
lifecycle wrapper around the canonical Firebase/PostgreSQL memory application.
It keeps the raw Hono application private and exposes only `start`, `fetch`,
`stop`, and a content-safe snapshot.

The constructor requires the exact closeable PostgreSQL pool already embedded
in the service options. It captures that pool's close method and the injected
readiness check synchronously. A different pool cannot be closed as a proxy for
the one serving requests, and later dependency mutation cannot retarget the
process.

## Lifecycle

- Constructed and starting processes answer liveness but return fixed 503
  unavailable bytes for readiness and every domain request.
- Readiness becomes 200 only after the injected dependency check returns exact
  `true`. Failure or malformed success never opens admission.
- Stopping changes the phase synchronously, so no later domain request can
  enter. Requests admitted before that edge drain before the exact pool closes.
- A readiness callback completing after stop has begun cannot reopen traffic.
- Start and stop replay deterministically. Pool close runs at most once; a
  close failure is terminal `failed`, never successful shutdown.
- Stopped or failed process objects return 503 for both health and readiness.

No timeout is inferred. The future process adapter must impose its ratified
shutdown deadline and terminate the host process if cooperative draining cannot
finish. This kernel preserves the exact requests already admitted so that
runtime qualification can measure, rather than assume, the deadline.

## Exclusions

This module imports no SQLite/QA store, dev token, QA control route, listener,
environment reader, signal handler, worker loop, or model. It does not decide
MCP credentials, query recall, port binding, pool capacity, OCI image/runtime,
secret loading, release, deployment, or traffic.
