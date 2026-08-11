# Owner-projected query source contract

Status: P5 preregistration, 2026-08-11; implementation and activation absent

## Purpose

Create the exact `authorized-query-evaluation-input-v1` payload consumed by the
inert query-grounding producer. The adapter turns one live, owner-scoped graph
load into a liveness-filtered, policy-classified, reader-scoped candidate set.
It is the authority for source-to-class derivation; the model and artifact
materializer are not.

## Trust and policy boundary

The adapter receives only a sealed `memories.experiments.shadow` service
context. A future concrete loader must revalidate that context against the
database inside each load. This unit remains injected and defines no database,
grant, route, or worker composition.

The adapter uses the canonical `genericPolicyClassifier` and an owner request
context. Owner visibility is existing retrieval behavior, not a new
`subject:*` admission rule. The external P4 application projection remains
generic-only and unchanged.

## Load contract

The injected loader returns one exact plain record:

```text
found
  owner account id + account epoch
  requested source ref + input frontier
  query text + account timezone
  durable graph snapshot
```

Closed not-found, retryable, stale-context, and authorization-denied outcomes
pass through. Exceptions are contained by the existing evidence-source facade.

The adapter detaches the graph through the canonical plain-JSON boundary before
inspection, rejects every nested cross-owner coordinate, and calls
`projectTreeInputSnapshot` with the owner request context, canonical classifier,
timezone, and exact graph generation. Projection diagnostics fail the load;
missing evidence/event closure never becomes a partial candidate set.

## Candidate derivation

1. Consider only evidence spans actually cited by at least one projected live
   claim. Ignore unreferenced evidence.
2. Require a nonempty authorized excerpt and exact Evidence -> Event -> Capture
   closure already proven by the projection.
3. For each evidence span, collect the subject class of every projected claim
   citing it. Sort and deduplicate; never infer from text, pronouns, speaker
   rendering, entity labels, or a later graph.
4. Build the trace seed from the version, reader projection digest, exact
   evidence/event/capture/range coordinate, and sorted supporting claim
   revisions. Pass that seed to one injected reader-scoped trace codec.
5. Require a `tr1_` output, reject raw-coordinate leakage and collisions, then
   sort candidates by trace ref. The payload stores only trace ref, excerpt, and
   classes; raw graph coordinates do not leave the adapter.
6. Enforce fixed candidate and total-text budgets by failing the load, never by
   silently truncating a reader's graph and claiming complete input.

The projection authorization digest is derived from the complete sealed worker
authorization coordinate. The reader projection and projected-content digests
come from the canonical owner projection. Classifier version is explicit. All
are committed by `copied-memory-evaluation-input-v2`, so the producer's second
load detects any authorization, graph, liveness, text, class, or codec-relevant
drift.

## Pre-registered acceptance tests

1. Wrong capability/owner/epoch/source kind, malformed loader envelopes, graph
   proxies/accessors/classes/aliases, nested cross-owner records, and projection
   diagnostics fail before codec/output.
2. Purged, forgotten, tombstoned, superseded, non-live, or unreferenced evidence
   never becomes a candidate; active evidence cited by a live claim does.
3. One evidence cited by owner and bystander claims produces sorted
   `bystander,owner`; evidence cited only by bystander produces `bystander`.
4. No text, entity, speaker, or handle changes a subject class. Only the
   canonical classifier over exact claim/evidence labels contributes.
5. Codec input commits the exact reader/evidence/support closure. Raw,
   malformed, duplicate, or colliding outputs fail. Different reader projection
   digests produce different refs under the real codec.
6. Candidate order is independent of graph/claim/evidence array order. The
   copied input digest is byte-stable for equivalent permutations.
7. Any query, graph generation, live head, evidence excerpt/range, supporting
   claim, class, authorization coordinate, timezone, or classifier change
   changes the copied input digest and is caught by producer revalidation.
8. Candidate-count or total-text budget overflow fails closed and never emits a
   truncated `found` result.
9. The produced payload contains no owner, claim, evidence, event, entity,
   capture-session, source, transcript, or graph identifier field.
10. No route, PostgreSQL client, grant, service composition, model, cache,
    `subject:*` admission, bystander boundary, compose voice, Listen mapping,
    default, or truth grading changes.

## Explicit exclusions

- no lexical/vector/model candidate ranking in this first source adapter;
- no accepted/STM overlay until those inputs have the same projection closure;
- no concrete PostgreSQL loader or production codec secret;
- no product read or external-application policy widening;
- no inference that a source-derived class is David-specific truth.
