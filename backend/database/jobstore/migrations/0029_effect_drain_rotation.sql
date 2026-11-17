-- Per-owner bounded drain rotation must survive janitor owner backoff updates.
-- This is scheduling metadata, never erasure proof or a custody expiry.
ALTER TABLE privacy_effect_inflight ADD COLUMN drain_after timestamptz NOT NULL DEFAULT now();
