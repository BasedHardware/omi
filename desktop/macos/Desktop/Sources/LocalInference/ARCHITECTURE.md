# Local inference architecture

`LocalInference/` owns on-device generation and embedding. Nothing here opens a
cloud LLM client. Capture, OCR, and cloud upload stay on their existing paths.

## Ports

- `LocalInferenceService` — structured generation / tool loops (summaries).
- `LocalEmbeddingService` — sentence vectors. Implementations must not use a
  network provider. NaturalLanguage types are not Sendable; the Apple adapter
  keeps them inside an actor.

## Embedding engines

`LocalEmbeddingRuntime.makeDefault()` registers Apple `NLContextualEmbedding`
(`apple_nlce`) as the only production engine. English uses the English model;
non-English dominant text falls back to the Latin/multilingual model.
`hasAvailableAssets` is checked first; a miss calls `requestAssets` once with a
bounded wait, then the probe reports `assets_unavailable`. Capture never waits
on that request.

There is no downloadable CoreML pack in this tree. Vectors live only in
`local_embeddings`, keyed by `(sourceKind, sourceId, modelId)`.

## Kill switches

Readable from the process environment or the app UserDefaults:

- `OMI_DISABLE_LOCAL_EMBEDDINGS=1` / `disableLocalEmbeddings` — skip local
  selection. Screen search keeps the existing Gemini path.
- `OMI_FORCE_LOCAL_EMBEDDING_ENGINE=<id>` / `forceLocalEmbeddingEngine` — pin an
  engine id. Unknown ids fail closed to keyword-only.

Generation has a parallel pair (`OMI_DISABLE_LOCAL_INFERENCE`,
`OMI_FORCE_LOCAL_INFERENCE_ENGINE`) documented on `LocalInferenceKillSwitches`.

## Probe and fail-closed ladder

1. Kill switch disabled → Gemini screen search (existing path). `recordFallback`
   `to: keyword` is not used; the route is `legacy`.
2. Selected engine, 32-token synthetic fixture, dimension, two-second budget →
   hybrid (FTS + cosine, RRF). Probe verdicts are cached in-process per
   `(engineID, modelID, thermal, kill-switch)` with a 60s TTL and invalidation
   on thermal or kill-switch change.
3. Probe miss (`assets_unavailable`, over budget, unknown engine) → local
   FTS-only. Never Gemini for a free account. `recordFallback` `to: keyword`.
4. Selected engine that then fails a query → keyword-only. The route does not
   change to Gemini.

## Storage and hybrid search

`LocalEmbeddingStore` owns `local_embeddings`, `transcript_chunks` + FTS5, and
`memories_fts`. `LocalHybridSearch` filters by `sourceKind` so
`search_screen_history` stays screen-only. Transcript chunks (window 8 /
stride 6) and memories are indexed by `LocalEmbeddingIndexer` on session
finalize / memory insert-or-update, with AC-bounded backfill like OCR
embeddings.

## Benchmark

`LocalEmbeddingBenchmark` uses in-repo synthetic fixtures only (no personal
data). Headless: `./scripts/omi-ctl action local_embedding_benchmark` on a
non-production bundle. JSON reports recall@10 and nDCG@10 for FTS, vector, and
hybrid slices. Label every number `synthetic`.
