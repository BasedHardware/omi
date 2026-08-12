# Durable memory work execution policy contract

Status: P3 production-neutral contract, 2026-08-11

## Purpose

Lease and retry timing must be a persisted, versioned part of the accepted
execution contract. A worker may not guess these values from an environment
variable, request parameter, process default, or provider behavior.

This unit defines that policy without choosing or activating a production
value. A later acceptance migration binds one registered policy to each
accepted work item before the PostgreSQL lease adapter is allowed to run.

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

The future database adapter loads the policy named by accepted work under the
same locked account/epoch/strategy coordinates. It obtains event time from the
database, calculates lease expiry and next eligibility from this policy, and
persists the resulting pure state transition atomically. The failed attempt is
1-based; its matching retry delay is returned, while the final attempt returns
no delay and becomes dead work.

## Explicit exclusions

- no production timing value or default is selected;
- no PostgreSQL table, grant, lease operation, worker, scheduler, route, model,
  credential, or runtime composition is added;
- no subject, identity, bystander/privacy, compose-voice, or data-disposition
  behavior changes;
- no claim that accepted work is yet bound to this policy in persistence.

## Acceptance tests

1. Every work kind, strategy digest, attempt budget, lease duration, and retry
   delay changes the policy digest.
2. Attempt and timing bounds are exact; schedule length is exactly
   `max_attempts - 1`.
3. Parsing recomputes the digest and rejects extras, proxies, accessors,
   malformed tokens, and forged digests.
4. Retry lookup is total only for attempts 1 through the declared budget and
   returns null exactly at exhaustion.
5. Focused/full tests, import lint, strict changed-source TypeScript, and diff
   checks pass before the unit is recorded.
