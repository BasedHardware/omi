-- Operator-rendered SQL only: psql -v runtime_role=... -v residue_role=...
-- No role creation, IAM, remote connection or migration is performed by import.
-- Runtime must not own these tables or inherit an owner role. Validate effective
-- privileges, including inherited/default grants, before any enforcement ramp.
REVOKE ALL ON privacy_owner_fence, privacy_conversation_fence, privacy_fence_change,
 privacy_fence_config, privacy_residue_target FROM :"runtime_role";
GRANT SELECT, INSERT, UPDATE ON privacy_owner_fence, privacy_conversation_fence,
 privacy_fence_change TO :"runtime_role";
GRANT SELECT ON privacy_fence_config TO :"runtime_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON privacy_effect_inflight TO :"runtime_role";
GRANT SELECT, INSERT ON privacy_residue_target TO :"runtime_role";
GRANT SELECT, UPDATE, DELETE ON privacy_residue_target TO :"residue_role";
