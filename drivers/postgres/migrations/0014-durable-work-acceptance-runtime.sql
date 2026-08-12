-- P3 acceptance-only runtime grant. The application may atomically persist an
-- already-authorized, exact work request and its pending state before any
-- model execution. Leasing, retries, results, success, and outbox delivery
-- remain ungranted until their execution policy and crash gates are ratified.

REVOKE ALL ON omi_memory.memory_strategy_definitions FROM PUBLIC;
REVOKE ALL ON omi_memory.memory_strategy_assignment_policies FROM PUBLIC;
REVOKE ALL ON omi_memory.memory_strategy_policy_shadows FROM PUBLIC;
REVOKE ALL ON omi_memory.memory_strategy_assignment_bundles FROM PUBLIC;
REVOKE ALL ON omi_memory.memory_strategy_shadow_assignments FROM PUBLIC;
REVOKE ALL ON omi_memory.memory_work_acceptances FROM PUBLIC;
REVOKE ALL ON omi_memory.memory_work_input_manifest FROM PUBLIC;
REVOKE ALL ON omi_memory.memory_work_state_revisions FROM PUBLIC;
REVOKE ALL ON omi_memory.memory_work_heads FROM PUBLIC;

GRANT SELECT, INSERT ON omi_memory.memory_strategy_definitions
  TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_strategy_assignment_policies
  TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_strategy_policy_shadows
  TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_strategy_assignment_bundles
  TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_strategy_shadow_assignments
  TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_work_acceptances
  TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_work_input_manifest
  TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_work_state_revisions
  TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_work_heads
  TO omi_platform_application;

-- Intentionally no UPDATE or DELETE and no privilege on
-- memory_work_staged_results, memory_work_successes,
-- memory_work_success_ledger_inputs, memory_work_outbox_events, or any worker
-- execution surface.
