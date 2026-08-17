# Model-pipeline resource exclusivity contract

Status: route-free production-neutral kernel; no provider/resource default

## Boundary

`ModelPipelineExclusivity` serializes complete model-dependent producer phases
by an opaque digest. The provider-credential owner supplies a stable digest for
the actual shared provider resource and its generation. It must not substitute
the database worker credential: two workers using one provider key must resolve
to one resource even when their database credentials differ. API keys, provider
names, prompts, model output, account identifiers, and user content never enter
the lock coordinate or outcome.

The durable runner acquires exclusivity only when no normalized result is staged.
A replay that finds a staged result performs no resource acquisition and no model
call. Contention is a retryable `model_rate_limited` durable-work failure;
infrastructure failure is `dependency_unavailable`.

The PostgreSQL adapter uses `pg_try_advisory_lock` on a separately reserved
session. It deliberately holds no database transaction while model work runs.
The same connection owns the lock until the callback settles, then performs the
exact unlock before release. An unlock or connection-health failure quarantines
the reservation instead of returning unknown lock state to the pool.

The formation and predicate one-shot runtimes require an exclusivity port and an
explicit resource resolver at construction. They add no credential issuer,
provider/model default, timer, polling loop, route, deployment, or runtime
activation.

## Operational qualification boundary

The model lock pool must be distinct from the transaction pool used inside the
producer; a size-one shared pool would deadlock while the producer loads its
input. Capacity admission must reserve this connection class separately.

Session locks release automatically when a worker process and its connection
terminate. A database connection can also fail independently while an external
model request remains in flight; PostgreSQL cannot fence that provider request.
Therefore this kernel proves healthy-connection cross-process exclusion, while
activation under independently lossy database connections additionally requires
a cancellable provider invocation or an operationally stronger resource fence.
That residual is explicit and prevents overstating exactly-once model execution.
