-- P3 one-shot execution state grant. The sealed driver may append immutable
-- work-state revisions, advance only the matching head coordinates, and emit
-- a dead-letter outbox row in the same transaction. No poller, model, result
-- success, product route, or deployment is activated.

REVOKE ALL ON omi_memory.memory_work_outbox_events FROM PUBLIC;

GRANT INSERT ON omi_memory.memory_work_outbox_events
  TO omi_platform_application;

GRANT UPDATE (state_revision, state_digest, updated_at)
  ON omi_memory.memory_work_heads
  TO omi_platform_application;

-- Existing migration 0014 supplies SELECT/INSERT on acceptance, immutable
-- state, and head rows; 0015 supplies SELECT on the exact execution policy.
-- UPDATE/DELETE on acceptance, policy, manifest, state revisions, and outbox
-- rows remain forbidden.
