# Offline replay coordinator contract

Status: P5 pre-registration, 2026-08-11

## Purpose

Run one already-assigned authority strategy and its selected shadow strategies
sequentially over one immutable copied input, with explicit repeats. Reuse
committed isolated results after restart, record baseline/candidate pairs, and
return only content-safe evaluation coordinates. This coordinator cannot append
memory authority, build product projections, serve recall, answer, grade truth,
or promote a strategy.

## Copied input

The authorized evaluation evidence-source facade loads one exact source under a
sealed shadow context, detaches and deeply freezes it with the existing
normalized-result limits, and brands the result. The v2 digest binds owner,
account epoch, source kind/reference digest, frontier, and payload. The
coordinator accepts only that branded value and rechecks owner/epoch. Raw copied
content is passed only to the injected producer and is never returned in the
run outcome, pair record, telemetry, or error.

## Execution

One run binds an already minted deterministic assignment bundle, opaque
evaluation-run id, copied input, and an explicit repeat count. The bundle must
contain at least one selected shadow. For every repeat the coordinator:

1. loads the authority baseline from the isolated result repository;
2. calls the injected producer only on a true miss and stages the normalized
   result before proceeding;
3. repeats the same load-or-produce step for every selected shadow; and
4. records one exact baseline/candidate pair per selected shadow.

All producer calls are awaited sequentially. The coordinator never uses
`Promise.all` or owns an API key, concurrency pool, timer, retry loop, cache,
database, filesystem, environment variable, route, or logger. Resource-specific
serialization and provider retries remain the injected producer's responsibility.

Producer outcomes are exact and closed: produced normalized result coordinates,
or one existing durable-work error code. A thrown producer becomes the closed
`dependency_unavailable` failure. Result-contract mismatch stops as
`invalid_result`. Repository retry/context/conflict outcomes remain distinct.
No provider text or exception message is retained.

## Replay and output

A committed result is always loaded before production. Restart after any staged
baseline or candidate therefore reuses it without another model call. Pair
recording is immutable and replayable. The completed outcome contains only
verified pair records and integer counts for producer calls and reused results.
A stopped outcome contains a closed stop/failure code, counts, and already
completed verified pairs; it never fabricates a pair for missing work.

The coordinator records comparisons but does not calculate McNemar, contamination,
quality, or truth. Those remain downstream tools, with blind human grading where
David-specific truth cannot be machine-judged.

## Pre-registered acceptance tests

1. Two repeats over one authority plus two selected shadows produce six model
   calls, four exact pairs, and never overlap producer calls.
2. Restart with staged results makes zero model calls and replays identical pair
   identities; a partially staged run calls only the missing strategy/repeats.
3. Each producer sees the same frozen copied payload and the exact registered
   strategy/role/repeat coordinate. Later caller mutation cannot change it.
4. No selected shadow, forged copied input, forged assignment, excessive repeat,
   result-contract mismatch, hostile producer outcome, or mismatched repository
   replay can become a completed pair.
5. Producer failure, thrown producer, storage retry, authorization/context stop,
   and idempotency conflict remain closed and distinct. Provider/error text is
   absent from every returned outcome.
6. Completed and stopped serialized outcomes contain no copied payload,
   normalized result, raw frontier, response digest, query, answer, transcript,
   prompt, or error text.
7. Focused/full tests, contract tests, import lint, strict changed-file
   TypeScript filter, bundle parse/build, and `git diff --check` pass before the
   unit is recorded.

## Explicit exclusions

- No production event/graph loader implementation, PostgreSQL adapter, worker,
  scheduler, model composition, route, runtime grant, telemetry sink, or
  experimental product projection is added.
- No statistical test, contamination audit, blind sheet, human grade, promotion
  policy, cohort, deployment, or production default is added.
- Subject tiers, bystander/privacy, identity authority, compose voice, and data
  disposition remain unchanged and David-gated.
