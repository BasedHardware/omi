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
Both Rewind capture variants share `indexScreenshotEmbeddings`: OCR is persisted
first, then the policy schedules Gemini and/or local vector writes. The local
indexer resolves production switches on each operation so checkout, sign-out,
and opt-out do not require restarting the process.

Capture and backfill recheck the cached entitlement before Gemini batch
dispatch, including batches queued before a downgrade.

Route decisions emit one existing `recordFallback` counter with
`route_event=screen_embedding_route`, `plan_class=free|paid|unknown`,
`route=gemini|local|fts_only|disabled`, and bounded `route_reason` (the shared
helper uses `policy` or `dispatch_disabled` for its standard `reason`).
`disabled` means the hard kill restored Gemini. No OCR text, query text, plan raw strings, or frame identifiers are sent.
Capture records a route on every frame; the process emits only when
`(planClass, searchRoute, reason)` changes, plus at most one heartbeat per hour.
Chat `search_screen_history` and the Rewind UI search both take
`ScreenHistorySearchRoute`, so a free plan never embeds the query with Gemini.

## Plan ladder

| Plan | Capture embed | Search |
|---|---|---|
| Free / unknown / inactive paid | Local / FTS-only (never Gemini) | Local hybrid when the engine is available; otherwise FTS-only |
| Active paid | Gemini upload (Pinecone phone parity) plus local index when available | Local hybrid when the engine is available; otherwise Gemini |
| Any, hard kill (`OMI_DISABLE_LOCAL_EMBEDDINGS`) | Gemini | Gemini |

## Rollout: client capability handshake

The server embed gate is on by default. A current client sends
`X-Omi-Local-Embeddings: 1` on every Gemini proxy request (via
`DesktopGeminiProxyRequest.prepare`) unless the hard kill is set. The proxy
402s basic-plan `embedContent` / `batchEmbedContents` for that header.
Builds that predate this change omit the header and fail open to Gemini.
`DESKTOP_EMBED_PLAN_GATE_DISABLED=1` is the only server kill switch.
Rollout is merge, then desktop release; there is no backend config step.

## Rollout: vectorless row sync

Legacy `ScreenActivitySyncService.fetchLegacySyncRows` still requires
`embedding IS NOT NULL` while Gemini capture is on. When the current
`ScreenEmbeddingPolicy` says `shouldEmbedWithGemini == false`, a row is
sync-eligible without a vector once OCR is final (non-empty text and the
five-minute bucket has closed — the lossless path's notion of final, so an
in-flight OCR row is not shipped early). Lossless sync already delivers
text-only rows after its 15-minute embedding grace. The backend
`POST /v1/screen-activity/sync` handler (`routers/desktop_screen_crisp.py`)
accepts `embedding: null` and still upserts Firestore rows; Pinecone is gated
separately by `grants_cloud_screen_vectors`.

## Storage and hybrid search

`LocalEmbeddingStore` owns `local_embeddings`, `transcript_chunks` + FTS5, and
`memories_fts`. `LocalHybridSearch` filters by `sourceKind` so
`search_screen_history` stays screen-only. Transcript chunks (window 8 /
stride 6) and memories are indexed by `LocalEmbeddingIndexer`. Session
finalize and memory insert-or-update capture the owner snapshot, then
schedule indexing on a background Task — they never await NLCE. Backfill is
AC-bounded like OCR embeddings.

## Benchmark

`LocalEmbeddingBenchmark` has two fixtures. Headless:
`./scripts/omi-ctl action local_embedding_benchmark` on a non-production bundle.
`fixture=synthetic` (default) uses in-repo fixtures with no personal data.
`fixture=real` copies a Rewind DB (Beta bundle path, or `db=`) to a temp file
first and never opens the live database. It samples up to 500 screenshot rows
that already hold a Gemini embedding blob and non-empty OCR, builds the local
index with the selected engine (`apple_nlce`) when missing, then reports
recall@10 / nDCG@10 for FTS, vector, hybrid, and Gemini-cosine.

Ground truth on a real DB has no labels, so the report is honest about two
views: (a) **agreement with Gemini** — top-10 overlap of each local mode
against Gemini document-space kNN for the same source row (queries never leave
the process, so Gemini ranking uses the stored document vector rather than a
network query encoder); (b) **held-out self-retrieval** — a distinct 6–12 word
span from after the first OCR line, target is that row, recall@1/@10 per mode.

The JSON report contains only counts, metric values, engine id, model id,
dimension, timings (p50/p95 embed ms, total index ms), row counts, and the
machine chip/ram class. No OCR text, window titles, or query strings. Label
every number with `fixture: real` or `fixture: synthetic`.
