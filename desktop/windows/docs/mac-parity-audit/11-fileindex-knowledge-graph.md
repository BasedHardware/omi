# Mac→Windows Parity Audit — File Index / Knowledge Graph / Memory Graph

> **Audit date: 2026-08-22 (re-audit, second pass).** Supersedes the 2026-08-20 pass,
> which was found to be materially stale on this area — several "Absent" verdicts
> described features that had already shipped, in one case (the full-screen
> interactive brain map) more than five weeks before that audit was written. Every
> claim below was independently re-verified against source on this date — file
> contents, `git log` dates, and line numbers were re-checked one by one rather than
> trusted from any prior draft of this document — see "Changed since the 2026-08-20
> audit."

> Scope: local file-system indexing, the local + server-backed knowledge graph, and the 3D memory-graph visualization. Windows baseline checked: `src/main/fileIndex/{indexer,scanPlan,scanRoots,scanRules,fileTypes}.ts`, `src/main/ipc/{kg.ts,kgWorker.ts,kgWriteQueue.ts,localGraph.ts,db.ts}`, `src/renderer/src/components/graph/{BrainGraph.tsx,LazyBrainGraph.tsx,KnowledgeGraphViewer.tsx,nodeColor.ts}`, `src/renderer/src/components/onboarding/{BrainMap.tsx,BuildProfileStep.tsx,OrbitScanner.tsx}`, `src/renderer/src/pages/{Memories.tsx,Onboarding.tsx,KnowledgeGraph.tsx}`, `src/renderer/src/lib/{useGraphSimulation.ts,onboardingGraphModel.ts,onboardingGraph.ts,localAgent.ts,knowledgeGraphClient.ts,mergeGraphs.ts,kgSynthesis.ts,kgSynthesisPrompt.ts,graphDisplay.ts,appLifetimeJobs.ts,screenSynthesis.ts}`, `src/renderer/src/hooks/{useKnowledgeGraph.ts,useMemoryGraph.ts}`, `src/renderer/src/routes/manifest.ts`. Mac baseline re-spot-checked where cited: `desktop/macos/Desktop/Sources/{FileIndexing,MainWindow,MainWindow/Pages/MemoryGraph,Providers}`.

## Changed since the 2026-08-20 audit

Re-verifying every line-and-file citation in this area against current source turned
up one *new* correction beyond what the first re-audit pass already caught (all of
which held up under a second, independent check):

- **Re-confirmed, all still accurate on re-check:** the full-screen interactive
  `/knowledge-graph` viewer (shipped 2026-07-15/19), true 3D physics for that viewer
  (`dimensions: 2 | 3`, shipped 2026-07-16/18), incremental mtime-diff scanning
  (`scanPlan.ts`, shipped 2026-07-14), the widened 28-entry `SKIP_DIRS` list
  (shipped 2026-07-14, 21 macOS entries verbatim + 7 Windows-specific), and the
  onboarding AI entity-extraction engine (`kgSynthesis.ts`/`kgSynthesisPrompt.ts`,
  present since the Windows app's first commit on 2026-06-11) all check out exactly
  as previously reported, down to the cited line numbers, commit hashes, and code
  comments. Re-verified fresh this session: `SKIP_DIRS`'s exact 28-entry contents,
  `scanPlan.ts`'s retention-diff logic and its three 2026-07-14 commits,
  `KnowledgeGraphViewer.tsx`'s rebuild/density/labels controls line-by-line,
  `useGraphSimulation.ts`'s `dimensions` plumbing (including that `BrainGraph.tsx`
  itself, not just the hook, hard-codes `interactive ? 3 : 2` at its call site),
  `localAgent.ts`'s `ENRICH_ENABLED = false` and its surrounding comment verbatim,
  and `appLifetimeJobs.ts`'s `GRAPH_BUILD_DELAY_MS = 1800`. BrainGraph's two preview
  call sites (`Memories.tsx:563`, `Onboarding.tsx:325`) are still hard-coded
  `interactive={false}`.
