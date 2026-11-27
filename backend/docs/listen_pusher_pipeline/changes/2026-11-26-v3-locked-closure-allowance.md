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
before any transaction, after its load (about 3.6k reads in the fixture) and the outline call. A closure with
more rows than six batches could ever commit (6 x (449 - sources)) stops at load instead, at the first row past
that bound (or by id, before reading, when one round's claims name them all). It never plans, calls the outline or
reaches the commit. In the fixture, at a cap of 5, the 2,276-row closure parked after 4 charged loads of about 2.6k
reads each; a closure split into more batches by prepared bytes, which the load cannot see, still parks at the
commit's cap before any transaction. The clamp counts only sources and the lease: removals, absorption redirects (up
to 16 writes), retire, retired and settle writes, and pointer splits can also push a closure past the cap, which
stays the backstop. Each attempt is charged to the pass's own builder lease token, so a stale pass charges nothing
and loads with the origin bound. The 8 MiB byte
allowance keeps the batch count from being driven by stored speech.

**Per-owner ceiling.** While pending remains, a pending-seeded request runs up to 3 inline passes, and the owner is
woken each minute. Uncapped, one listed owner could therefore spend up to 3 x 30k reads a minute (about 130M a day).
`CONVERSATIONS_V3_LOCKED_DAILY_PASSES` (default 20) is a per-owner budget of allowance **attempts** per UTC day, not
commits. Every builder load of a listed owner charges one (`v3_locked_day`, `v3_locked_passes` on the builder lease) in
its own transaction under the held lease, before the load reads anything. So a capped attempt and each smaller-page
retry, a commit interrupted after a committed prefix, a smaller page that fits the origin bound, and a parked pass are
all charged. A spent day, a lease that is not held, or a charge that cannot be written (contention exhausted, a
Firestore error) loads with the origin bound, so the owner parks as before. The charge never adds a failure of its
own.

The ceiling is derived from that counter as attempts x the most one attempt can read:
- the charge: 1 read and 1 write, at most three tries;
- the load: at most about 5.9k reads. It admits at most 6 x (449 - sources) rows, what six batches can commit
  (2,694 with no sources), and fetches at most twice that many derived documents plus one sentinel (5,389) across the unlocked
  page, the claim reads and every interval query, counting repeats; plus up to 400 sources and the seeds;
- the commit: up to about 24k reads; each batch runs at most three transactions under main's contention retry, so
  up to about 72k;
- renewals: a few reads.

That is about 78k per attempt, and 20 x 78k, **about 1.6M reads per listed owner per day**. The measured attempts read
6.5k to 22k. Parked retries after the budget is spent run at the origin bound, at today's cost for any parked owner.

An owner can spend its 20 attempts early in the UTC day; it then runs at the origin bound, parking as before, until
00:00Z. The readback watches for that (`v3_locked_passes` at 20 with pending still owed).

**Kill switches.** An empty list, or `CONVERSATIONS_V3_LOCKED_DERIVED_ALLOWANCE`, `_DERIVED_BYTES`, `_MAX_BATCHES` or
`_DAILY_PASSES` set to `0`, restores the origin bound; a negative or unparseable value keeps the default.

**Lease.** The caller renews the pass's lease (`builder`, or `backfill-builder` for a derive pass) once before the
commit. The commit now renews it before every later batch, so a 6-batch commit cannot outlive the 240 s lease after
writing a prefix. This applies to every owner and costs one renewal transaction per later batch.
`CONVERSATIONS_V3_COMMIT_LEASE_RENEWAL=off` restores the single renewal.

A failed renewal stops the commit after the batches already written. That committed prefix stays: it is existing,
tolerated behaviour for any multi-batch commit, not something this change removes. Pending stays owed, and the next
pass completes the closure:
- `lease_lost` makes the pass `raced`, with a wake the next minute;
- exhausted renewal contention is the reconcile 409 retry.

The emulator fixture shows a 6-batch commit holding its lease while the commit clock advances 200 s per batch.
Without renewal, the same commit loses the lease after two batches.

**Builder passes only.** The allowance applies only to builder passes (lease `builder`), so the batch cap and the
daily cap apply wherever it does. Derive (`load_derive`, partition budget) and live re-derive (`load_live_rederive`,
`DERIVED_LIMIT`) keep today's bounds for a listed owner; a heavy derive is planned as its own run.

**Seed retry.** A pass whose commit would exceed the batch cap raises `LockedBatchCap` before any transaction. The
builder re-enters down the same ladder a load-time overflow uses, pending and unlocked seeds alike: 32 pending + 8
unlocked, 8 + 8, 1 + 1, then one seed of either kind (the single lanes). The step comes from the seeds the pass read,
and it only moves down, so a pass re-enters at most three times and parks only at one seed. Each retry repeats the
load and the outline.

**Runtimes.** `store.load()` runs on every runtime that runs builder passes: the on-open builder on `backend` and
`backend-integration`, and builder tasks on `backend-sync` and `backend-sync-backfill`. `pusher` and
`backend-listen` only mark pending and enqueue (`triggers.changed`); they never load a closure. The allowlist, sizes,
batch cap and daily passes must agree on the four loaders, and the activation manifest
(`deploy/activation/conversations-v3.yaml`, `v3-locked-closure-*`) requires one value. Lease renewal is decided per
commit, so it is not in the manifest.

**Owner list: unbound in this change.** This repository is public, so owner tags never go in Git.
`CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS` ships unbound on all four loaders; its code default is empty, so nobody is
admitted. Admission needs a later, separate change, which needs an operator with Secret Manager and IAM rights:
1. provision the secret `CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS` (version 1 `none`, `secretAccessor` for
   `backend-runtime@`);
2. then a small PR binds it on the four loaders and adds `v3-locked-closure-owners` to the activation manifest;
3. then roll.

Each owner after that is a new secret version and a roll; see the runbook. The four numeric keys are literal in the
prod overlay, at the code defaults.

**Refinement.** Serving backend-sync runs 300/300 timing, so the live planner never offers refinement. Under
custom timing it is offered, one merge of 2 to 8 donors per pass, and the fixture keeps custody either way.

**Rollout.** Off by default. List one parked owner whose closure is at most 1,200 rows, then five (at most about 8M
reads a day at the cap), then all parked owners. Listing more than about six owners, `*`, or any step that expects
more than 10M reads a day needs a yes from the Firestore cost owner (SCA-2173). Roll back with a secret version of `none` and a revision roll (or, before the binding change, there is nothing to roll back). A follow-up should fence unchanged locked rows
once, not in every batch, which would cut commit reads from about 12k to about 3k per heavy pass.
