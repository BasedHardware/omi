# Finalized query grounding and provenance contract

Status: P5 contract plus legacy compatibility gate, 2026-08-11; no authorized
producer, persistence adapter, route, or runtime activation landed

## Purpose

Create the exact sensitive artifact that joins one finalized query answer to
the authorized claims and policy classes that grounded each assertion. The
existing zero-model contamination audit may consume only this artifact through
its sealed source facade. It may never reconstruct provenance from answer text,
opaque-reference shape, a later graph snapshot, or an unprojected store scan.

This is evaluation infrastructure first. It does not approve query-bearing
product recall, compose voice, `subject:*` admission, bystander policy, or a
strategy default.

## Current seam and why an adapter cannot be wired mechanically

The canonical tree has the pieces, but no producer currently owns all of them:

- `memory-read-evaluation-result-v1` requires exact ordered assertions, grounded
  `tr1_` citations, a branded recall trace, and an authorized copied input;
- the contamination audit requires one total subject-class row per grounded
  trace reference;
- `core/retrieve/agentic.ts` is query-bearing dogfood, not an application read:
  it returns raw evidence identifiers, now retains the final entailed assertion
  manifest after salvage, but does not require a branded
  application-authorized projected snapshot and performs no final
  authorization/projection revalidation after model calls;
- `core/retrieve/application-read.ts` has the correct authorization-before-load,
  coherent reload, reader-scoped codecs, and final revalidation discipline, but
  serves synthesized pages rather than query answers; and
- the current provenance-source implementation has hermetic fixtures only.

Therefore the production source must be built at a new query-bearing evaluation
composition that combines the application-read authorization discipline with
assertion-local compose/entailment. Post-hoc joining is forbidden.

## Sensitive finalized artifact

The producer creates exactly one immutable artifact for each staged sensitive
read result. Its logical shape is:

```text
finalized-query-grounding-v1
  evaluation result ref + normalized result digest
  copied input digest + input frontier digest
  assignment + execution contract digest
  projection authorization + reader projection + projected content digests
  response digest + finalization digest
  rows[]
    grounded trace ref
    sorted unique contributing subject classes
```

The artifact is sensitive even though it contains no answer text: trace
references and subject classes are linkable to the isolated result. It stays in
the isolated evaluation plane and is never returned by the opaque evaluation
export, blind sheet, product route, telemetry, or error path.

The persisted artifact needs no raw evidence, claim, event, entity, owner,
source, or transcript identifier. Those values are present only inside the
authorized producer while it creates the reader-scoped trace reference and
derives the subject-class row. Persisting fewer identifiers is not license to
guess the mapping later: the producer must seal the artifact during the same
finalization that still holds the exact authorized mapping.

## Producer algorithm

1. Resolve live application authorization and load one coherent graph snapshot.
   Project to the exact reader before search, walk, hydration, model input, trace
   encoding, or any result coordinate.
2. Bind owner, epoch, credential/grant state, authorization digest, reader
   projection digest, projected content digest, graph generation, copied input,
   assignment, and full strategy contract before the first model call.
3. Search, walk, and hydrate only claims in that projected snapshot. An
   unprojected owner snapshot, null projection authorization, hidden claim, stale
   evidence head, tombstone, purge/forget fence, or cross-owner coordinate fails
   before compose.
4. Encode each citation from its exact authorized evidence closure using the
   reader-scoped trace codec while the internal evidence-to-claim relation is in
   hand. The codec output and internal coordinate stay one-to-one for this
   attempt; duplicate outputs fail.
5. Compose an ordered assertion manifest. Entail each assertion against only
   its declared authorized cited spans, then perform drop-only salvage. The
   final answer is exactly the surviving assertion texts joined by one space.
6. For each surviving grounded trace reference, derive contributing subject
   classes from every authorized supporting claim attached to that exact cited
   evidence in this final attempt. Use the existing versioned policy classifier
   and restrictive join. Never infer owner/bystander from text, pronouns,
   speaker rendering, trace shape, or a later snapshot.
7. Require total closure: every final assertion citation is cited and grounded;
   every grounded trace reference is used by an assertion; every such reference
   has exactly one nonempty class row; and no unused/extra row survives.
8. After the final model/entailment call, resolve authorization and coherently
   load again. Any owner, epoch, grant, credential, lifecycle, deletion,
   projection, content, or generation change invalidates the attempt before
   staging.
9. Atomically stage the exact sensitive result and the one finalized grounding
   artifact, or stage neither. Exact replay returns both without model calls.
   Same result coordinate with changed result, provenance, response, projection,
   or strategy bytes is an idempotency conflict.
10. The contamination source loads only this artifact under
    `memories.experiments.shadow`, revalidates live authority, and passes its
    rows through the existing strict total-manifest facade.

## Persistence and replay boundary

The isolated PostgreSQL expansion needs an account/epoch-scoped artifact table
with a one-to-one foreign key to the exact evaluation result and immutable
digests for the result, input, strategy, projection, response, rows, and whole
artifact. No application or product worker receives a grant.

