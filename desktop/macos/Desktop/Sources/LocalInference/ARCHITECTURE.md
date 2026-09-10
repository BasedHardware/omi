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
(`apple_nlce`) as the only production engine. Released bundles stay on Gemini
until opt-in; non-production dogfoods the local path. English uses the English
model; non-English dominant text falls back to the Latin/multilingual model.
`hasAvailableAssets` is checked first; a miss calls `requestAssets` once with a
bounded wait, then the probe reports `assets_unavailable`. Capture never waits
on that request. When opt-in is off, `selectEngine()` is `.disabled` and the
indexer is a no-op (no probe, no `requestAssets`).

There is no downloadable CoreML pack in this tree. Vectors live only in
`local_embeddings`, keyed by `(sourceKind, sourceId, modelId)`.

## Opt-in and kill switches

Default **on** in non-production (`AppBuild.isNonProduction`), **off** on
production-family bundles (stable and Beta). Readable from the process
environment or the app UserDefaults:

- `OMI_LOCAL_EMBEDDINGS=1` / `localEmbeddingsEnabled` — opt in on a
  production-family bundle. `0`/`false`/`off` turns it off even in
  non-production.
- `OMI_DISABLE_LOCAL_EMBEDDINGS=1` / `disableLocalEmbeddings` — hard kill.
  Screen search keeps the existing Gemini path even if opt-in is on.
- `OMI_FORCE_LOCAL_EMBEDDING_ENGINE=<id>` / `forceLocalEmbeddingEngine` — pin an
  engine id. Unknown ids fail closed to keyword-only.

Generation has a parallel pair (`OMI_DISABLE_LOCAL_INFERENCE`,
`OMI_FORCE_LOCAL_INFERENCE_ENGINE`) documented on `LocalInferenceKillSwitches`.

## Probe and fail-closed ladder

1. Not opted in, or hard kill → Gemini screen search (existing path). No probe,
   no indexer, no `requestAssets`. `recordFallback` `to: keyword` is not used;
   the route is `legacy`.
2. Opted in, selected engine, 32-token synthetic fixture, dimension,
   two-second budget → hybrid (FTS + cosine, RRF). Probe verdicts are cached
   in-process per `(engineID, modelID, thermal, kill-switch)` with a 60s TTL
   and invalidation on thermal or kill-switch change.
3. Opted in, probe miss (`assets_unavailable`, over budget, unknown engine) →
   local FTS-only. Never Gemini. `recordFallback` `to: keyword`.
4. Opted in, selected engine that then fails a query → keyword-only. The route
   does not change to Gemini.

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
