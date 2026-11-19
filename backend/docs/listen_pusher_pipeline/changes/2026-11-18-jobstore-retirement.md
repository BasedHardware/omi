# Jobstore retained-copy rotation

The serving supervisor on Cloud Run backend-integration rotates one bounded
PG table/source page per tick. Migration 0010 stores and locks the cursor in
the same transaction as page mutations, with version-and-cursor CAS. No schema
migration runs at boot. See [the owning contract](../../jobstore-production-mirror.md)
for budgets, telemetry, deletion executor inventory and the CLI fallback.

Production target/context bindings reach the serving host, Cloud Run deletion
executors, listen and the GPU writer. Mirroring remains off and mode remains
firestore. First copying and recovery hints require the release-owned activation
packet, applied schema/grants, mode-off erasure and measured full rotation.
