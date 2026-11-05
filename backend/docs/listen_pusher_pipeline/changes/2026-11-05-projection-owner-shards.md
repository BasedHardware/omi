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
   - Firestore reads drop from N instances paging the full keyset every 20 s
     to one leader paging at most 30 pages per tick, with no per-row pre-read.
3. **Fresh first.** Commits of audio captured under 6 h ago take the `fresh`
   lane, newest capture first. Two drain slots per process stay reserved for
   backlog while backlog waits. A stuck owner moves behind due owners.
4. **Every non-terminal head has an exit.**
   - Failing heads already took the held disposition after 24 h. That bound
     is now `BATCH_PROJECTION_HEAD_DEADLINE_SECONDS`.
   - Behind `BATCH_PROJECTION_BLOCKED_HEAD_DEADLINE_ENABLED` (default off),
     never-passing `ProjectionBlocked` heads on a closed allowlist take the
     same held disposition once the deadline lapses. Audio is kept and the
     reviewed redrive owns the unit.
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
