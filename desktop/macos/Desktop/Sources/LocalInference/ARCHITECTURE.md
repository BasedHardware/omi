# Local inference architecture

`LocalInference/` owns on-device generation and embedding. Nothing here opens a
cloud LLM client. Capture, OCR, and screen-activity row sync stay on their existing paths.
`ScreenEmbeddingPolicy` owns the entitlement boundary for screen vectors.

## Ports

- `LocalInferenceService` — structured generation / tool loops (summaries).
- `LocalEmbeddingService` — sentence vectors. Implementations must not use a
  network provider. NaturalLanguage types are not Sendable; the Apple adapter
  keeps them inside an actor.

## Embedding engines

`LocalEmbeddingRuntime.makeDefault()` registers Apple `NLContextualEmbedding`
(`apple_nlce`) as the only production engine. Free and unknown plans default to the local path on every bundle; paid
production-family bundles opt in. Non-production defaults on for every plan. English uses the English
model; non-English dominant text falls back to the Latin/multilingual model.
`hasAvailableAssets` is checked first; a miss calls `requestAssets` once with a
bounded wait, then the probe reports `assets_unavailable`. Capture never waits
on that request. When opt-in is off, `selectEngine()` is `.disabled` and the
indexer is a no-op (no probe, no `requestAssets`).

There is no downloadable CoreML pack in this tree. Vectors live only in
`local_embeddings`, keyed by `(sourceKind, sourceId, modelId)`.

## Opt-in and kill switches

Resolve in this order, synchronously from environment / UserDefaults:

1. `OMI_DISABLE_LOCAL_EMBEDDINGS=1` / `disableLocalEmbeddings` is the hard
   kill: Gemini capture and search on every plan, local off.
2. `OMI_LOCAL_EMBEDDINGS` explicitly true/false overrides
   `localEmbeddingsEnabled`. `0`/`false`/`off` disables local even for free users.
3. With neither override, local is **on** for free/unknown plans and all
   non-production bundles; **off** for paid production-family bundles
   (stable and Beta).
4. `OMI_FORCE_LOCAL_EMBEDDING_ENGINE=<id>` / `forceLocalEmbeddingEngine` pins
   the engine. An unknown engine fails closed.

`FloatingBarUsageLimiter` owns the `floatingBarCachedPlan` cache. It persists
paid identities only when active, writes inactive plans as `basic`, and clears
on sign-out. No network fetch runs on capture. A missing or unrecognized plan
is unknown and has the free spend policy. Explicit local opt-out for free users
means FTS-only; only the hard kill restores Gemini.

Generation has a parallel pair (`OMI_DISABLE_LOCAL_INFERENCE`,
`OMI_FORCE_LOCAL_INFERENCE_ENGINE`) documented on `LocalInferenceKillSwitches`.

## Probe and fail-closed ladder

| Entitlement | Local engine | Gemini capture | Local index | Policy search route |
|---|---|---|---|---|
| Free / unknown / inactive paid | Available | No | Yes | Local hybrid |
| Free / unknown / inactive paid | Unavailable or opted out | No | No | FTS-only |
| Active paid | Available | Yes (Pinecone phone parity) | Yes | Local hybrid |
| Active paid | Unavailable or opted out | Yes | No | Gemini |
| Any, hard kill | Any | Yes | No | Gemini |

Selected engines must pass a 32-token synthetic probe with valid dimensions
within two seconds. Probe results are cached per engine/model/thermal/switch
for 60 seconds. Missing assets, Intel, timeouts, and unknown engine IDs fail
closed for free users. An already-selected local query failure stays keyword-only.
Capture and backfill must recheck the cached entitlement before Gemini batch
dispatch, including batches queued before a downgrade.

Route decisions emit one existing `recordFallback` counter with
`event=screen_embedding_route`, `plan_class=free|paid|unknown`,
`route=gemini|local|fts_only|disabled`, and bounded `route_reason` (the shared
helper buckets its standard `reason`). `disabled` means the hard kill restored
Gemini. No OCR text, query text, plan raw strings, or frame identifiers are sent.
The policy exposes search intent; routing the Rewind UI through that policy is
the follow-up in BasedHardware/omi #13465.

## Storage and hybrid search

`LocalEmbeddingStore` owns `local_embeddings`, `transcript_chunks` + FTS5, and
`memories_fts`. `LocalHybridSearch` filters by `sourceKind` so
`search_screen_history` stays screen-only. Transcript chunks (window 8 /
stride 6) and memories are indexed by `LocalEmbeddingIndexer`. Session
finalize and memory insert-or-update capture the owner snapshot, then
schedule indexing on a background Task — they never await NLCE. Backfill is
AC-bounded like OCR embeddings.

## Benchmark

`LocalEmbeddingBenchmark` uses in-repo synthetic fixtures only (no personal
data). Headless: `./scripts/omi-ctl action local_embedding_benchmark` on a
non-production bundle. JSON reports recall@10 and nDCG@10 for FTS, vector, and
hybrid slices. Label every number `synthetic`.