- **New this pass — a Mac-side reference citation had gone stale, not a Windows
  finding.** The previous re-audit cited Mac's `MemoryGraphInlineCard` — "a smaller
  embedded card (350pt tall) with its own rebuild button" living at the top of the
  Memories list — as the thing Windows's non-interactive preview card corresponds
  to. That type **no longer exists on Mac at all**: commit `bdff578fd9` ("SB review
  polish — home insights, chat spinner, ⌘O, Brain Map tab", 2026-07-22) deleted the
  `MemoryGraphInlineCard(viewModel:)` call from `MemoriesPage.swift` outright — "Brain
  Map now lives in its own hub tab (beside Memories/Conversations), so it's no longer
  embedded at the top of the memory list." This landed **before** the original
  2026-08-20 audit was even written, so both that audit and the first 2026-08-22
  re-audit cited a Mac surface that had already been removed for four weeks. Mac's
  Brain Map is now reached exclusively via a `MemoryHubSwitcher` tab
  (`MemoryHubPage.swift`) — there is no longer a small non-interactive preview on
  Mac at all; the tab is always the same fully-interactive SceneKit view
  (`allowsCameraControl = true`). This makes Windows's inline-preview-plus-full-page
  split a Windows-specific design choice rather than something mirroring a Mac
  surface — it does not change any Present/Absent verdict, but the "Where (Mac)"
  citation is corrected below. Separately, and **out of this audit's scope to
  evaluate**: Mac's Brain Map tab itself now branches on a server-driven capability
  flag (`MemoryGraphPresentationMode.resolve(canonicalLifecycleExposed:)`,
  `MemoryGraphPage.swift:27-34`) between the legacy SceneKit/`ForceDirectedSimulation`
  view this audit's Mac citations describe and a new, structurally different
  "Canonical Memory Atlas" (`CanonicalMemoryAtlasView.swift`, cluster-based —
  People/Organizations/Places/Things/Concepts as "territories" — under active
  development as recently as 2026-08-16). Accounts for which the server has not yet
  exposed `canonicalLifecycleExposed` still get the legacy view these Mac citations
  target; accounts that have may already see something this audit never evaluates.
  Flagged, not audited — a parity comparison against the canonical atlas would need
  its own pass.
- **Line-number correction:** the periodic 3-hour background-rescan `.task` block in
  `DesktopHomeView.swift` is at lines **294-306** as of this session, not 339-360 as
  previously cited — unrelated code was added above it since. The finding itself
  (Windows still has no periodic re-scan timer, only a 30s-post-launch backfill plus
  manual) is unchanged and re-confirmed by grepping every `setInterval` in
  `src/main` this session.
- **Provider-routing footnote, no behavioral change:** `localAgent.ts`'s
  `AGENT_MODEL` was repointed from a hardcoded `claude-haiku-4-5-20251001` to the
  managed structured lane id `'omi-structured'` on 2026-08-09 (commit `bce7414c5a`,
  "managed structured lane for desktop planner and local agent"). `ENRICH_ENABLED`,
  `MAX_ITERS`, `AGENT_CALL_TIMEOUT_MS`, and the disabled-agentic-preflight finding
  are all untouched by that commit and remain accurate.
- **Resolved, not just re-flagged:** the previous pass's "spotted outside scope" note
  wondered whether Mac's `ChatToolExecutor` still exposes `query_kg`/`search_files` as
  separate first-class tools, since Windows's `localAgent.ts` treats them as dead
  legacy no-ops ("Use execute_sql instead"). Checked this session:
  `GeneratedToolExecutors.swift`'s full ~39-entry tool enum has no `query_kg` or
  `search_files` case at all, today or historically searchable in this file. These
  are Windows-internal legacy action names from an earlier iteration of its own
  agent loop, not a live Mac parity gap — there is nothing on the Mac side for them
  to be behind.

## Summary table

| Capability | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Scan roots & directory-skip policy | `FileIndexScanPolicy.swift` | Present-equivalent (superset of Mac's list) | — |
| Incremental (mtime-diff) re-scan | `FileIndexerService.swift` (`scanFolders(_:incremental:)`) | Present | — |
| Automatic periodic background re-scan (Mac: every 3h) | `DesktopHomeView.swift:294-306` | Absent (one-time 30s post-launch backfill + manual only) | M |
| File-type categorization granularity | `IndexedFileRecord.swift` (`FileTypeCategory`) | Present-but-weaker | L |
| Local KG storage schema (nodes/edges) | `KnowledgeGraphRecord.swift`, `KnowledgeGraphStorage.swift` | Present-equivalent (Windows schema is a superset) | — |
| Backend KG fetch/rebuild + client-side scoping | `MemoryGraphViewModel.fetchGraph/rebuildGraph` | Present-equivalent (Windows adds account-wide→per-memory scoping) | — |
| Local semantic entity extraction (LLM: person/org/project/interest + relationships + narrative overview) | `FileIndexingView.swift` (`runAIExploration`, `save_knowledge_graph`) | Present, but as a silent post-onboarding background job — no onboarding-time spectacle, no discovery card, no visible narrative reveal | M |
| Chat agent local-context enrichment (`execute_sql` agentic pre-step) | `ChatToolExecutor.swift` (always available) | Present-but-disabled (`ENRICH_ENABLED = false`) | M |
| Memory-graph physics (3D vs. 2D-on-plane) | `ForceDirectedSimulation.swift` (legacy path; see canonical-atlas caveat above) | Present-equivalent for the interactive viewer (true 3D); previews stay 2D by design | L |
| Memory-graph interactivity (drag/rotate/pan/zoom) + standalone full-screen surface | `MemoryGraphPage.swift` via `MemoryHubPage`'s Brain Map tab (`MemoryGraphSceneView`, `allowsCameraControl = true`) | Present-equivalent (`/knowledge-graph` route, `KnowledgeGraphViewer.tsx`) | — |
| Onboarding scan progress feedback (per-folder status + numeric %) | `FileIndexingView.swift` loading phase | Present-but-weaker | L |

## File Index / Knowledge Graph capabilities

### Scan roots & directory-skip policy

**What it is:** Which folders get walked for local file metadata, and which subdirectories are pruned to avoid noise/cost.

**Where (Mac):** `FileIndexing/FileIndexScanPolicy.swift`.

**How it works:** Roots = `~/Downloads`, `~/Documents`, `~/Desktop`, `~/Developer`, `~/Projects`, `~/Code`, `~/src`, `~/repos`, `~/Sites`, `/Applications`, `~/Applications`. Max depth 3, max file size 500MB. `skipFolders` is a 21-entry set: `.Trash, node_modules, .git, __pycache__, .venv, venv, .cache, .npm, .yarn, Pods, DerivedData, .build, build, dist, .next, .nuxt, target, vendor, Library, .local, .cargo, .rustup`. Package-like directories (`.app`, `.framework`, `.xcodeproj`, etc.) are indexed as a single opaque record rather than descended into.

**Windows status: Present-equivalent — a superset of Mac's list.** `src/main/fileIndex/scanRoots.ts` mirrors the doc/dev roots (adds VS's `~/source/repos`; uses Start-Menu `.lnk` folders, tagged `kind: 'apps'`, as the `/Applications` analog). `src/main/fileIndex/scanRules.ts`'s `SKIP_DIRS` (as of commit `9556d87472`, 2026-07-14, "widen skip-list to macOS parity") carries all 21 of Mac's `skipFolders` entries verbatim, plus 7 Windows/.NET-specific additions: `obj`, `bin`, `packages`, `.gradle`, `.terraform`, `$RECYCLE.BIN`, `OneDriveTemp` — 28 entries total, re-counted and re-diffed against Mac's list this session, case-insensitively matched via `NORMALIZED_SKIP_DIRS`. There is no gap here.

**Value / notes:** — (no gap). Package-like-directory-as-opaque-record (`.app`/`.xcodeproj`) has no direct Windows analog beyond the `.lnk`-as-apps-root treatment, but that's covered by the roots/kind split, not skip-list weakness.

### Incremental re-scan + automatic background refresh

**What it is:** Keeping the index fresh as files change, without re-scanning everything every time, and doing so periodically without user action.

**Where (Mac):** `FileIndexerService.swift` — `scanFolders(_:incremental:)` loads existing `(path → modifiedAt)` for O(1) diffing, skips unchanged files, and deletes index rows for files no longer on disk. `DesktopHomeView.swift:294-306` runs a `.task { while !Task.isCancelled { ... FileIndexerService.shared.backgroundRescan() } }` loop sleeping `3 * 60 * 60` seconds between runs, gated on `hasCompletedFileIndexing`, plus a separate one-time post-launch backfill (`scheduleInitialFileIndexing()`, `DesktopHomeView.swift:880-896`) and on-demand runs from Settings.

**Windows status: Present for the incremental diff; still Absent for periodic auto-refresh.** `src/main/fileIndex/scanPlan.ts`'s `planScan()` (added 2026-07-14, commit `69cfaea20b` "incremental mtime-skip, persisted status, startup backfill") walks the roots, records a file for upsert only when it's new or its `modifiedAt` changed against the caller-supplied `existing: Map<string, number>`, and computes a pure retention diff (`pathsToDelete`, ported 1:1 from `FileIndexerService.pathsToDelete`) that protects any root/subdirectory whose enumeration failed or was absent — an unreadable folder or unmounted drive can no longer purge its previously-indexed rows (a bug the 2026-07-14 commit `7437b58bfd`/`435015da3b` pair explicitly hardened against: "never blind-clear when the scan env is empty" / "stop wiping the index on a transient read failure"). `indexer.ts::runFileIndex()` calls `planScan()` then `applyFileIndexDiff(toUpsert, toDelete)` — no more full clear-then-reinsert. Re-read `scanPlan.ts` and `indexer.ts` in full this session; both hold up exactly as described.

What is still missing is a Mac-style **periodic** timer. The only automatic trigger is `scheduleStartupRescan()` (`indexer.ts:109-120`) — a single `setTimeout(30_000)` fired once per app launch, gated on the index already being populated (so it never races onboarding's first scan) and `unref()`'d so it can't hold the process open, which calls `runFileIndex()` exactly once. Grepping `desktop/windows/src/main` for every `setInterval` this session (26 hits) confirms none belongs to the file index — they're the updater, several assistant/coordinator subsystems, Rewind OCR/embeddings/retention, task sync, the floating bar, and similar unrelated timers. So a long-running session (no relaunch) still only refreshes the index via the onboarding scan, the 30s-after-launch backfill, or the user's manual "Re-scan now" in `AdvancedTab.tsx` (`fileIndex.ts` exposes `fileIndex:scan` for that, confirmed still wired this session). Practically this now matters much less than the old "Absent" verdict implied, since a relaunch — likely at least daily — gets a full incremental catch-up cheaply; but a session left open across a 3h+ working day, as Mac explicitly re-scans, will not.

**Value / notes:** M for the still-missing periodic trigger (down from the old audit's combined M, since the costlier half of the gap — full-walk-every-time, unsafe blind-clear — is fixed).

### File-type categorization granularity

**What it is:** The extension → category bucketing used for the "files by type" summary and KG-adjacent digests.

**Where (Mac):** `IndexedFileRecord.swift` (`FileTypeCategory`, an enum re-read this session) — 10 buckets: `document, code, image, video, audio, spreadsheet, presentation, archive, data, other`.

**Windows status: Present-but-weaker (unchanged).** `src/main/fileIndex/fileTypes.ts` — still 7 buckets: `document, code, image, media, archive, application, other`. Video+audio remain collapsed into `media`; spreadsheets/presentations remain folded into `document`; there is still no `data` bucket — json/yaml/toml/sql still route into `code`. `git log` shows no commits to this file since the initial Windows port (2026-06-11) — re-confirmed this session; this is a genuinely unchanged, still-accurate finding.

**Value / notes:** L.

### Local knowledge-graph storage schema

**What it is:** The on-disk shape of the chat-built knowledge graph (nodes/edges persisted locally).

**Where (Mac):** `KnowledgeGraphRecord.swift` (`LocalKGNodeRecord`/`LocalKGEdgeRecord`) + `KnowledgeGraphStorage.swift` — `nodeId, label, nodeType, aliasesJson, sourceFileIds, createdAt, updatedAt` / `edgeId, sourceNodeId, targetNodeId, label, createdAt`. Reads/writes happen synchronously on the shared `RewindDatabase` GRDB pool inside an actor; `saveGraph` does delete-all+insert, `mergeGraph` does upsert.

**Windows status: Present-equivalent (schema is still a superset).** `local_kg_nodes` / `local_kg_edges` (base columns at `db.ts:452-469`: `id, label, node_type, summary, source, created_at` / `id, source_id, target_id, label, created_at`) plus `aliases_json` and `source_refs` added via `ensureColumn` migrations at `db.ts:676-677`. Mac has no `summary`/`source` fields at all. Writes go through a dedicated `worker_thread` (`kgWorker.ts`) via `KgWriteQueue` (`kgWriteQueue.ts`) that coalesces concurrent saves (last-write-wins, shared resolve cycle for coalesced callers, re-read in full this session) and keeps an in-memory snapshot so the Electron main thread is never blocked by the delete+insert transaction. No gap. (An unrelated `dropIfMissingColumn(db, 'local_kg_nodes', 'summary')` at `db.ts:405` is dead-schema migration cleanup from an abandoned earlier KG experiment, not a contradiction of the `summary` column defined at line 456 — it only fires against a database that still has the old incompatible shape.)

### Backend knowledge-graph fetch/rebuild + client scoping

**What it is:** Pulling the server-synthesized (chat/memory-derived) graph and rebuilding it on demand.

**Where (Mac):** `MemoryGraphViewModel.fetchGraph()`/`rebuildGraph()` in `MemoryGraphPage.swift` — local SQLite first, falls back to `APIClient.shared.getKnowledgeGraph()`/`rebuildKnowledgeGraph()` with auth-restore retry loop.

**Windows status: Present-equivalent, arguably deeper (unchanged from the old audit's finding).** `knowledgeGraphClient.ts` calls the same `/v1/knowledge-graph` (+`/rebuild`, +`DELETE` — still explicitly unused, "exported for a later milestone (delete-graph UI); intentionally unused in Milestone A", re-read verbatim this session). `useMemoryGraph.ts` layers a persisted **onboarding "floor" graph** (you → language → apps, from the local `onboarding_kg_*` tables, which `db.ts` keeps deliberately separate from the chat-KG `local_kg_*` tables) under the account-wide server graph, and **scopes** the server graph down to entities referencing the user's *current* memory set (`scopeGraphToMemories` in `mergeGraphs.ts`) so deleted memories don't leave phantom nodes, refetching whenever the memory count changes. `useKnowledgeGraph.ts`'s `rebuild()` additionally polls the rebuild job to completion via `REBUILD_POLL_DELAYS_MS = [2000, 3000, 5000, 8000, 10000, 10000, 10000, 10000, 10000, 10000]` (≈78s total) until the node count is stable across two consecutive fetches before adopting the result, specifically to avoid flashing a half-rebuilt graph. No gap.

### Local semantic entity extraction ("digital profile")

**What it is:** Having an LLM read/derive from the indexed file metadata + memories and synthesize a personalized knowledge graph — people, organizations, projects, interests — plus a written "here's what I found about you" narrative, and (on Mac) presenting that as a first-run spectacle.

**Where (Mac):** `FileIndexingView.swift` — Stage 2 (`runAIExploration`/`startExplorationChat`, lines 366-390/501-556, 60%→90% of the onboarding loading bar): sends a detailed prompt instructing the chat AI to run 3-5 `execute_sql` queries over `indexed_files` (file types/folders/project indicators, recently modified files, tech-stack patterns), then call the `save_knowledge_graph` tool with entities and relationships. The live AI messages stream into a "Behind the scenes" info popover (line 129). After exploration: `appendExplorationToProfile()` appends the AI's findings to the persistent `AIUserProfileService` profile, and `injectDiscoveryCard()` puts a collapsible "Your Digital Profile" card into the chat transcript. Stage 3 then polls local SQLite for the graph the exploration just saved.

**Windows status: Present, as a silent background job — not an onboarding moment.** `src/renderer/src/lib/kgSynthesis.ts`'s `buildLocalGraph()` (present, largely unchanged in shape, since the Windows app's first commit on 2026-06-11) builds a deterministic technology/app/folder floor (`deriveTechNodes`/`deriveAppNodes`/`deriveFolderNodes` — real file extensions and installed apps only, an anti-hallucination guard) and then layers an **LLM-synthesized semantic entity graph** on top: `kgSynthesisPrompt.ts::buildSynthesisPrompt()` feeds the model up to 60 memory strings (`MAX_MEMORY_LINES`) + the recently-active-folders digest + installed-app names, and asks for `project | person | org | interest` nodes plus labeled relationship edges, forbidding invented technologies/apps/folders. A second prompt synthesizes a natural-language "overview" of the user, saved as a `card`-type KG node. The extraction call itself moved from a direct Claude Haiku chat-completion to the backend's `POST /v1/knowledge-graph/extract` route (`kgSynthesis.ts:126`) on 2026-08-09/10 (commits `d5598db7ab`/`ac1aa64fac`) — a provider change, not a capability change; the People/Orgs/Projects/Interests + relationships + narrative-overview shape has been present the whole time.

The gap is not the AI work — it's that none of it happens where or when Mac's does, and none of it is shown to the user. `buildLocalGraph()`/`maybeBuildLocalGraph()` are wired to run: `GRAPH_BUILD_DELAY_MS = 1800` (~1.8s) after the main app shell mounts, **post-onboarding**, via `useAppLifetimeJobs()` in `appLifetimeJobs.ts` (mounts "exactly once per signed-in, onboarded session," per its own comment, re-read verbatim this session); after screen-capture writes (`screenSynthesis.ts:92`, staleness-gated); from a background live-mirror timer (`LiveMirrorHost.tsx:25`, a 120s one-shot `setTimeout`); and manually from Settings' Advanced tab. `BuildProfileStep.tsx` — the actual onboarding "Discovery" step, re-read in full this session — never calls it; it only runs the mechanical file scan plus `addAppNodes` (see the progress-feedback section below). There is no live "Behind the scenes" message stream, no `AIUserProfileService`-equivalent persistent append, and no UI anywhere renders the synthesized overview text to the user; the `card`-type node is consumed exclusively as silent grounding context inside `localAgent.ts::snapshotSections()` (feeds the chat floor, never surfaced as its own card). So a Windows user gets the same underlying personalization signal in their chat's local context, but is never shown that it was built, when it was built, or what it says about them — the "wow, it already knows about me" moment Mac manufactures deliberately doesn't exist on Windows even though the substance behind it does.

**Value / notes:** M. The old "Absent — single largest gap" verdict from the 2026-08-20 audit was materially wrong: the actual entity-extraction and narrative-synthesis engineering already exists and has for the entire life of the Windows port. What's missing is presentation/timing — moving (or duplicating) the call into the onboarding flow and surfacing its result.

### Chat agent local-context enrichment (`execute_sql` agentic pre-step)

**What it is:** Before answering a chat message, having the LLM agent optionally run its own `execute_sql`/search queries against the local DB (files, KG, memories) to ground its answer in the user's actual local data — separate from the semantic-extraction background job above; this is the always-available runtime capability, mirroring Mac's standing tool.

**Where (Mac):** `ChatToolExecutor.swift` + `Generated/GeneratedToolExecutors.swift` — `execute_sql` (line 6 of the generated tool enum) is a standing capability available to chat at any time, not gated off; re-confirmed present and actively maintained this session (most recent touch to `ChatToolExecutor.swift` is 2026-08-20). The generated tool enum has no `query_kg` or `search_files` case at all — see the callout above.

**Windows status: Present-but-disabled (unchanged).** `src/renderer/src/lib/localAgent.ts` still implements the identical bounded agent loop (`{"action":"execute_sql", ...}` / `{"action":"search_memories", ...}` / `{"action":"final"}`, `MAX_ITERS = 2`, `AGENT_CALL_TIMEOUT_MS = 2_500`, calling `window.omi.kgExecuteSql`) — fully wired and tested. The module's own `ENRICH_ENABLED = false` constant (line 33) and its comment are unchanged: *"Floor-only mode… The `execute_sql` agent enrichment added up to `ENRICH_BUDGET_MS` of dead time before every message and, within that budget, usually got cut off mid-loop… So enrichment is OFF… Flip to true to restore the macOS-faithful agentic pre-step."* Chat still answers from the deterministic `snapshotSections()` floor. `query_kg`/`search_files` remain legacy no-op actions inside the loop ("Use execute_sql instead" — `localAgent.ts:164`); these are Windows-internal legacy names with no Mac-side counterpart at all (see the callout above), not an unverified parity delta as previously flagged. Separately, `AGENT_MODEL` was repointed from a hardcoded Haiku model id to the managed structured lane `'omi-structured'` on 2026-08-09 (commit `bce7414c5a`) — a routing change that doesn't touch `ENRICH_ENABLED` or any of this section's findings.

**Value / notes:** M. Self-documented, intentional simplification, not a bug — still a real behavioral gap from the "macOS-faithful" design the code itself references.

## Memory Graph visualization

### Physics model (3D vs. 2D-on-plane)

**What it is:** The force-directed layout algorithm positioning graph nodes in space.

**Where (Mac):** `ForceDirectedSimulation.swift` — genuine 3D physics (`SIMD3<Float>` positions, re-confirmed this session), Coulomb-like pairwise repulsion, spring attraction along edges, center gravity, damping, all three axes free; node size scales with connection count; auto-tunes repulsion/attraction/rest-length by node count; guarantees connectivity by bridging disconnected components to the user-anchor node. **Caveat found this session:** this is the *legacy* graph. `MemoryGraphPage.swift:27-34` now defines a `MemoryGraphPresentationMode` that resolves to `.canonicalAtlas` instead of `.legacyBrainMap` once the server exposes a `canonicalLifecycleExposed` capability — `.canonicalAtlas` renders an entirely different, cluster/territory-based view (`CanonicalMemoryAtlasView.swift`, actively developed through 2026-08-16) that this audit has not evaluated. These citations describe the fallback path only; see the callout section above.

**Windows status: Present-equivalent for the interactive viewer; the two decorative previews stay 2D by design.** `useGraphSimulation.ts`'s `GraphSimulation` class (constructor: `dimensions: 2 | 3 = 2`) genuinely runs `d3-force-3d` in 3 dimensions — real `x/y/z` positions, z-jittered seeding (`seedPositionNear`), a spherical (not planar) clamp in `clampPositions()`, and a dimension-aware layout cache key specifically so a 2D-settled layout can never be misadopted by a 3D scene. This shipped 2026-07-16/18 (`a1b6087a3a` "3D interactive Brain Map", `ec49e37229` "real 3D orbit, no fog blackout"). `BrainGraph.tsx` itself hard-codes `interactive ? 3 : 2` at the call site (line 540), so only the two non-interactive contexts — the Memories inline card and the onboarding map — ever pass 2D, which the code frames as a deliberate readability tradeoff for scenes the user cannot rotate to disambiguate.

Windows-only extras beyond Mac's (legacy) simulation, still present: per-node random size/radius jitter for a "cloud" look, a settled-layout cache keyed by node-set + dimensions + center id (skips re-running physics on remount), and a `reshuffle()` gentle in/out drift between onboarding screens that Mac's simulation has no equivalent of.

**Value / notes:** L — reads as parity for the viewer that matters (the interactive one) against the legacy Mac path; the previews' 2D choice is a considered, documented tradeoff rather than a gap. Not scored against the newer canonical atlas, which is out of scope for this pass.

### Interactivity + standalone full-screen viewer

**What it is:** Letting the user actually explore their knowledge graph — rotate, pan, zoom — outside of onboarding, plus a rebuild control.

**Where (Mac):** `MemoryGraphPage.swift` — a dismissible full-bleed SceneKit view (`MemoryGraphSceneView`, `scnView.allowsCameraControl = true`, native drag-to-rotate/scroll-to-zoom/right-drag-to-pan), with a rebuild button (spinner while rebuilding) and a dismiss control. **Corrected this session:** Mac no longer reaches this via a small embedded "inline card" on the Memories page — that surface (`MemoryGraphInlineCard`) was removed 2026-07-22 (commit `bdff578fd9`), before either audit pass. Brain Map is now its own destination in a `MemoryHubSwitcher` (`MemoryHubPage.swift`: Memories / Conversations / Brain Map, later joined by an Activity tab), always rendering the fully-interactive `MemoryGraphSceneView` — there is no separate non-interactive preview surface on current Mac at all (subject to the canonical-atlas caveat above, for accounts past that capability gate). `FileIndexingView`'s onboarding brain-map screen (line 189) shows the same `MemoryGraphSceneView` with an on-screen shortcuts legend.

**Windows status: Present-equivalent.** `BrainGraph.tsx`'s `interactive` prop still gates `<OrbitControls enablePan enableZoom enableRotate />` vs. a fixed `CameraRig`, and both small-preview call sites hard-code it off — `Memories.tsx:563` and `Onboarding.tsx:325` (independently re-confirmed this session, both still `interactive={false}`). A maximize button on the Memories inline card (`Memories.tsx:584-591`, added 2026-07-15 commit `16004ab810`, "expand affordance from the Memories brain-map card") navigates to `/knowledge-graph` (`routes/manifest.ts:118-124`), which mounts `KnowledgeGraph.tsx` → `KnowledgeGraphViewer.tsx` (added 2026-07-15, labels toggle added 2026-07-19). That viewer renders `BrainGraph` with `interactive` unconditionally true, full-bleed, sourced from the exact same `useMemoryGraph()` data the inline card uses, plus: a floating back/close button, a **rebuild** button wired to `useKnowledgeGraph().rebuild()` (spinner while rebuilding), a "Show all N / Show key 120" density toggle (the code's own comment cites a measured real account at ~188 nodes / ~474 edges, one 226-degree hub — re-read verbatim this session), and an independent "show all labels" toggle. The code's own comments describe this explicitly as "mirroring macOS's MemoryGraphPage chrome."

Net effect: a Windows user **can** drag/rotate/pan/zoom their knowledge graph and trigger a rebuild from the graph UI — just not from the small inline card itself, which stays a non-interactive preview. Since Mac itself dropped its own inline-card/full-page distinction on 2026-07-22 (Brain Map is now always-interactive, reached only via a hub tab), Windows's two-tier design is no longer mirroring a live Mac surface, but it still delivers the same end capability (an interactive, rebuildable graph reachable from the Memories area) that the tab delivers on Mac, so the verdict is unchanged.

**Value / notes:** — (no material gap against the legacy Mac path this audit evaluated). The onboarding brain-map screen still has no equivalent of Mac's on-screen shortcuts legend; minor, not worth a separate H/M/L line.

### Onboarding scan progress feedback

**What it is:** Live status while the file scan / AI exploration / KG build runs, so the user isn't staring at an indeterminate spinner.

**Where (Mac):** `FileIndexingView.swift` loading phase — per-folder status text ("Scanning ~/Documents · 1,234 files found"), a real 0-100% progress bar driven by actual scan/exploration/KG-build stage weights (0-60% scan, 60-90% AI exploration, 90-100% KG poll — line numbers re-confirmed this session), plus `OnboardingLoadingAnimation.swift`'s Canvas-based orbital ring whose filled arc tracks that percentage.

**Windows status: Present-but-weaker (unchanged).** `BuildProfileStep.tsx` (re-read in full this session) shows `OrbitScanner.tsx` (a comparable-looking SVG/CSS orbital-dots animation) as a purely indeterminate loop with no percentage — status text flips between "Scanning your projects and apps" and "Your workspace is mapped" only once the scan promise resolves (`runScan()`/`ensureIndexed()`), then reveals the final file count. Still no per-folder progress, no numeric percentage, and no live AI-exploration status shown here — consistent with the semantic-extraction job (see above) not running during this step at all; it runs later, silently, after onboarding finishes.

**Value / notes:** L.

## Spotted outside my scope

- **Rewind screenshot OCR embeddings** (`Rewind/Services/OCREmbeddingService.swift`) remain a related-but-separate feature from file indexing — no embeddings exist for *file content* on either platform (both `IndexedFileRecord`/`indexed_files` are metadata-only), so that's parity, not a gap, for this audit's scope. The `rewind` teammate's area.
- `AdvancedTab.tsx` (Windows Settings) still surfaces file-index stats (`fileIndex.filesIndexed`, `lastRunAt`) and a manual "Re-scan now" button (`rescan()` → `window.omi.indexFilesScan()`) — confirmed unchanged this session; didn't re-audit the rest of that settings surface for further Mac parity.
- `kgSynthesis.ts`'s background job is also triggered from `screenSynthesis.ts` and `LiveMirrorHost.tsx` (screen-capture/live-mirror subsystems) — those triggers are outside this audit's file-index/KG scope on the *producer* side; only the KG-consumer behavior was assessed here.
- **Mac's Canonical Memory Atlas** (`CanonicalMemoryAtlasView.swift`, `MemoryHubPage.swift`'s `brainMapDestination`, gated by `canonicalLifecycleExposed`) is a structurally different graph surface under active development on Mac (commits through 2026-08-16) that this audit did not evaluate against Windows at all — it may already be what a meaningful slice of Mac users see instead of the SceneKit force-directed graph this document compares against. A future pass should determine the rollout's current reach and whether it changes any verdict above.
