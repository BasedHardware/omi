# Authorized query-grounding producer contract

Status: P5 preregistration plus production-neutral producer and injected
owner-source kernels, 2026-08-11; concrete PostgreSQL adapters, pairing,
service composition, and activation absent

## Purpose

Produce one sensitive `memory-read-evaluation-result-v1` and its exact
`finalized-query-grounding-v1` artifact from a reader-projected input, then
stage both through the sealed atomic repository boundary. This is an isolated
shadow/offline evaluator. It does not serve a product route, choose a default,
grade truth, or authorize durable memory.

## Boundary correction discovered during seam audit

The P4 `application-read.ts` boundary is the right model for ordering:
authorization before load, reader projection before outward work, coherent
snapshot coordinates, and final revalidation before release. It is not the
right direct data plane for this evaluator. P4 deliberately projects an
external application's default generic policy view. Owner and bystander
subject classes are therefore excluded rather than retained, making the
contamination variable unobservable.

The producer must not weaken that P4 policy or add an owner exception to the
application route. Instead it uses the existing
`memories.experiments.shadow` service authorization and a separate sealed
owner-scoped evidence source. A future concrete source adapter performs the
same authorization/project/revalidation ordering over the owner-visible graph.
Only the isolated evaluator receives the result.

## Exact copied input

The existing `copied-memory-evaluation-input-v2` envelope remains the source
and replay coordinate. For `authorized_graph_snapshot`, its payload is exactly:

```text
authorized-query-evaluation-input-v1
  query text
  projection authorization digest
  reader projection digest
  projected content digest
  classifier version
  candidates[] sorted by opaque trace ref
    opaque reader-scoped trace ref
    authorized cited text
    sorted unique contributing subject classes
```

This payload is sensitive and remains inside the isolated result plane. It
contains no owner, claim, evidence, event, entity, capture-session, source, or
transcript identifier. Opaque trace refs must be unique. Subject classes are
derived by the source adapter from every exact authorized supporting claim;
they are retained by the coordinator but never sent to the model callback.

The payload parser is structural validation, not source authority. Only a
source implementation that revalidates the service context against the real
owner projection may produce it in production. No such adapter or grant is
part of this unit.

## Producer algorithm

1. Validate the sealed worker context, assignment bundle, selected
   baseline/candidate assignment, run/repeat coordinates, and an
   `authorized_graph_snapshot` source request before any dependency call.
2. Load and seal the first copied input. Reject missing, malformed, duplicate,
   unsorted, cross-coordinate, or non-opaque candidate data. An exact empty
   candidate set is retained as an explicit authorized query gap.
3. Compute the exact evaluation coordinate. Ask the isolated result repository
   first. If the result exists, load its finalized grounding artifact and
   return exact replay with zero model calls. A result without its artifact is
   an incomplete-persistence failure and never triggers regeneration.
4. When the candidate set is empty, build the deterministic qualified
   `query_gap` result and non-grounded trace locally with zero model calls. For
   a nonempty set, give the producer callback only query text, opaque trace refs, authorized
   cited text, selected registered strategy, role, and repeat. Do not expose
   subject classes or projection authorization coordinates to model behavior.
5. Accept only a closed produced/failed envelope. Build the read result through
   `buildMemoryReadEvaluationResult`; every trace-stage ref and assertion
   citation must belong to the copied candidate set.
6. After the callback's final model edge, load the same source request again.
   Require byte-identical copied-input identity, including projection,
   classifier, candidate, and source/frontier coordinates. Any unavailable,
   denied, stale, missing, or changed second load invalidates the attempt.
7. Derive grounding rows from the first sealed candidate map for exactly the
   final grounded refs. No model text, pronoun, later graph scan, or opaque-ref
   shape may create or change a class.
8. Materialize the branded evaluation result and grounding artifact, then call
   the grounding repository's single atomic `stage(result, artifact)` operation.
   Staged or exact replay succeeds; changed bytes conflict; all other outcomes
   stop with a closed code.

## Replay and pairing

This unit produces one role/repeat result. The landed paired coordinator calls
it sequentially for authority plus selected shadows, then uses the existing
verified pair repository. It never stages the generic result separately: the
grounding repository is the only success path for read evaluations because it
atomically owns both sensitive objects.

Exact replay performs source and repository reads but zero model calls. A
changed input digest selects a different evaluation coordinate. A stored result
whose grounding is absent is corruption/incomplete persistence, not permission
to call the model again.

## Landed kernel

`memory-authorized-query-grounding-producer.ts` implements the single-result
kernel with injected source, model, result-read, and atomic-grounding ports. It
strictly parses the copied payload, withholds classes and projection coordinates
from the model callback, rejects every trace-stage reference outside the copied
candidate set, revalidates after the model and before stage, revalidates stored
replay before release, and never regenerates a result whose grounding is
missing. It contains dependency/model/storage failures behind closed outcomes.

`memory-owner-query-evidence-source.ts` now supplies the injected source
authority kernel described above. It performs the owner-visible projection and
exact class derivation, but still owns no concrete PostgreSQL load, codec
secret, grant, or service composition. Its contract and landed verification are
recorded separately in `owner-query-source-contract.md`.

Verification for the landed unit: 7 focused producer tests and 35 combined
producer/repository/audit/migration tests passed; the broad platform gate passed
1,272 tests with 9,284 expectations across 175 files, plus the isolated 18-test
epoch suite. Import graph, strict TypeScript, and diff checks passed. The known
occupied fixed-port dev-server test remained excluded.

## Pre-registered acceptance tests

1. Authority capability, owner, epoch, assignment role, source kind, run id,
   repeat, and strategy contract fail before source/model/store access.
2. Payload wrappers, extras, accessors, proxies, sparse/decorated arrays,
   oversized values, non-opaque/duplicate/unsorted refs, empty/duplicate/
   unsorted classes, and raw identifier fields fail before model access.
3. The producer sees candidate text and opaque refs but never subject classes,
   projection digests, source ref, owner, or account epoch.
4. A model citation or any recall-trace stage ref outside the exact copied
   candidate set fails before staging.
5. Final source denial, disappearance, exception, epoch/frontier/projection/
   classifier/text/class change, or candidate reordering invalidates after one
   model call and performs zero stage calls.
6. Grounding rows equal exactly the final grounded refs and preserve the source
   classes. Mixed owner+bystander stays mixed; omission cannot turn it into
   bystander-only or owner-only.
7. The adapter receives the exact branded result and artifact once. A persisted
   result/artifact replay is byte-identical and performs zero model calls.
8. Result-without-grounding, changed persisted artifact, idempotency conflict,
   serialization failure, and authority/context outcomes remain distinct and
   content-safe.
9. No product route, application-read policy, `subject:*` admission, compose
   voice, bystander boundary, strategy default, grant, PostgreSQL client, or
   service composition changes.
10. Focused/full tests, import graph, strict TypeScript, migration hashes, and
    `git diff --check` pass; the known occupied fixed-port test remains isolated.

## Explicit exclusions

- no direct use or widening of the P4 external-application generic projection;
- no concrete graph/source/PostgreSQL adapter or worker grant;
- no paired/repeat scheduling in this first unit;
- no model choice, prompt tuning, cache, route, Listen mapping, or deployment;
- no truth grade or promotion decision;
- no David-gated bystander, `subject:*`, or compose-voice change.
