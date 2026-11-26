# v3 locked-closure allowance for heavy owners (SCA-2918)

On 2026-11-26, 21 owners were parked on `v3_derived_budget` and still overflowed with one pending seed. One long
recording (155 to 229 minutes) owned 300 to 1,002 locked one-line windows (median 8 s). The old moving cap cut
left them, and `a0aa6ee` fixed that cut. A replan loads every row that owns the recording's lines, so one seed's
closure held 1,026 to 1,994 rows against `DERIVED_LIMIT` 1,024.

For owners listed in `CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS`, `load()` now gives locked claimants extra room
(2,048 rows, 8 MiB of decoded speech). Locked claimants are the rows the planner already keeps fixed: not
`in_progress`, not `v3_unlocked`, both timestamps set, and not a refined transferred row. Rewritable rows keep
`DERIVED_LIMIT` and `DERIVED_BYTES`. The list is empty by default. See the
[conversations v3 contract](../../listen_pusher_pipeline.mdx).

**Cost.** Every projection batch rereads the whole loaded closure to fence revisions. A heavy pass costs about
batches x closure reads. The emulator fixture is
`tests/integration/test_conversations_v3_locked_closure_cost_firestore.py`, which runs the real load, planner
and commit. It measured:

- 6.5k reads per steady pass for a 1,137-row closure (3 batches);
- 15.0k reads for 1,976 rows (5 batches);
- 21.9k reads for 2,276 rows (6 batches).

Steady writes are under 40 per pass. A first contact that restamps every fragment writes at most about twice
the closure. The commit is capped at `CONVERSATIONS_V3_LOCKED_MAX_BATCHES` (6) batches, so the ceiling is about
24k commit reads plus about 1.6 reads per row at load: about 30k reads per pass. A closure past the cap parks
before any transaction, after its load (about 3.6k reads in the fixture) and the outline call. The 8 MiB byte
allowance keeps the batch count from being driven by stored speech.

**Lease.** The caller renews the builder lease once before the commit. The commit now renews it before every
later batch, so a 6-batch commit cannot outlive the 240 s lease after writing a prefix. This applies to every
owner and costs one renewal transaction per later batch. The fixture shows a 6-batch commit holding a 5 s
lease. Without renewal, the same commit loses the lease after two batches and keeps pending owed.

**Refinement.** Serving backend-sync runs 300/300 timing, so the live planner never offers refinement. Under
custom timing it is offered, one merge of 2 to 8 donors per pass, and the fixture keeps custody either way.

**Rollout.** Off by default. List one parked owner whose closure is at most 1,200 rows, then five, then all
parked owners. Listing `*`, or any step that expects more than 10M reads per day, needs a yes from the
Firestore cost owner (SCA-2173). Roll back by emptying the list. A follow-up should fence unchanged locked rows
once, not in every batch, which would cut commit reads from about 12k to about 3k per heavy pass.
