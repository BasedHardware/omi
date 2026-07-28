# Mac→Windows Parity Audit — File Index / Knowledge Graph / Memory Graph

> Scope: local file-system indexing, the local + server-backed knowledge graph, and the 3D memory-graph visualization. Windows baseline checked: `src/main/fileIndex/{indexer,scanRoots,scanRules,fileTypes}.ts`, `src/main/ipc/{kg.ts,kgWorker.ts,kgWriteQueue.ts,localGraph.ts,db.ts}`, `src/renderer/src/components/graph/{BrainGraph.tsx,LazyBrainGraph.tsx,nodeColor.ts}`, `src/renderer/src/components/onboarding/{BrainMap.tsx,BuildProfileStep.tsx,OrbitScanner.tsx}`, `src/renderer/src/lib/{useGraphSimulation.ts,onboardingGraphModel.ts,localAgent.ts,knowledgeGraphClient.ts,mergeGraphs.ts}`, `src/renderer/src/hooks/{useKnowledgeGraph.ts,useMemoryGraph.ts}`, `src/renderer/src/pages/{Memories.tsx,Onboarding.tsx}`.

## Summary table

| Capability | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Scan roots & directory-skip policy | `FileIndexScanPolicy.swift` | Present-but-weaker | M |
| Incremental scan + automatic 3h background refresh | `FileIndexerService.swift` (`backgroundRescan`), `DesktopHomeView.swift:339-360` | Absent | M |
| File-type categorization granularity | `IndexedFileRecord.swift` (`FileTypeCategory`) | Present-but-weaker | L |
| Local KG storage schema (nodes/edges) | `KnowledgeGraphRecord.swift`, `KnowledgeGraphStorage.swift` | Present-equivalent (Windows schema is a superset) | — |
| Backend KG fetch/rebuild + client-side scoping | `MemoryGraphViewModel.fetchGraph/rebuildGraph` | Present-equivalent (Windows adds account-wide→per-memory scoping) | — |
| Onboarding AI file-exploration → entity extraction ("digital profile") | `FileIndexingView.swift` (`runAIExploration`, `startExplorationChat`, `save_knowledge_graph` tool, `appendExplorationToProfile`, `injectDiscoveryCard`) | Absent | H |
| Chat agent local-context enrichment (`execute_sql` agentic pre-step) | `ChatToolExecutor.swift` (always available) | Present-but-disabled (`ENRICH...` flag off) | M |
| Memory-graph physics (3D vs. 2D-on-plane) | `ForceDirectedSimulation.swift` | Present-but-weaker | L |
| Memory-graph interactivity (drag/rotate/pan/zoom) + standalone full-screen page | `MemoryGraphPage.swift`, `MemoryGraphSceneView` (`allowsCameraControl = true`) | Absent | M/H |
| Onboarding scan progress feedback (per-folder status + numeric %) | `FileIndexingView.swift` loading phase | Present-but-weaker | L |

## File Index / Knowledge Graph capabilities

### Scan roots & directory-skip policy

**What it is:** Which folders get walked for local file metadata, and which subdirectories are pruned to avoid noise/cost.

**Where (Mac):** `FileIndexing/FileIndexScanPolicy.swift`.

**How it works:** Roots = `~/Downloads`, `~/Documents`, `~/Desktop`, `~/Developer`, `~/Projects`, `~/Code`, `~/src`, `~/repos`, `~/Sites`, `/Applications`, `~/Applications`. Max depth 3, max file size 500MB. `skipFolders` is a 21-entry set: `.Trash, node_modules, .git, __pycache__, .venv, venv, .cache, .npm, .yarn, Pods, DerivedData, .build, build, dist, .next, .nuxt, target, vendor, Library, .local, .cargo, .rustup`. Package-like directories (`.app`, `.framework`, `.xcodeproj`, etc.) are indexed as a single opaque record rather than descended into.

