-- P5 expand-only vocabulary for isolated retrieval/composition evaluation.
-- Durable work tables deliberately retain their four graph-writing work kinds.

ALTER TABLE omi_memory.memory_strategy_definitions
  DROP CONSTRAINT memory_strategy_definitions_work_kind_check,
  ADD CONSTRAINT memory_strategy_definitions_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition'
  ));

ALTER TABLE omi_memory.memory_strategy_assignment_policies
  DROP CONSTRAINT memory_strategy_assignment_policies_work_kind_check,
  ADD CONSTRAINT memory_strategy_assignment_policies_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition'
  ));

ALTER TABLE omi_memory.memory_strategy_policy_shadows
  DROP CONSTRAINT memory_strategy_policy_shadows_work_kind_check,
  ADD CONSTRAINT memory_strategy_policy_shadows_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition'
  ));

ALTER TABLE omi_memory.memory_strategy_assignment_bundles
  DROP CONSTRAINT memory_strategy_assignment_bundles_work_kind_check,
  ADD CONSTRAINT memory_strategy_assignment_bundles_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition'
  ));

ALTER TABLE omi_memory.memory_strategy_shadow_assignments
  DROP CONSTRAINT memory_strategy_shadow_assignments_work_kind_check,
  ADD CONSTRAINT memory_strategy_shadow_assignments_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition'
  ));

ALTER TABLE omi_memory.memory_strategy_evaluation_baselines
  DROP CONSTRAINT memory_strategy_evaluation_baselines_work_kind_check,
  ADD CONSTRAINT memory_strategy_evaluation_baselines_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition'
  ));

ALTER TABLE omi_memory.memory_strategy_shadow_results
  DROP CONSTRAINT memory_strategy_shadow_results_work_kind_check,
  ADD CONSTRAINT memory_strategy_shadow_results_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition'
  ));

-- No grant, role, trigger, function, route, worker, or product-authority change.
