-- P5 isolated experiment result, pair, and finalized-grounding persistence.
-- The application role can append and verify experiment rows only. These
-- grants cannot mutate graph, product, durable work, recall, or answer state.

REVOKE ALL ON omi_memory.memory_strategy_evaluation_baselines FROM PUBLIC;
REVOKE ALL ON omi_memory.memory_strategy_shadow_results FROM PUBLIC;
REVOKE ALL ON omi_memory.memory_strategy_evaluation_pairs FROM PUBLIC;
REVOKE ALL ON omi_memory.memory_strategy_baseline_read_groundings FROM PUBLIC;
REVOKE ALL ON omi_memory.memory_strategy_candidate_read_groundings FROM PUBLIC;

GRANT SELECT, INSERT ON omi_memory.memory_strategy_evaluation_baselines
  TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_strategy_shadow_results
  TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_strategy_evaluation_pairs
  TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_strategy_baseline_read_groundings
  TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_strategy_candidate_read_groundings
  TO omi_platform_application;

-- Intentionally no UPDATE, DELETE, TRUNCATE, graph, product, work, recall,
-- query-input, blind-label, grading, statistics, route, or model-execution grant.
