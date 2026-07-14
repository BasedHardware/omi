# Track 3 — Proactive Intelligence & Memory — Live Status

> Orchestrator status doc. Single source of truth for phase progress, decisions, and parked
> questions across this (long, unattended) session. Update as items complete.

Branch: `feat/win-proactive` (worktree `.worktrees/track3-proactive`, pushed to origin).
Worktree ports: renderer **5223**, CDP **9329**, profile `omi-windows-sandbox-track3-proactive`.
Mac reference (frozen ground truth): `.worktrees/mac-ref` @ tag `v0.12.72+12072-macos` (commit 50d264c9).

## Phase plan (dependency order)

- [ ] **P0 Ground truth** — 9 Sonnet extractors → `track3-ground-truth/*.md` (IN PROGRESS)
- [ ] **P0 Additive schema PR** (land FIRST): db.ts + types.ts + preload append-only block for
      profile / assistants / focus / insight / memory-extract / embeddings tables. Additive-only.
- [ ] **P1 AI User Profile** (enabler #1): wire get/update_ai_profile, 2-stage synthesis, daily cadence.
- [ ] **P2 AssistantCoordinator** (framework): throttling (per-assistant+global clocks, freq 0–5,
      suppression snooze→master→frequency), context-switch detection, backpressure.
- [ ] **P3 Focus assistant** + glow overlay.
- [ ] **P4 Insight assistant depth** (two-phase SQL+vision, backend-sync as memory, history UI).
- [ ] **P5 Continuous memory extraction** + embeddings (source-namespace key, count-guard, RAW-row pager).
- [ ] **P5b Screen task extraction** — GATE G-A (staged-tasks vs candidate/workstream).
- [ ] **P6 Auto daily goal gen + advice** — goal-completion uses BACKEND contract (C10, Mac wrong).
      Goals nav = GATE G-C.
- [ ] **P7 Unified connectors** — publish 3 entry points (Memories page / onboarding / Apps hub).
- [ ] **P8 Home widgets** WhatMattersNowSection + FocusedGoalsSection; delete legacy QuickTask/QuickGoals.
- [ ] **P9 Page surfaces** to Mac spec: Memories (filters, cards, detail sheet, undo toast, BrainGraph
      mount via props), Tasks (grouped-by-due; NOT rich multi-filter = G-D), Goals (G-C; emoji/gradient/confetti).

## Decisions & log

- **2026-07-14 setup**: worktree created, bootstrap OK, branch pushed. 9 ground-truth extractors spawned.
- **Cherry-pick a4c50bcb4 — REVISED to HOLD.** The commit is primarily *conversation/listen-path*
  device provenance (backend sync.py/transcribe.py/merge_conversations.py + settled Windows files
  omiListen.ts/apiClient.ts + web). Only `lib/clientDevice.ts` (a self-contained per-install
  device-id primitive) is Track-3-relevant and collision-free. Holding even that until the
  memory ground-truth confirms the backend `/v3/memories` contract actually carries per-device
  provenance fields — else the "This device" filter is dead UI and clientDevice.ts is dead code.
  See PARKED Q1.

## Ground-truth returns (as they land)

- **gt-tasks.md ✓** — Only ONE server staging model: `staged_tasks` (fully built, platform-agnostic,
  zero X-App-Platform refs). Routes: POST/GET/DELETE /v1/staged-tasks, PATCH /batch-scores,
  POST /promote, POST /{id}/promote, POST /migrate. Model: id/description/completed/due_at/source/
  priority/metadata/category/relevance_score(0-1000). Promote has dedup guard vs active action_items.
  **G-A DISSOLVED**: "candidate/workstream" are Mac UI/telemetry names, not backend models — build
  against staged_tasks; nothing to decide. Extraction (Mac TaskAssistant): whitelisted apps + 10-min
  timer, gemini-2.5-flash, 0.75 confidence, 8-iter tool loop (search_similar/search_keywords/
  no_task_found/extract_task/reject_task). Mac Tasks grouping = 4 buckets (Today/Tomorrow/Later/
  No-Deadline). **Windows Tasks 300-cap/no-refresh ALREADY FIXED** (commit d750654) — no work needed.
- **gt-goals.md ✓** — Backend truth: GoalUpdate accepts only {title,target_value,current_value,
  min_value,max_value,unit}; NO completion route; complete = PATCH /{id}/progress?current_value=target
  (Windows already correct; Mac completeGoal/getCompletedGoals are 400/404-broken — do NOT port).
  advice endpoint (path-only → {advice}) richer than Mac, uncalled on Windows = quick win. suggest =
  zero payload, backend truncates to 20 memories. Mac client-gen = 500 mem/100 convo/100 task/persona.
  Visual: emoji keyword-bucket default 🎯; progress = 5-bucket threshold colors (green#22C55E/lime
  #84CC16/yellow#FBBF24/orange#F97316/gray, NOT a gradient); confetti = 4-phase ~3.5s celebration.

- **gt-focus-glow.md ✓** — Focus rides shared 3s capture timer (×3 battery). gemini-2.5-flash via
  proxy /v1/proxy/gemini/models/{model}:generateContent thinkingBudget 0. Schema {status:
  focused|distracted, app_or_site, description, message?}. Notify only on state transitions; freq
  0-5 (0 off/1 60m/2 30m/3 10m/4 3m/5 none), bar-only. Table `focus_sessions`(id,screenshotId,
  status,appOrSite,description,message,durationSeconds,backendId,backendSynced,createdAt,windowTitle)
  + dual-write to `memories` (tags focus/focused|distracted/app:X) via generic createMemory (no
  dedicated focus backend API). Daily score = focusedMin/(focusedMin+distractedMin)*100. Glow = 4
  click-through edge windows, animated gradient hue focused 0.38 / distracted 0.0, 3.5s, 3×1.5s pulse.
- **gt-memextract-embeddings.md ✓** — MemoryAssistant: newest-1 frame buffer, interval 600s, gated
  isEnabled&&notificationsEnabled, Gemini Flash + JPEG + last-20 mem dedup. Schema {has_new_memory,
  memories[{content ≤15w, category system|interesting, source_app, confidence}], context_summary,
  current_activity}; only first used; confidence ≥0.7. Save local→createMemory→markSynced. Embeddings:
  /v1/proxy/gemini/models/{model}:embedContent(s), 3072-dim L2-norm, index cap 5000 over action_items
  +staged_tasks. Bug-fixes to replicate: composite key {source,id}; guard embeddings.count==texts.count.
  Pager: two cursors (filtered vs RAW-count advance). **Windows: bulk pager already fixed; REAL bug =
  hooks/useMemories.ts:43-58 single limit=500/offset=0, Memories page caps ~5000 → fix in my file.**

- **gt-windows-inventory.md ✓** — db.ts new-table pattern = `CREATE TABLE IF NOT EXISTS` in bootstrap
  (mirror `insights` table + INSIGHT_COLUMNS + recentInsights). `insights` table ALREADY EXISTS →
  insight depth extends it. dbMigrations MIGRATIONS has one entry (v1); NET-NEW tables need no
  migration entry (avoids version contention). Renderer patterns: A=local SQLite via IPC
  (window.omi.X→ipc→db.ts), B=renderer→backend axios (memories/goals/tasks today, no local table).
  Goals/Tasks have NO hooks (inline in pages; Goals completion duped in QuickGoalsWidget).
  **CORRECTION — MemoryValueRequest is a PHANTOM**: generated client AND backend memories.py:815/843
  both use query-param `value: str`; no MemoryValueRequest type exists anywhere. Windows edit/visibility
  is already correctly wired (useMemories PATCH query-param) — C9 gap is UI-button-only. DO NOT regen
  toward JSON body (would 422). **Regen IS still needed** — staged_tasks bindings absent from client.
  Real Memories-page pager bug = useMemories.ts:43-58 (single limit=500/offset=0). AI-profile
  get/update present in client (update = JSON body). Goal advice/suggest present, uncalled.

## P0 additive-schema PR — IN PROGRESS (Opus agent afe2c9b)
3 net-new tables via CREATE TABLE IF NOT EXISTS (no migration entry): `ai_user_profiles`,
`focus_sessions`, `task_embeddings` (composite (source,item_id) PK per Mac bug-fix). + db.ts CRUD +
shared/types.ts records + tests. Assistant *settings* → use existing Windows settings store (not SQLite).

- **gt-screenfeed.md ✓ (KEY UNBLOCK)** — Capture: renderer RewindCaptureHost getUserMedia 720p/1fps
  JPEG → IPC rewind:saveFrame → main ingestRewindFrame → file + `rewind_frames` row. Read-only seam
  (exported, ZERO Track-4 edits): `latestRewindFrame()`, `listRewindFrames()`, `getCurrentScreen()`
  (main/rewind/currentScreen.ts, ~1s-fresh OCR text). Active window: main/usage/nativeForeground.ts
  (koffi/user32) with event-driven `subscribeForegroundChange()` (SetWinEventHook) — built, unused,
  reusable for context-switch detection. NO push "new frame" event → Track 3 polls latestRewindFrame()
  on own cadence + diffs id. Existing insight ENGINE = renderer/src/lib/insightEngine.ts (mine; 15-min
  poll, TEXT-only, no vision) → upgrade to two-phase SQL+vision. main/insight/** = display-only.
  **ARCH DECISION (tentative): coordinator + Focus/Memory/Task assistants live in `main/assistants/**`**
  (JPEG buffers + native foreground hook + SQLite all in main), polling the read-only seam. Finalize
  with profile+coordinator + insight extractor detail.

- **gt-connectors.md ✓** — Mac Gmail/Cal = cookie-scrape hack; **Windows AHEAD**: real Google OAuth2
  PKCE + REST already built (main/integrations/oauth.ts, google.ts, flag VITE_ENABLE_GOOGLE_INTEGRATION)
  → EXTEND, don't port Mac. Import write path: POST v3/memory-imports/batch (max 100, chunked, retry
  429/5xx) → fallback POST v3/memories/batch on 404/403 memory_import_requires_canonical (implement
  BOTH). Synthesis = 1 claude-haiku call → ~10-15 memories + 2-5 tasks. X: GET /v1/x/oauth-url →
  backend callback → poll /v1/x/connection-status. MCP: server {base}v1/mcp/sse; mint POST /v1/mcp/keys
  {name}→{key}. CLI writers (idempotent, %USERPROFILE%): Claude Code ~/.claude.json mcpServers.omi-memory
  (http+bearer); Codex `codex mcp add ... npx -y mcp-remote <url> --header "Authorization: Bearer <key>"`;
  OpenClaw ~/.openclaw/openclaw.json + SOUL.md note; Hermes ~/.hermes/config.yaml mcp_servers + SOUL.md.
  ChatGPT/Claude = public PKCE (omi-chatgpt-prod/omi-claude-prod, display URL+clientId). Notion =
  memory-pack only. Port ConnectorImportRunner shape as shared run-state store. Platform 'windows'
  recognized backend-side, no connector gating. 3 entry points mount one capability module (interface
  in doc): listDestinations/runImport/getExportStatus/executeExport/ensureMcpKey/getRunState.

## Parked questions for Chris (batch — do not block)

- **Q1 (a4c50bcb4 full cherry-pick):** Should the full conversation-provenance commit (backend +
  listen-socket wiring in settled files) be landed by Track 3, or does its capture/backend half
  belong to the capture/settled owners? Track 3 only needs the `clientDevice.ts` primitive IF the
  memory backend carries device provenance (checking).
- **G-A — RESOLVED by evidence (no longer parked):** build task extraction against `staged_tasks`.
  No candidate/workstream backend model exists. (Kept here only as a record.)
- **G-C (Goals nav placement).**
- **G-D (Tasks rich multi-group filter — skip for now).**
