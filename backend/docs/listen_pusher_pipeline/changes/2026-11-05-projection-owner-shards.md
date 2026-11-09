# Owner-hash projection shards, push wakes, fresh-first drains, blocked-head deadline

Before this change, every backend-integration instance paged the same global
`committed_at` keyset and raced its peers for each owner's advisory claim.
Each pass reset the cursor. Most turns ended `claim_busy` or found nothing,
while the GPUs sat near 20% and the persisted backlog grew. The fix is in four
parts.

1. **One writer per owner.** Owners hash to 64 shards. Each shard has a 30 s
   Redis lease held by one serving process, and the leases balance across
   members. Only the holder drains the shard's owners, so drains stop
   competing for claims. The claim and the transactional predecessor fence
   still guard every assignment.
2. **Push wakes instead of polling.**
   - A merge commit pushes a wake for the owner's shard holder.
   - The GPU worker's own commits have no Redis, so the maintenance leader
     follows the newly committed tail each tick.
   - The leader alone runs a discovery-only backstop over the durable log,
     and followers no longer sweep.
   - Tail/backstop discovery atomically creates a wake only if the owner has
     none in either lane. Replays leave existing scores and sequences untouched,
     including taken wakes and future retries in the opposite lane. Real commit
     notifications still bump the sequence even if their score stays unchanged,
     so settlement or deferral cannot erase new work arriving during a turn.
     GPU-only rows racing with settlement remain in the durable log and are
     revisited by the resuming whole-log backstop if their replay preceded removal.
   - Firestore reads drop from N instances paging the full keyset every 20 s
     to one leader paging at most 30 pages per tick, with no per-row pre-read.
3. **Fresh first.** Commits of audio captured under 6 h ago take the `fresh`
   lane, newest capture first. Two drain slots per process stay reserved for
   backlog while backlog waits. A stuck owner moves behind due owners,
   including when it has wakes in both lanes: defer its taken backlog wake
   before moving fresh into backlog, preserving both sequence checks. A push
   arriving during the drain keeps its lane position. Productive shard owners
   yield after one drain turn and re-enter backlog admission one pump tick later,
   behind already-due work; the two-slot backlog reserve applies again on every
   admission. Redis takes only scores at or before the wall clock, before the
   page limit, and admission checks that bound again. Persisted future retry
   scores survive holder restarts or moves without consuming backlog reserve;
   reading them neither mutates their score nor their sequence. Legacy local
   continuations keep their FIFO behavior. Future captures use backlog, with no
   clock-skew allowance. Tail discovery routes each owner using its freshest
   capture across the bounded pages, retaining its oldest commit for backlog.
4. **Every non-terminal head has an exit.**
   - Failing heads already took the held disposition after 24 h. That bound
     is now `BATCH_PROJECTION_HEAD_DEADLINE_SECONDS`.
   - Behind `BATCH_PROJECTION_BLOCKED_HEAD_DEADLINE_ENABLED` (default off),
     never-passing `ProjectionBlocked` heads on a closed allowlist take the
     same held disposition once the deadline lapses. Audio is kept and the
     reviewed redrive owns the unit. Each exact allowlisted message has its
     own bounded episode token, retaining the closed reason code as well;
     changing either component starts a fresh deadline.
   - Prod enablement needs David's approval.

All new switches default to today's behavior. Shards apply to the serving
loops only. A dedicated projection pump process (`BATCH_PIPELINE_PROJECTION_PUMP_ENABLED`)
keeps its plain sweep. With `BATCH_PIPELINE_SERVING_PROJECTION_SWEEP=off` the
leader skips the tail and the backstop, but commit wakes still flow.

Not included:
- Transactional multi-row assignment batching. It touches the core receipt
  transaction and needs its own review.
- Provider-stt and enrichment fresh-first ordering, which is #24714.

Contract: [Batch projection owner shards](../../listen_pusher_pipeline.mdx#batch-projection-owner-shards).
Hermetic coverage:
- `tests/unit/test_batch_projection_shards.py`: leases, wakes, pump, serving
  wiring and the deadline.
- `tests/unit/test_batch_projection_shard_drain.py`: two processes with real
  drains on shared fakeredis.