**Windows status: Present-but-weaker.** `src/main/fileIndex/scanRoots.ts` mirrors the doc/dev roots closely (adds VS's `~/source/repos`, uses Start-Menu `.lnk` folders as the apps analog — a sensible platform adaptation). But `src/main/fileIndex/scanRules.ts`'s `SKIP_DIRS` is only 4 entries: `.Trash, node_modules, .git, __pycache__`. Build/dependency/venv directories that Mac explicitly excludes — `.venv`, `venv`, `dist`, `build`, `target`, `vendor`, `.next`, `.nuxt`, `.cache`, `.npm`, `.yarn`, `.cargo`, `.rustup` — are NOT skipped on Windows, so a Python venv or a Rust `target/` inside a scanned project directory gets walked and indexed (up to `MAX_DEPTH=3`), diluting `indexed_files` and any `execute_sql`/digest results derived from it.

**Value / notes:** M. Concrete, mechanically fixable divergence; affects file-summary quality and KG signal-to-noise, not just cosmetics.

### Incremental scan + automatic background refresh

**What it is:** Keeping the index fresh as files change, without re-scanning everything every time.

**Where (Mac):** `FileIndexerService.swift` — `scanFolders(_:incremental:)` loads existing `(path → modifiedAt)` for O(1) diffing, skips unchanged files, and deletes index rows for files no longer on disk. `DesktopHomeView.swift:339-360` runs `backgroundRescan()` automatically every 3 hours while the app is running (once onboarding's initial index exists), plus on-demand from Settings.

**Windows status: Absent.** `src/main/fileIndex/indexer.ts`'s `runFileIndex()` always does a full walk, then `clearIndexedFiles()` + `replaceIndexedFiles()` (delete-all + reinsert every record). There is no incremental/diff path and no periodic trigger anywhere in `src/main` (only call sites are the onboarding `BuildProfileStep` and a manual "re-scan" button in `AdvancedTab.tsx` settings). The index only reflects reality at the moment of onboarding or a manual re-scan — it goes stale as the user creates/moves/deletes files during a session, and every re-scan pays the full walk+write cost regardless of how little changed.

**Value / notes:** M.

### File-type categorization granularity

**What it is:** The extension → category bucketing used for the "files by type" summary and KG-adjacent digests.

**Where (Mac):** `IndexedFileRecord.swift` (`FileTypeCategory`) — 10 buckets: `document, code, image, video, audio, spreadsheet, presentation, archive, data, other`.

**Windows status: Present-but-weaker.** `src/main/fileIndex/fileTypes.ts` — 7 buckets: `document, code, image, media, archive, application, other`. Video+audio are collapsed into `media`; spreadsheets/presentations are folded into `document`; Mac's `data` bucket (json/xml/yaml/sql/db/plist/toml/ini/conf) doesn't exist — Windows instead routes json/yaml/toml/sql into `code`. Coarser breakdowns feed into `getFileIndexDigest()`'s `byType`/`byExtension`, so the synthesized "what kind of files does this person have" signal is less nuanced than Mac's.

**Value / notes:** L.

### Local knowledge-graph storage schema

**What it is:** The on-disk shape of the chat-built knowledge graph (nodes/edges persisted locally).

**Where (Mac):** `KnowledgeGraphRecord.swift` (`LocalKGNodeRecord`/`LocalKGEdgeRecord`) + `KnowledgeGraphStorage.swift` — `nodeId, label, nodeType, aliasesJson, sourceFileIds, createdAt, updatedAt` / `edgeId, sourceNodeId, targetNodeId, label, createdAt`. Reads/writes happen synchronously on the shared `RewindDatabase` GRDB pool inside an actor; `saveGraph` does delete-all+insert, `mergeGraph` does upsert.

**Windows status: Present-equivalent (schema is actually a superset).** `local_kg_nodes` / `local_kg_edges` (`db.ts:114-131`) carry `summary`, `source`, `aliases_json`, AND `source_refs` (Mac has no `summary`/`source` fields, and `sourceFileIds` is declared but never populated in the record shown). Writes go through a dedicated worker_thread (`kgWorker.ts`) via `KgWriteQueue` (`kgWriteQueue.ts`) that coalesces concurrent saves and keeps an in-memory snapshot so the Electron main thread is never blocked by the delete+insert transaction — a more robust write path than Mac's synchronous actor write. No gap here; noted for completeness since it's core to the audited area.

### Backend knowledge-graph fetch/rebuild + client scoping

**What it is:** Pulling the server-synthesized (chat/memory-derived) graph and rebuilding it on demand.

**Where (Mac):** `MemoryGraphViewModel.fetchGraph()`/`rebuildGraph()` in `MemoryGraphPage.swift` — local SQLite first, falls back to `APIClient.shared.getKnowledgeGraph()`/`rebuildKnowledgeGraph()` with auth-restore retry loop.

**Windows status: Present-equivalent, arguably deeper.** `knowledgeGraphClient.ts` calls the same `/v1/knowledge-graph` (+`/rebuild`, +`DELETE`, the last unused pending a future milestone). `useMemoryGraph.ts` layers a persisted **onboarding "floor" graph** (you → language → apps, from the local `onboarding_kg_*` tables) under the account-wide server graph, and **scopes** the server graph down to entities referencing the user's *current* memory set (`scopeGraphToMemories`) so deleted memories don't leave phantom nodes — logic with no Mac equivalent found in the read files. No gap.

### Onboarding AI file-exploration → entity extraction ("digital profile")

**What it is:** During onboarding, having an LLM actually read/query the indexed file metadata (via SQL) and synthesize a personalized knowledge graph — people, organizations, things (projects/tools/languages), concepts — plus a written "here's what I found about you" narrative.

**Where (Mac):** `FileIndexingView.swift` — Stage 2 (`runAIExploration`/`startExplorationChat`, 60%→90% of the loading bar): sends a detailed prompt instructing the chat AI to run 3-5 `execute_sql` queries over `indexed_files` (file types/folders/project indicators, recently modified files, tech-stack patterns), then call the `save_knowledge_graph` tool with 15-40 nodes covering People/Organizations/Things/Concepts and their relationships. The live AI messages stream into a "Behind the scenes" info popover. After exploration: `appendExplorationToProfile()` appends the AI's findings to the persistent `AIUserProfileService` profile, and `injectDiscoveryCard()` puts a collapsible "Your Digital Profile" card into the chat transcript. Stage 3 then polls local SQLite for the graph the exploration just saved.

**Windows status: Absent.** `BuildProfileStep.tsx` (the "Discovery" onboarding step) calls `window.omi.indexFilesScan()` (file metadata scan only), then deterministically builds graph nodes from **installed apps** via `addAppNodes(rankApps(apps)...)` (`onboardingGraph.ts`/`onboardingGraphModel.ts` — `buildApps`: one `thing` node + `uses` edge per app) and a language preference node (`buildLanguage`). There is no LLM call, no `execute_sql` exploration of file content/names, no People/Organizations/Concepts extraction, no "Behind the scenes" popover, no AI-profile append, and no discovery card. The resulting onboarding graph is mechanically `you → language` + `you → installed apps` only — materially shallower than Mac's file-content-derived personalization graph.

**Value / notes:** H. This is the single largest gap in this audit area — it's a distinctive first-run "wow" moment on Mac (an AI that has already looked at your files and tells you something specific about your work) that Windows onboarding does not attempt at all; Windows substitutes a purely mechanical app-usage graph.

### Chat agent local-context enrichment (`execute_sql` agentic pre-step)

**What it is:** Before answering a chat message, having the LLM agent optionally run its own `execute_sql`/search queries against the local DB (files, KG, memories) to ground its answer in the user's actual local data — separate from the onboarding-specific exploration above; this is the always-available runtime capability.

**Where (Mac):** `ChatToolExecutor.swift` + `Generated/GeneratedToolExecutors.swift` — the `execute_sql` tool (and others) is a standing capability available to chat at any time, not gated off.

**Windows status: Present-but-disabled.** `src/renderer/src/lib/localAgent.ts` implements the identical bounded agent loop (`{"action":"execute_sql", ...}` / `{"action":"search_memories", ...}` / `{"action":"final"}`, capped iterations, calling `window.omi.kgExecuteSql`) — the plumbing (`kg:executeSql` IPC → `guardSelect` → `execSafeSelect` read-only connection) is fully wired and tested. But the module's own comment states it is currently **off**: *"Floor-only mode... The `execute_sql` agent enrichment added up to `ENRICH_BUDGET_MS` of dead time before every message and, within that budget, usually got cut off mid-loop... So enrichment is OFF... Flip to true to restore the macOS-faithful agentic pre-step."* Chat currently answers from a deterministic "floor" snapshot (`snapshotSections`) instead.

**Value / notes:** M. Self-documented, intentional simplification (not a bug) but a real behavioral gap from the "macOS-faithful" design it references — chat answers with local-data grounding are shallower on Windows today.

## Memory Graph visualization

### Physics model (3D vs. 2D-on-plane)

**What it is:** The force-directed layout algorithm positioning graph nodes in space.

**Where (Mac):** `ForceDirectedSimulation.swift` — genuine 3D physics (`SIMD3<Float>` positions), Coulomb-like pairwise repulsion, spring attraction along edges, center gravity, damping, all three axes free; node size scales with connection count; auto-tunes repulsion/attraction/rest-length by node count (small/medium/large graph presets); guarantees graph connectivity by bridging disconnected components back to the user-anchor node.

**Windows status: Present-but-weaker.** `useGraphSimulation.ts` uses `d3-force-3d` but deliberately constrains every node to the `z=0` plane ("2D layout... this is what makes labels reliably readable — in 3D, two nodes far apart in space can still project on top of each other"), with `forceManyBody` (charge), `forceLink`, `forceRadial` (per-node random target radius instead of Mac's spring rest-length), and label-aware `forceCollide`. This is a considered design tradeoff (readability) rather than an oversight, and it includes things Mac's simulation doesn't (per-node random size/radius jitter for a "cloud" look, gentle reshuffle animation between onboarding screens). Still, it's visually flatter than Mac's true 3D sphere distribution.

**Value / notes:** L — reads as an intentional simplification, not a missing feature.

### Interactivity + standalone full-screen viewer

**What it is:** Letting the user actually explore their knowledge graph — rotate, pan, zoom — outside of onboarding, plus a rebuild control.

**Where (Mac):** `MemoryGraphPage.swift` — a dismissible full-bleed SceneKit view (`scnView.allowsCameraControl = true`, i.e. native drag-to-rotate/scroll-to-zoom/right-drag-to-pan) reachable as its own page, with a rebuild button (spinner while rebuilding) and a dismiss (X) button. There's also `MemoryGraphInlineCard` — a smaller embedded card (350pt tall) with its own rebuild button, used elsewhere in the UI. `FileIndexingView`'s onboarding brain-map screen shows the same interactive SceneKit view with an on-screen shortcuts legend ("Drag to rotate / Right-drag to pan / Scroll to zoom / Double-click to reset").

**Windows status: Absent.** `BrainGraph.tsx` *supports* interactivity (`interactive` prop toggles `<OrbitControls enablePan enableZoom enableRotate />` vs. a fixed non-interactive `CameraRig`), but every call site in the app passes `interactive={false}`: the Memories-page inline card (`Memories.tsx:216`) and the onboarding map (`Onboarding.tsx:282`) both hard-code it off. There is no standalone/full-screen knowledge-graph page anywhere in the Windows renderer (`App.tsx`/`Memories.tsx`/`Onboarding.tsx` are the only three mount sites found), and the Memories inline card has no rebuild button in its UI even though `useKnowledgeGraph()`'s `rebuild()` is available and used internally by the hook layer. Net effect: a Windows user can never drag, rotate, pan, or zoom their own knowledge graph, and can't explicitly trigger a rebuild from the graph UI.

**Value / notes:** M/H — the underlying tech to close this exists in-repo (just flip `interactive` + add a page/route + a rebuild button); the gap is pure UI wiring, not new engineering.

### Onboarding scan progress feedback

**What it is:** Live status while the file scan / AI exploration / KG build runs, so the user isn't staring at an indeterminate spinner.

**Where (Mac):** `FileIndexingView.swift` loading phase — per-folder status text ("Scanning ~/Documents · 1,234 files found"), a real 0-100% progress bar driven by actual scan/exploration/KG-build stage weights (0-60% scan, 60-90% AI exploration with an eased animation curve, 90-100% KG poll), plus `OnboardingLoadingAnimation.swift`'s Canvas-based orbital ring whose filled arc tracks that same percentage.

**Windows status: Present-but-weaker.** `BuildProfileStep.tsx` shows `OrbitScanner.tsx` (a comparable-looking SVG/CSS orbital-dots animation) but it's a purely indeterminate loop with no percentage — status text only flips between "Scanning your projects and apps" and "Your workspace is mapped" once the scan promise resolves, then reveals the final file count. No per-folder progress, no numeric percentage, no live AI-exploration status (consistent with there being no AI exploration step at all, per above).

**Value / notes:** L.

## Spotted outside my scope

- **Rewind screenshot OCR embeddings** (`Rewind/Services/OCREmbeddingService.swift`, Gemini-embedding batched vector search over screen-capture text) are a related-but-separate feature from file indexing — no embeddings exist for *file content* on either platform (both `IndexedFileRecord`/`indexed_files` are metadata-only, no text extraction), so that's parity, not a gap, for this audit's actual scope. Whether Windows has an OCR-embedding equivalent for Rewind screenshots is the `rewind` teammate's area.
- `AdvancedTab.tsx` (Windows Settings) surfaces file-index stats and a manual re-scan button — didn't audit the rest of that settings surface for further Mac parity (e.g. Mac's equivalent settings entry point for file indexing wasn't located in the files read for this pass).
- Windows' `localAgent.ts` agentic loop currently treats `query_kg`/`search_files` actions as legacy no-ops ("Use execute_sql instead") — worth checking whether Mac's `ChatToolExecutor` still exposes those as separate first-class tools, which would be an additional small tool-surface delta not fully chased down here.
