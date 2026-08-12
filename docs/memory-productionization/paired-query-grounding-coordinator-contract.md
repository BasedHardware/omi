# Paired query-grounding coordinator contract

Status: P5 production-neutral coordinator and composition root plus concrete
route-free PostgreSQL query/result/grounding adapters, 2026-08-12; one-shot
runtime, model adapter, and activation absent

## Purpose

Run one already-assigned read authority strategy and every selected read shadow
through the finalized-grounding producer over explicit repeats, then persist
verified baseline/candidate pair metadata. This is the production-neutral
bridge from exact authorized query results to the existing export, repeat-noise,
contamination, statistics, and blind-sheet tools. It cannot serve a product
answer, grade truth, promote a strategy, or write memory authority.

The generic offline replay coordinator is not reused mechanically. It stages a
normalized result without a finalized grounding artifact. Query evaluation may
succeed only through `MemoryAuthorizedQueryGroundingProducer`, whose one atomic
stage owns the sensitive result and its exact grounding artifact.

## Input and authority

One run binds:

- a sealed `memories.experiments.shadow` context;
- one minted retrieval or composition assignment bundle with exactly one
  authority assignment and at least one selected shadow;
- one opaque evaluation-run id;
- one exact `authorized_graph_snapshot` source request; and
- an explicit repeat count from 1 through 20.

The coordinator validates the complete request before its first dependency
call. It accepts no copied payload, model, prompt, graph, answer, grade, secret,
database, filesystem, environment, scheduler, or retry-loop parameter.

## Sequential execution

For each repeat ordinal in ascending order:

1. invoke the finalized-grounding producer for the authority assignment;
2. await completion before invoking any shadow;
3. invoke selected shadows in their minted bundle order, one at a time;
4. pair each completed shadow only with that repeat's completed authority
   result using `pairMemoryEvaluationResults`; and
5. persist the verified pair through the existing isolated result repository
   before moving to the next shadow.

There is no `Promise.all`, fan-out, credential selection, concurrency pool, or
producer retry. One run therefore consumes at most one model edge at a time.
Model-call counts are summed from producer receipts: replay and an explicit
empty authorized projection may each consume zero calls.

Baseline and candidate attempts independently revalidate their exact source
after their final model edge. If the input changes between arms, pairing fails
closed because the verified results have different input/frontier coordinates.
The coordinator never relabels such results as a comparison.

## Failure, replay, and output

A producer stop ends the run with its closed producer stop/failure code and all
already recorded pairs. A thrown producer becomes a closed
`dependency_unavailable` stop. Pair construction failure becomes
`invalid_result`. Repository retry, authorization/context denial, and
idempotency conflict remain distinct closed stops. The sealed repository throws
for both an invalid adapter envelope and an adapter exception; the coordinator
therefore maps both to one honest `pair_storage_unavailable` outcome instead of
inspecting raw error text. No raw exception or provider content survives.

Restart invokes the producer again for each coordinate, but the producer loads
the exact staged result plus grounding first and revalidates the source before
returning zero-call replay. Pair persistence is immutable and replayable. A
stopped run never fabricates a pair for an incomplete arm.

The persisted verified pair is protected isolated metadata and includes its
account key. It is never returned by this coordinator. Only after successful
pair persistence does the coordinator derive a content-safe receipt containing
the pair version, opaque pair ref/digest, and repeat ordinal. A future isolated
pair-read boundary may load the full verified rows for the existing export.

Completed and stopped outputs contain only those opaque pair receipts, integer
observed-model-call/staged/replayed-result and recorded/replayed-pair counts,
and closed stop codes. On a stopped run, `observed_model_calls` counts only
completed producer receipts; a thrown dependency cannot be used to claim an
unknown total. Outputs contain no
query, answer, assertion, citation, trace ref, subject class, graph/source
coordinate, copied input, normalized result, response digest, prompt, model,
owner, credential, grant, or error text.

Repeat ordinal 0 remains the sole primary sample downstream. The coordinator
records later repeats for read-side disagreement only and computes no statistic.

## Pre-registered acceptance tests

1. Two repeats over one authority plus two shadows produce six sequential
   completed attempts, four exact pair receipts, peak producer concurrency one, and the
   order baseline/A/B then baseline/A/B.
2. Exact restart returns the same pair refs with zero model calls and six replayed
   results. A prefix restart reuses completed arms/pairs and invokes only the
   missing work.
3. Empty authorized projections complete every arm and pair with zero model
   calls; no empty row requires a human grade click downstream.
4. Source drift between baseline and candidate cannot pair. Final or replay
   revalidation failure stops without recording that pair.
5. Wrong capability/owner/work kind, no shadow, malformed run/source/repeat,
   forged assignment, accessor/proxy/decorated input, and dependency accessors
   fail before producer or repository access.
6. Producer stop/throw, pair mismatch, repository retry, authorization denial,
   idempotency conflict, and pair-storage-unavailable remain closed and
   distinguishable. Malformed adapter output and pair-write throw share the
   last class by design. Already recorded pairs remain exact.
7. Serialized completed/stopped outcomes contain none of the sensitive fields
   named above, including the account key present in the persisted pair. Pair
   receipt order and identity are stable under replay.
8. Later repeats are present with exact ordinals but the existing statistics
   and contamination gates still use repeat 0 as primary N.
9. Focused and broad tests, import graph, migration hashes, and
   `git diff --check` pass before the unit is recorded.

## Pre-registered success criterion

The slice lands only if all acceptance tests pass and a two-repeat/two-shadow
hermetic run records four verified pairs with peak concurrency one, while exact
restart performs zero model calls and returns byte-identical opaque pair refs.
This proves orchestration and replay safety only. It is not answer-quality,
contamination, truth, or production-read evidence.

## Landed kernel

`memory-paired-query-grounding-coordinator.ts` implements the sealed sequential
bridge. It accepts only the branded atomic grounding producer and isolated pair
repository, validates the complete run before dependency access, invokes
baseline then selected shadows for each explicit repeat, pairs only verified
same-input results, persists each pair before advancing, and returns only opaque
pair receipts plus closed counters/outcomes. Full verified pair rows remain
inside isolated storage.

The pre-registered two-repeat/two-shadow run completed six attempts, recorded
four pairs, and held peak producer concurrency at one. Exact restart returned
the same four opaque pair refs with zero model calls and six replayed results.
Empty authorized projections also recorded all four pairs with zero model calls.

Verification: 8 focused coordinator tests passed with 51 expectations; the
combined coordinator/producer/result/grounding suite passed 24 tests with 124
expectations. The broad platform gate passed 1,289 tests with 9,372 expectations
across 177 files; the isolated epoch suite passed 18 tests with 141
expectations; migration checks passed 19 tests with 1,192 expectations. Import
graph and diff checks passed. The first epoch run was deliberately attempted in
parallel with the broad gate and hit its known cleanup timeout; the required
isolated rerun passed. The occupied fixed-port dev-server test remained
excluded.

## Explicit exclusions

- no concrete codec secret, model adapter, API-key pool, worker scheduler,
  one-shot PostgreSQL runtime, route, activated grant, cache, Listen mapping,
  deployment, or product read;
- no McNemar or contamination verdict inside the coordinator;
- no blind sheet or request for David's grading until fresh machine gates pass;
- no `subject:*`, bystander/privacy, identity authority, compose voice, data
  disposition, model default, promotion, cohort, or production decision.
