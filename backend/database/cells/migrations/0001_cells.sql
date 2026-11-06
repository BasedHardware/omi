-- B1 cell store: per-space documents, one ordered change log, device cursors.
-- Doc mode (plan-v1 R2): the whole document lives in `doc jsonb`; query columns are added as
-- STORED generated columns by later expand-only migrations when a domain port promotes its table.
-- Every row is scoped by leading space_id; doc rows carry author_id (R1) and rev = the change_log
-- seq that last wrote them (R8). Expand-only, like every jobstore migration.

-- The per-space seq authority (R6). `next_seq` is the last ALLOCATED seq; 0 = fresh space.
-- Writers allocate with INSERT .. ON CONFLICT DO UPDATE (row lock held to commit), so per-space
-- allocation order == commit order. Backfill copies this row so seq continues across cell moves.
CREATE TABLE space_heads (
    space_id   text COLLATE "C" NOT NULL,
    next_seq   bigint NOT NULL,
    epoch      bigint NOT NULL DEFAULT 1,
    updated_at float8 NOT NULL,
    PRIMARY KEY (space_id),
    CONSTRAINT space_heads_next_seq_nonneg CHECK (next_seq >= 0),
    CONSTRAINT space_heads_epoch_positive CHECK (epoch >= 1)
);

CREATE TABLE cell_docs (
    space_id   text COLLATE "C" NOT NULL,
    entity     text COLLATE "C" NOT NULL,
    entity_id  text COLLATE "C" NOT NULL,
    author_id  text COLLATE "C" NOT NULL,
    rev        bigint NOT NULL,
    doc        jsonb NOT NULL,
    updated_at float8 NOT NULL,
    PRIMARY KEY (space_id, entity, entity_id),
    CONSTRAINT cell_docs_rev_positive CHECK (rev >= 1)
);

-- The device feed (R6/R7): content-free (ids/op/rev/mutation_id), one row per coalesced entity
-- change per transaction. `op='delete'` rows ARE the tombstones (kept unbounded by compaction).
-- `rev` equals `seq` by construction; kept as the protocol's rev slot and pinned so it cannot drift.
CREATE TABLE change_log (
    space_id           text COLLATE "C" NOT NULL,
    seq                bigint NOT NULL,
    entity             text COLLATE "C" NOT NULL,
    entity_id          text COLLATE "C" NOT NULL,
    op                 text NOT NULL,
    rev                bigint NOT NULL,
    actor_uid          text COLLATE "C" NOT NULL,
    client_mutation_id text COLLATE "C",
    fingerprint        text COLLATE "C",
    feed               boolean NOT NULL DEFAULT true,
    ts                 float8 NOT NULL,
    PRIMARY KEY (space_id, seq),
    CONSTRAINT change_log_op_domain CHECK (op IN ('upsert', 'delete')),
    CONSTRAINT change_log_rev_is_seq CHECK (rev = seq),
    CONSTRAINT change_log_rev_positive CHECK (rev >= 1),
    CONSTRAINT change_log_fingerprint_with_mutation CHECK (client_mutation_id IS NULL OR fingerprint IS NOT NULL)
);
-- Content-free replay receipts have an independent 90-day retention domain.
-- No FK to change_log: feed compaction must never remove a replay receipt.
CREATE TABLE mutation_receipts (
    space_id           text COLLATE "C" NOT NULL,
    client_mutation_id text COLLATE "C" NOT NULL,
    seq                bigint NOT NULL,
    fingerprint        text COLLATE "C" NOT NULL,
    created_at         float8 NOT NULL,
    PRIMARY KEY (space_id, client_mutation_id),
    CONSTRAINT mutation_receipts_seq_positive CHECK (seq >= 1)
);
CREATE INDEX mutation_receipts_retention ON mutation_receipts (space_id, created_at, client_mutation_id);

-- Device pull cursors live in the cell (space-scoped) so compaction needs no cross-database call.
CREATE TABLE sync_cursors (
    space_id     text COLLATE "C" NOT NULL,
    device_id    text COLLATE "C" NOT NULL,
    last_seq     bigint NOT NULL,
    last_seen_at float8 NOT NULL,
    PRIMARY KEY (space_id, device_id),
    CONSTRAINT sync_cursors_last_seq_nonneg CHECK (last_seq >= 0)
);
-- Covering index for the floor scan: min(last_seq) over devices seen in the retention window.
CREATE INDEX sync_cursors_floor ON sync_cursors (space_id, last_seen_at, last_seq);
