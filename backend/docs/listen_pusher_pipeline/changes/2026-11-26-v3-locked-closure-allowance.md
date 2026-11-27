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

**Per-owner ceiling.** While pending remains, a pending-seeded request runs up to 3 inline passes, and the owner is
woken each minute. Uncapped, one listed owner could therefore spend up to 3 x 30k reads a minute (about 130M a day).
`CONVERSATIONS_V3_LOCKED_DAILY_PASSES` (default 48) caps the committed allowance passes per owner per UTC day. The
final batch counts them on the builder lease. Past the cap, the owner's passes that day load with the origin bound
and park as before. The bound is about 1.44M reads for allowance passes plus up to about 0.15M for parked retries:
about 1.6M reads per listed owner per day.

**Lease.** The caller renews the pass's lease (`builder`, or `backfill-builder` for a derive pass) once before the
commit. The commit now renews it before every later batch, so a 6-batch commit cannot outlive the 240 s lease after
writing a prefix. This applies to every owner and costs one renewal transaction per later batch.
`CONVERSATIONS_V3_COMMIT_LEASE_RENEWAL=off` restores the single renewal.

A failed renewal stops the commit after the committed prefix and leaves pending owed:
- `lease_lost` makes the pass `raced`, with a wake the next minute;
- exhausted renewal contention is the reconcile 409 retry.

The emulator fixture shows a 6-batch commit holding its lease while the commit clock advances 200 s per batch.
Without renewal, the same commit loses the lease after two batches.

**Builder passes only.** The allowance applies only to builder passes (lease `builder`), so the batch cap and the
daily cap apply wherever it does. Derive (`load_derive`, partition budget) and live re-derive (`load_live_rederive`,
`DERIVED_LIMIT`) keep today's bounds for a listed owner; a heavy derive is planned as its own run.

**Seed retry.** A pass whose commit would exceed the batch cap raises `LockedBatchCap` before any transaction. The
builder re-enters below the seeds it used (32, 8, 1), as a load-time overflow does, and parks only at one seed. The
ceiling only falls, so a pass re-enters at most twice. Each retry repeats the load and the outline.

**Runtimes.** `store.load()` runs on every runtime that runs builder passes: the on-open builder on `backend` and
`backend-integration`, and builder tasks on `backend-sync` and `backend-sync-backfill`. `pusher` and
`backend-listen` only mark pending and enqueue (`triggers.changed`); they never load a closure. The allowlist, sizes,
batch cap and daily passes must agree on the four loaders, and the activation manifest
(`deploy/activation/conversations-v3.yaml`, `v3-locked-closure-*`) requires one value. Lease renewal is decided per
commit, so it is not in the manifest.

**Owner list in Secret Manager.** This repository is public, so owner tags never go in Git. The four loaders bind
`CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS` to the Secret Manager secret of the same name, `version: latest`. Release
provisions it, with first version `none` and `secretAccessor` for `backend-runtime@`, before this change merges: a
Cloud Run revision bound to a missing secret does not start. Admitting an owner is a new secret version, then a new
revision on the four loaders. The four size keys stay literal in the prod overlay, at the code defaults.

**Refinement.** Serving backend-sync runs 300/300 timing, so the live planner never offers refinement. Under
custom timing it is offered, one merge of 2 to 8 donors per pass, and the fixture keeps custody either way.

**Rollout.** Off by default. List one parked owner whose closure is at most 1,200 rows, then five (at most about 8M
reads a day at the cap), then all parked owners. Listing more than about six owners, `*`, or any step that expects
more than 10M reads a day needs a yes from the Firestore cost owner (SCA-2173). Roll back with a secret version of `none` and a revision roll. A follow-up should fence unchanged locked rows
once, not in every batch, which would cut commit reads from about 12k to about 3k per heavy pass.
