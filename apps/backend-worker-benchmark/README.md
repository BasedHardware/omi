# Backend Worker Retrieval Benchmark

Synthetic-only, local-first benchmark harness to select between **Cloudflare
Vectorize** and **Cloudflare AI Search** for derived retrieval in
`apps/backend-worker`. No hosted index is created, no credentials are used, no
production-like content is loaded, and no deploy or network calls are made.

## Scope

- **Synthetic only.** Every fixture carries `synthetic: true` and an
  `acct-synthetic-*` account id. The fixture validator rejects production-like
  fields (`email`, `transcript`, `token`, …) and any relevance id that does not
  resolve to a same-account synthetic document.
- **Two account scopes** (`acct-synthetic-alpha`, `acct-synthetic-beta`) with
  overlapping embeddings so cross-account leakage is detectable.
- **Queries and mutations.** The harness upserts, queries, deletes, flushes, and
  re-queries per scope.
- **Provider adapter interface** (`RetrievalProvider` in `src/types.ts`): one
  contract for both candidates. The local providers are in-memory simulations of
  Vectorize (pure vector) and AI Search (hybrid vector + term) semantics, not the
  hosted services.

## Hard gates

- **Account isolation:** any hit id foreign to the querying account fails the
  run.
- **Deletion correctness:** a revoked id returned after deletion fails the run.
- **Sensitivity self-check:** an intentionally bad provider (ignores scope,
  ignores deletes) is run every time and must fail both gates. If it passes, the
  harness is broken, not the candidate.

## Metrics

Recall@K, MRR, nDCG, and p50/p95/p99 for both query latency and index lag
(staleness between upsert and visibility).

## Run

```sh
bun run test          # full suite
bun run test:focused  # fixture validator only
bun run run           # print a local metric + gate report
bun run check         # format:check + lint + typecheck + test
```

## Selection rubric

A candidate is selectable only when ALL of the following hold on a real
Cloudflare staging run against synthetic staging resources:

1. **Hard gates pass** for both account scopes (isolation + deletion).
2. **Recall@K / MRR / nDCG** meet or exceed the derived-retrieval quality bar on
   the synthetic relevance set.
3. **p95 latency** fits the Worker's retrieval budget.
4. **Index lag p95** is tolerable for the derived-content freshness SLA.
5. **Operational fit:** index/metadata limits, per-account isolation primitives,
   delete/tombstone semantics, and cost fit the Worker's deployment model.

## No winner claimed here

This harness produces **local simulation numbers only**. It does NOT claim that
either Vectorize or AI Search won. The in-memory providers model expected
scoring and lag behavior but are not the hosted services. A real staging run on
synthetic staging resources (a Cloudflare Vectorize index and an AI Search index
populated with synthetic documents only) is required before any selection.

## Boundary for eventual synthetic staging resources

When staging becomes available, the work is bounded to:

- Create one **synthetic-only** Vectorize index and one **synthetic-only** AI
  Search index in a staging Cloudflare account. No production data, no real user
  ids, no credentials in this repo.
- Implement `RetrievalProvider` adapters that call the hosted APIs, keeping the
  same interface and the same hard gates.
- Reuse this corpus, validator, harness, metrics, and gates unchanged.
- The fixture validator and hard gates remain the acceptance boundary; a hosted
  adapter that leaks accounts or returns revoked ids fails identically.
