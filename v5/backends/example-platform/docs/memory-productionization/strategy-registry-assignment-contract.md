# Memory strategy registry and assignment contract

Status: P5 pre-registration, 2026-08-11

## Purpose

Make model and algorithm evolution an explicit production capability without
letting an experiment silently become memory authority. Every accepted durable
work item must be tied to one immutable, complete execution strategy selected
by a deterministic assignment policy before processing starts.

This is an internal experiment plane. Assignment, strategy, cohort, storage,
or backend identity never appears in the client-facing memory API.

## Strategy identity

A registered strategy is immutable and account-scoped. It binds one durable
work kind to the complete set of coordinates that can change its result:

- strategy, model, prompt, policy, code, schema, tokenizer, and tool versions;
- result-contract version; and
- speaker-frame and boundary versions, using the literal `none` when a
  coordinate is inapplicable.

The canonical execution-contract digest is the digest of that complete
definition. A caller cannot supply an unrelated digest under the same strategy
id. A changed coordinate creates a different immutable definition; it never
rewrites accepted work or historical results.

## Assignment policy

One immutable policy applies to exactly one work kind and declares its stable
assignment unit (`account`, `session`, or `work`). It names:

- exactly one authority strategy;
- zero or more distinct shadow candidates with an allocation in basis points;
  and
- a key version for the injected assignment secret.

The assignment function is pure apart from its injected secret bytes. It uses
keyed digests over the owner, declared unit, policy, and candidate strategy, so
the same inputs select the same shadows while persisted rows contain no raw
account/session/work unit and no secret. Policy order is canonical; reordering
shadow candidates cannot change assignment.

Every assignment bundle always contains its one authority selection. Each
shadow candidate is independently included when its deterministic bucket is
below the declared allocation. A policy or key-version change produces a new
bundle identity and never mutates the earlier assignment.

## Authority separation

The authoritative durable-work acceptance port accepts only a bundle minted by
the deterministic assigner and requires all of the following:

- owner and work kind equal the accepted job;
- the bundle's authority execution digest equals the job's execution-contract
  digest; and
- the complete assignment participates in the acceptance request digest.

Only the authority entry is referenced by an authoritative work acceptance.
Shadow entries are persisted in a separate normalized relation and have no
foreign-key path into the authoritative work queue, graph append, product
projection, or answer path. A shadow candidate can become authority only through
a new reviewed assignment-policy version. Cohort or real-user activation remains
a David gate.

Before either staged-result lookup or a model call, the production-neutral work
runner resolves the exact registered authority strategy and compares its work
kind and execution digest with the leased job. It passes that frozen definition
to the producer and materializer and rejects a mismatched result-contract
version. Thus an accepted digest cannot be paired with a caller-selected model
or parser by accident.

## Persistent shape

An inert checksummed migration adds account-scoped immutable tables for strategy
definitions, assignment policies, normalized policy shadow allocations,
assignment bundles, and selected shadow entries. It extends accepted durable
work with an exact foreign key to the bundle's authority strategy and execution
digest. The migration grants nobody and activates no registry, selector, worker,
route, model, database client, or cohort.

## Pre-registered acceptance tests

1. A one-byte change to any strategy coordinate changes the execution-contract
   digest; reordered object fields do not. Wrong work kind, owner, unknown
   strategy, duplicate id, or conflicting immutable strategy id fails closed.
2. Same secret, policy, owner, and unit produce byte-identical assignments.
   Candidate ordering does not matter; unit, policy, allocation, key version, or
   secret changes assignment identity.
3. Zero basis points selects no shadow; 10,000 selects it deterministically.
   Authority is always present exactly once and can never also be a shadow.
4. Persisted assignment data contains only opaque unit digests, buckets, counts,
   version coordinates, and stable ids. It contains no raw unit ref, secret,
   prompt, transcript, evidence, query, answer, or model output.
5. Durable-work acceptance rejects an unbranded/forged assignment, wrong owner,
   work kind, authority strategy, execution digest, or changed request digest
   before the adapter is called.
6. The work runner resolves the exact authority definition before model or
   staged-result access, rejects wrong work/digest/result-contract coordinates,
   and passes the same frozen definition to production and materialization.
7. Migration bytes are checksummed. Static tests prove every key and foreign key
   is account-scoped, accepted work references only the authority entry, shadow
   rows have no authority/write relation, and no grants or runtime are added.
8. Focused/full tests, contract QA, import lint, strict changed-file TypeScript
   filter, bundle parse/build, and `git diff --check` pass before recording the
   unit.

## Explicit exclusions

- No shadow model execution, shadow-result store, replay evaluator, cohort
  activation, promotion automation, or runtime composition is implemented here.
- No subject-tier, bystander/privacy, identity-authority, compose-voice, data
  disposition, blind-grading, or production rollout decision changes.
- No PostgreSQL version, client, container runtime, worker role, application
  grant, production credential, route, deployment, or traffic change is made.
