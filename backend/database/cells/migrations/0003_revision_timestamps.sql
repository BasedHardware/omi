-- Datetime revision tokens must follow the same commit order as sequences.
-- Keep caller event/retention timestamps separate from this server authority.
ALTER TABLE space_heads ADD COLUMN revision_us bigint NOT NULL DEFAULT 0;
ALTER TABLE change_log ADD COLUMN committed_at float8;

-- Pre-migration timestamps are untrusted for revision resolution. Leave them
-- NULL: clients must rebase with integer revisions rather than risk overwrites.
