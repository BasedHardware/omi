-- Contract (b): the Postgres Outbox. One table for every OutboxKind; (kind, dedupe_key) is the
-- natural key a producer coalesces on. No user content: `payload` is the content-free, <= 4 KiB
-- mapping the contract allows.
--
-- `lease_token` / `wake_token` are uuid-ish text minted by the store. `available_at` /
-- `lease_until` are epoch seconds (float8), matching the Firestore rows and the `now=` parameters.

CREATE TABLE outbox (
    id           bigserial PRIMARY KEY,
    namespace    text   NOT NULL,
    kind         text   NOT NULL,
    dedupe_key   text   NOT NULL,
    owner_id     text   NOT NULL,
    payload      jsonb  NOT NULL DEFAULT '{}'::jsonb,
    policy_id    text,
    available_at float8 NOT NULL,
    version      bigint NOT NULL DEFAULT 1,
    attempts     int    NOT NULL DEFAULT 0,
    wake_token   text,
    lease_token  text,
    lease_until  float8 NOT NULL DEFAULT 0,
    done_at      float8,
    done_reason  text,
    created_at   float8 NOT NULL,
    CONSTRAINT outbox_payload_small CHECK (octet_length(payload::text) <= 4096)
);
-- At most one OPEN row per (kind, dedupe_key): this is the coalescing invariant.
CREATE UNIQUE INDEX outbox_open_dedupe ON outbox (namespace, kind, dedupe_key) WHERE done_at IS NULL;
CREATE INDEX outbox_claimable ON outbox (namespace, kind, available_at) WHERE done_at IS NULL;
CREATE INDEX outbox_owner ON outbox (namespace, owner_id) WHERE done_at IS NULL;
