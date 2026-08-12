# Durable memory work execution policy contract

Status: P3 persisted acceptance binding, 2026-08-11

## Purpose

Lease and retry timing must be a persisted, versioned part of the accepted
execution contract. A worker may not guess these values from an environment
variable, request parameter, process default, or provider behavior.

This unit defines that policy without choosing or activating a production
value. Migration 0015 and the acceptance adapter now bind one registered
policy to each new accepted work item before the PostgreSQL lease adapter is
allowed to run. Historical qualification rows remain explicitly
legacy/unbound; PostgreSQL enforces the new check and account-scoped foreign
key on every later insert without inventing a policy for old data.

## Exact policy

One policy binds:

- one closed durable work kind and exact strategy execution-contract digest;
- a bounded attempt budget from 1 through 100;
- an explicit lease duration from 1 through 3,600 seconds; and
- exactly one explicit retry delay for every non-terminal failed attempt, each
  from 1 through 86,400 seconds.

The policy digest covers every field. There is no default lease, retry delay,
backoff formula, jitter, or environment override. A single-attempt policy has
an explicitly empty retry schedule.

## Worker use

The future lease database adapter loads the policy named by accepted work under the
same locked account/epoch/strategy coordinates. It obtains event time from the
database, calculates lease expiry and next eligibility from this policy, and
persists the resulting pure state transition atomically. The failed attempt is
1-based; its matching retry delay is returned, while the final attempt returns
no delay and becomes dead work.

## Explicit exclusions

- no production timing value or default is selected;
- one append-only PostgreSQL policy table and its acceptance foreign key are
  added; the application has only SELECT and INSERT on that table;
- no lease operation, worker, scheduler, route, model, credential, or runtime
  composition is added;
- no subject, identity, bystander/privacy, compose-voice, or data-disposition
  behavior changes;
- no production policy values are selected and no historical rows are
  backfilled with guessed timing.

## Acceptance tests

1. Every work kind, strategy digest, attempt budget, lease duration, and retry
   delay changes the policy digest.
2. Attempt and timing bounds are exact; schedule length is exactly
   `max_attempts - 1`.
3. Parsing recomputes the digest and rejects extras, proxies, accessors,
   malformed tokens, and forged digests.
4. Retry lookup is total only for attempts 1 through the declared budget and
   returns null exactly at exhaustion.
5. Acceptance rejects a policy whose work kind, strategy contract, or attempt
   budget differs from the exact pending work and includes the full policy in
   its idempotency digest.
6. PostgreSQL persists and replays the immutable policy under the application
   role, rejects same-id policy drift, denies mutation, and rolls it back with
   the accepted work on failure.
7. Focused/full tests, contract QA, import lint, real PostgreSQL Bun/Node
   parity, and diff checks pass before the unit is recorded.
