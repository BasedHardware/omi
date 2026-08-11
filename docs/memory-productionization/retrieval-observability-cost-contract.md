# Retrieval observability and cost-control contract

Status: P1 preregistration, 2026-08-11

## Scope

This unit selectively adapts measured, semantics-preserving mechanisms from research
commits `a0f5015db7`, `08c09078c8`, `2e4df82247`, `cc0da32b6b`, and
`ece0c94544`. It does not introduce a retrieval strategy, answer policy, product route,
model default, PostgreSQL job, or production cache.

The canonical backend already owns the safety-critical read path: authorization precedes
projection, liveness and lineage-head selection are reader-relative, produced renders are
branded and citation-closed, completeness qualifies absence, and the coherent read is
revalidated before codecs, bytes, cursors, or trace emission. This unit must converge on
those contracts rather than copy the research recall log.

The measured defects are:

- repeated recall logs localized zero of nine answer flips; stage-localized artifacts
  later distinguished no evidence from grounding loss and measured zero exact citation
  reuse in 22 repeated v9 answers;
- structured assertion citations enabled a zero-call census over 147 grounded assertions;
- `liveCommittedClaims` rebuilt a 34,236-entry evidence-head map per claim and took
  3.69 seconds on the v7 graph;
- the two-sided trajectory walk did not finish in 180 seconds, while the structural-only
  diff took 71 ms and avoided roughly 25.6 MB per-cycle walk output;
- v7 made at least 320 model calls per dream cycle, 87% in two repeated per-group phases,
  while raw-input cache identity missed prompt-equivalent work.

These measurements justify observability and cost work. They do not prove answer-quality,
cache-hit, production-overhead, or canonical-store performance improvements.

## Invariants frozen before implementation

### Authorized liveness selection

1. Selection order remains exact: authorize the reader, select reader-visible candidates,
   apply global purge/forget/evidence liveness, choose a head among visible live lineage
   members, then build provenance and citations. A hidden newer revision cannot suppress
   an older revision the reader may see.
2. The evidence-head map and purge/forget sets are built once inside one selection attempt.
   They remain private implementation details derived from that exact graph snapshot.
   Public callers cannot supply or reuse a map or set that could change liveness truth.
3. The optimization changes no selected claim, diagnostic, projected-content digest,
   authorization digest, generation, citation, completeness result, or wire byte.
4. Tombstoned/security-hidden evidence, corrupt evidence-head ties, missing evidence,
   purged/forgotten claims, and non-head lineage revisions remain fail-closed.

### Recall trace and assertion provenance

1. `recall-trace-v1` remains exact and authoritative. Research `recall_log.v3`, its raw
   evidence ids, query/answer text, host/database fields, and agent tool arguments are not
   production contracts.
2. Assertion provenance is a separate exact-shaped, versioned manifest. It contains only
   a stable assertion ordinal and unique reader-scoped opaque `tr1_` citation references.
   It contains no assertion text and is never reconstructed by sentence-splitting rendered
   prose.
3. The manifest may be built only from structured assertions that survived grounding and
   from citations already authorized for that read. It cannot add, remove, reorder, or
   smooth answer text, and it is not exposed on a product route in this unit.
4. Telemetry is evidence, never read or write authority. Sink failure cannot affect output.
   Denied or invalidated reads emit no successful read trace.

### Trajectory analysis

1. Trajectory analysis mode is explicit typed input, not an environment variable.
   `full` computes components and newly walkable paths; `structural` omits them.
2. A report carries a version and an explicit `walk_analysis` value. Empty walk fields mean
   "none found" only when analysis was computed; skipped work is never represented as an
   empty finding without that marker.
3. Structural fields are byte-identical in both modes. The current caller remains on
   `full` in this unit, so the runtime default does not change before a copied-store profile
   confirms the canonical cost and a later activation decision is recorded.
4. This is not called a once-per-cycle snapshot guarantee. The research commit did not
   establish such an invariant; it only reused selection indexes and made walk work
   skippable.

### Model telemetry and cache identity

1. The model adapter may expose the digest of the exact initial prompt bytes it sends,
   together with explicit model/provider, adapter, strategy, prompt, parser/schema,
   policy, retry, sampling/tool, and cache-format coordinates. Raw prompt bytes never
   enter a cache store or telemetry sink.
2. A cache scope is owner/account-specific. Reader-facing model work additionally binds
   the reader projection and authorization state, and cache lookup occurs only after that
   authorization/projection. A shared hit/miss timing channel across grants is forbidden.
3. Only strictly parsed successful results are cacheable. Throws, timeouts, provider
   failures, malformed responses, retryable/partial outcomes, and raw error strings are
   never cached. Cache corruption or coordinate mismatch is a miss, not a served value.
4. Retry-repair prompt bytes differ from the initial prompt. This unit does not claim
   exact successful-request caching until the adapter returns the exact successful prompt
   digest with its validated result.
5. The existing SQLite verdict cache remains QA/offline only. It may gain an adapter-owned
   prompt-identity seam and stricter tests, but no environment-selected path becomes a
   production control plane and no cache is wired into application service composition.
6. Content-safe operational telemetry is injected. Events contain only closed stage/error
   codes, opaque digests, bounded counts, token counts, duration, and explicit versions.
   They exclude query, prompt, excerpt, account/evidence ids, model output, tool arguments,
   provider/parser messages, and stack traces.
7. The research change from three to five GLM/agent retries is excluded. Retry policy is
   behavior and cost, not telemetry.

## Acceptance tests

- optimized and reference liveness selection are semantically identical across grants,
  tombstones, purge/forget fences, evidence-head ties, missing commit sequences, and input
  array permutations;
- the private evidence/fence indexes are constructed once per selection attempt and cannot
  be injected by a caller;
- assertion provenance rejects raw ids, duplicate/unsorted citations, extras, accessors,
  proxies, decorated/sparse arrays, invalid ordinals, and forged trace refs;
- assertion provenance serialization contains none of supplied query, answer, excerpt,
  account, evidence, model-output, or provider-error sentinels;
- full and structural trajectory modes have byte-identical structural fields, skipped walk
  analysis is explicit, and the current dream caller explicitly requests `full`;
- prompt-equivalent input objects share an adapter prompt digest, while any owner, model,
  adapter, strategy, prompt/schema/policy/retry/sampling, reader-projection, authorization,
  or cache-format coordinate change yields a different cache identity;
- failures and malformed/corrupt cache records are misses and remain retryable; successful
  empty model verdicts remain cacheable when the edge parser accepts them;
- trace/telemetry sink failure does not change canonical response bytes, and final read
  revalidation still detects any grant, graph, render, coverage, or coherent-timestamp
  change before output;
- focused retrieval/model/dream tests, the complete test suite, `qa:contracts`, and the
  import-graph gate pass without route, subject, compose, provider-default, or service
  composition changes.

## Explicit exclusions and exit

This unit excludes `subject:*`, bystander privacy, compose voice, owner/mixed-voice rules,
agentic query planning, entity dossiers, prompt experiments, accepted/STM positive
synthesis, health/readiness claims, PostgreSQL persistence, deployment, and human grading.

The unit exits with a local commit and independent review. It may claim semantic
equivalence and stricter observability/cost contracts. It may not claim faster production
reads, fewer production model calls, better answers, or production cache readiness until
the later copied-store profile/replay and PostgreSQL activation slices supply that evidence.
