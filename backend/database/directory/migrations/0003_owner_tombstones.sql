-- Content-free erasure admission fence, independent of routing mode and spaces.
-- No FK: this row must survive purge_owner, including an owner never enrolled.
CREATE TABLE owner_tombstones (
    uid text COLLATE "C" PRIMARY KEY,
    wipe_epoch bigint NOT NULL CHECK (wipe_epoch >= 1),
    cell text COLLATE "C",
    created_at float8 NOT NULL
);
