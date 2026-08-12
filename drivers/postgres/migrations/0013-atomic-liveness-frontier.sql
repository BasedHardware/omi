-- Liveness is graph state: a purge/forget fence must identify the append that
-- advanced the account graph head. Pre-activation rows without that coordinate
-- are rejected instead of being silently assigned false provenance.

DO $migration$
BEGIN
  IF EXISTS (
    SELECT 1 FROM omi_memory.memory_claim_liveness_fences LIMIT 1
  ) THEN
    RAISE EXCEPTION 'legacy liveness fences require an explicit rebuild'
      USING ERRCODE = '23514';
  END IF;
END;
$migration$;

ALTER TABLE omi_memory.memory_claim_liveness_fences
  ADD COLUMN commit_id text;

ALTER TABLE omi_memory.memory_claim_liveness_fences
  ALTER COLUMN commit_id SET NOT NULL;

ALTER TABLE omi_memory.memory_claim_liveness_fences
  ADD CONSTRAINT memory_claim_liveness_fences_commit_fk
  FOREIGN KEY (account_id, commit_id)
  REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id);
