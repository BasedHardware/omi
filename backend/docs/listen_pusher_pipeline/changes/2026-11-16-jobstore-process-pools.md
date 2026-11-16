# Retained-copy erasure shares bounded process connections

The optional [jobstore production mirror](../../jobstore-production-mirror.md)
now shares two normal PostgreSQL connections and one reserved erasure connection
across namespaces and concurrent cold deletion calls in each process. Normal
mirror/index traffic cannot consume the erasure reserve; erasure errors still
reach the existing durable retry flow. This closes per-call connection fan-out
without selecting a fleet budget or changing Firestore authority.

This source change adds no environment switch and performs no rollout. Copy and
index admission remain owned by the release packet; retained target bindings
must remain reachable with those controls off. Deployment needs the complete
writer/deletion roster, a justified fleet connection bound, privacy acceptance
and measured cost/rotation limits.
