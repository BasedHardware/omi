# Tombstone restore application coordinator

Status: inert production-neutral application contract. No route, runtime
composition, persistence adapter, traffic gate, or deployment default is
provided by this unit.

## Boundary

`defineTombstoneRestoreApplicationCoordinator` composes three named injected
ports:

1. a retention-locked terminal-set source returns the complete manifest and
   matching source receipt, or explicit `null` when no complete source exists;
2. a terminal-feed adapter holds one fence around the entire callback and
   exposes its current receipt; and
3. a target adapter applies one manifest record and returns one closed core
   outcome, or explicit `null` for missing progress.

Construction accepts one exact plain dependency record whose three ports each
contain exactly one own data-method. Those methods are captured and bound at
construction; later mutation or accessor substitution cannot redirect work.
The held-fence session is likewise required to expose exactly one own
`readCurrentFence` data-method, captured before the first fence read.

The coordinator validates and detaches the source before acquiring the fence.
Inside one held-fence callback it verifies the initial receipt, applies records
sequentially, validates and detaches every outcome before the next await, then
reads the fence again. A checkpoint can be returned only when the final receipt
is byte-equivalent to the initial held receipt and the existing core verifier
accepts the exact source, manifest, application set, and fence coordinates.
The coordinator also closes a callback-lifetime lease when the fence wrapper
returns. A callback invoked later performs no fence or target I/O, and a
callback resumed after an await rechecks the lease before its next operation.

Missing source is a closed stop, not an empty set. Missing target application
is omitted from the outcome set and therefore becomes the core
`application_missing` blocker. Dependency exceptions and malformed dependency
values collapse to bounded codes; provider text is never returned.

## Non-authority

A successful report says only that tombstone replay does not fence the future
traffic decision. The coordinator does not open traffic and does not mint or
grant authentication, authorization, account control, generation activation,
entitlement, or application access. Consumers must still revalidate current
subordinate account control at the traffic decision.

The injected fence adapter is responsible for the external guarantee that the
source feed remains held for the callback. Its concrete implementation must
await the callback and drain its own in-flight operations before resolving and
releasing the fence; the coordinator cannot recover a write that a broken
adapter starts and then falsely reports complete. Real retention-sink, legacy,
PostgreSQL target, infrastructure restore, and traffic adapters remain separate
production gates.
