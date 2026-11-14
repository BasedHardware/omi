-- G2 close work is transactional with the close, independent of transient wakes.
-- Tasks contain erasure metadata only and disappear after the drain completes.
CREATE TABLE privacy_close_drain (
 owner_key text NOT NULL,
 seq bigint NOT NULL,
 conversation_key text,
 available_at timestamptz NOT NULL DEFAULT now(),
 lease_token uuid,
 lease_until timestamptz,
 attempts int NOT NULL DEFAULT 0 CHECK (attempts >= 0),
 PRIMARY KEY (owner_key, seq),
 FOREIGN KEY (owner_key, seq) REFERENCES privacy_fence_change(owner_key, seq)
);
CREATE INDEX privacy_close_drain_due ON privacy_close_drain(available_at, owner_key, seq);
CREATE INDEX privacy_effect_expiry ON privacy_effect_inflight(lease_until, owner_key);
REVOKE ALL ON privacy_close_drain FROM PUBLIC;

-- A stuck sink must not monopolize every bounded janitor discovery page.
ALTER TABLE privacy_effect_inflight ADD COLUMN maintenance_after timestamptz NOT NULL DEFAULT now();

-- A restore changes the job admission, never the identity of an already-paid
-- attempt. Legacy unresolved attempts have NULL here and fail closed.
ALTER TABLE units ADD COLUMN attempt_admission_id uuid;