The repository operation must stage result and artifact in one transaction.
A separate best-effort insert is invalid: a crash could leave a result that can
never be audited, or provenance for a result that never committed. A retry must
distinguish exact replay from changed bytes without another model call.

Deletion and epoch change dominate the artifact just as they dominate the
isolated result. Backup/restore may restore both or neither and may never make
the artifact visible to product memory authority.

## Legacy 29.7% parity is a compatibility measurement

The inherited voice-on result was 11 contaminated answers among 37
second-person answers (29.7%), compared with 21/39 voice-off. Across 41
question/pass cells it fixed 15 and introduced 5, with exact McNemar p=0.041.

Those old logs measured whole-answer second person against any bystander-only
citation. Some lack a complete assertion manifest. No new adapter can recover
which sentence used which citation, so the old 29.7% must not be re-described as
assertion-local provenance.

Activation therefore has two distinct gates:

1. a QA-only copied-artifact compatibility adapter reproduces the old
   population, counts, 15/5 pairing, and p-value with the old answer-wide rule;
2. the new producer is measured on fresh results using the stricter
   assertion-local artifact and repeated reads.

Agreement on gate 1 verifies census/pairing compatibility, not production
authority. Gate 2 verifies the new contract. Neither is a truth grade or a
compose-voice default decision.

## Implementation units

1. **Finalizer contract:** return the final entailed assertions instead of
   discarding them; bind reader-scoped citations and policy classes inside one
   authorized projected attempt. No route.
2. **Isolated persistence:** add the inert checksummed artifact schema and a
   sealed atomic result-plus-grounding repository operation. No grant or real
   database claim until the ratified PostgreSQL gate exists.
3. **Offline evaluation composition:** combine authorized copied input,
   strategy assignment, coherent authorization revalidation, query retrieval,
   compose/entailment, result/artifact staging, pairing, and repeats. One model
   pipeline per credential; bounded work only.
4. **Copied-artifact compatibility tool:** zero model calls, copied SQLite/log
   artifacts only, exact input hashes and population/pairing assertions, legacy
   whole-answer result reported separately.
5. **Fresh assertion-local evaluation:** paired repeats, content-safe report,
   then a batched blind truth sheet only if the machine gates pass.

Landed sub-units:

- `cb2e6dc` preserves final entailed assertion manifests across both query
  retrieval paths and writes recall-log v3 assertion/citation ordinals. It does
  not claim authorized trace encoding or final revalidation.
- The QA compatibility tool
  `integration/memory-productionization/legacy-contamination-parity.ts` opens a
  copied store read-only, hashes all five inputs, performs zero writes/model
  calls, and reproduces voice-off 21/39, voice-on 11/37, 15/5 discordance over
  41 paired cells, and p=`0.04138946533203125`. Report digest:
  `6307b3f1f0da796578d43b14d7117d3db08cdad7a406ae44f613a736c68bd59a`.

## Pre-registered acceptance tests

1. Search, walk, hydration, compose, entailment, trace, and class rows cannot
   observe a claim excluded by the exact reader projection.
2. Null/unbranded projection authorization, stale graph/evidence heads, hidden
   evidence, liveness fences, tombstones, cross-owner coordinates, and changed
   account epoch fail before model or stage access.
3. Final revalidation catches grant/credential/lifecycle/deletion/projection
   changes occurring during every model-call boundary.
4. Final assertions, answer bytes, trace stages, class rows, and artifact digest
   are total and mutually closed; missing, extra, duplicate, swapped, unused,
   or forged rows fail.
5. One evidence closure supported by owner and bystander claims produces the
   restrictive mixed class and never becomes bystander-only by omission.
6. Subject classes come from the exact authorized supporting claims and the
   registered classifier version; changing either changes the artifact and
   conflicts under the same coordinate.
7. Result and artifact commit atomically under crash injection before/after
   result insert, artifact insert, commit, and acknowledgement.
8. Exact retry performs zero model calls and returns byte-identical result and
   artifact; changed input, response, projection, policy, strategy, or rows
   fails loudly.
9. Operational logs/outcomes contain only closed codes, counts, digests, and
   opaque work refs; never query, answer, assertion, trace, class, source, owner,
   model output, or raw error content.
10. The QA compatibility tool reproduces voice-off 21/39, voice-on 11/37,
    15 fixed, 5 introduced, 41 paired cells, and exact p=0.041 from copied
    artifacts, with input hashes and zero writes/model calls.
11. Fresh assertion-local results use `--repeats`; primary McNemar N is distinct
    inputs, while later repeats report the read self-noise floor.
12. Focused/full tests, contract QA, import graph, migration manifest/hash,
    changed-file strict TypeScript filter, and `git diff --check` pass.

## Explicit exclusions

- no product query route or transitional `/v1/memories/recall` semantic change;
- no post-hoc provenance reconstruction from text or opaque refs;
- no raw SQLite/log reader in product code;
- no assertion that a clean contamination finding is true or correctly
  diarized;
- no compose-voice, `subject:*`, bystander/privacy, model, or product default;
- no blind grading until a new sheet is explicitly queued for David;
- no PostgreSQL runtime, worker grant, credential, deployment, or cohort action.
