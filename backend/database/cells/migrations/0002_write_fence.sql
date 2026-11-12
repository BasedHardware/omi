-- B2: retain the per-space head as a durable admission tombstone after wipe.
-- Only enrollment/backfill creates heads; every writer locks and checks this row.
ALTER TABLE space_heads ADD COLUMN tombstoned boolean NOT NULL DEFAULT false;
