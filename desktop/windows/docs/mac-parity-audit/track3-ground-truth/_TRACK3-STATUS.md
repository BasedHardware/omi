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

## Parked questions for Chris (batch — do not block)

- **Q1 (a4c50bcb4 full cherry-pick):** Should the full conversation-provenance commit (backend +
  listen-socket wiring in settled files) be landed by Track 3, or does its capture/backend half
  belong to the capture/settled owners? Track 3 only needs the `clientDevice.ts` primitive IF the
  memory backend carries device provenance (checking).
- **G-A — RESOLVED by evidence (no longer parked):** build task extraction against `staged_tasks`.
  No candidate/workstream backend model exists. (Kept here only as a record.)
- **G-C (Goals nav placement).**
- **G-D (Tasks rich multi-group filter — skip for now).**
