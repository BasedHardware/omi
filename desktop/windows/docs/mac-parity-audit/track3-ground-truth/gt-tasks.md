# Track 3 Ground Truth — Tasks (screen extraction + staged-tasks contract + Tasks page UI)

Verified directly against source (not doc summaries). Sources:
- Mac (frozen v0.12.72): `.worktrees/mac-ref/desktop/macos/Desktop/Sources/...`
- Backend: `.worktrees/track3-proactive/backend/...`
- Windows: `.worktrees/track3-proactive/desktop/windows/src/renderer/src/...`

Audit doc checked against: `desktop/windows/docs/mac-parity-audit/02-proactive-tasks-goals.md` — its claims about the extraction pipeline, tool schema, and Windows Tasks.tsx 300-cap/staleness are accurate as written **at the time it was authored**, with one correction below (the 300-cap bug is now fixed on this branch).

## (A) Screen-based extraction + staged-tasks backend contract

**Mac local pipeline** (`TaskAssistant.swift`, `TaskAssistantSettings.swift`):
- Whitelisted apps (`TaskAssistantSettings.defaultAllowedApps`): Telegram, WhatsApp (+ hidden-LTR-mark variant), Messages, Slack, Discord, zoom.us, Chrome/Arc/Safari/Firefox/Edge/Brave/Opera, Notes, Superhuman. Browser apps additionally filtered by `defaultBrowserKeywords` (Gmail/Slack/Jira/Linear/etc., 30+ keywords).
- Cadence: `defaultExtractionInterval = 600.0` (10 min fallback timer) + context-switch trigger + fast-path (~15s) for messaging apps (per audit; confirmed constant exists, fast-path constant not directly greped but referenced in comments).
- Model: **Gemini**, not Claude — `GeminiClient(apiKey:model: ModelQoS.Gemini.taskExtraction, fallbackModel: "gemini-2.5-flash")` (TaskAssistant.swift:173).
- `defaultMinConfidence = 0.75` (TaskAssistantSettings.swift:113), user-configurable.
- Tool-calling loop, **exactly 8 iterations max** (`toolLoop: for iteration in 0..<8`, TaskAssistant.swift:1059), 5 tools confirmed by grep: `search_similar`, `search_keywords`, `no_task_found`, `extract_task`, `reject_task`. `forceToolCall: iteration == 0`. Loop explicitly continues after `extract_task`/`reject_task` (asks "is there another commitment?") rather than stopping — multi-task-per-frame extraction confirmed in prompt text (TaskAssistant.swift:1185-1232).
- Title validation: prompt instructs "Verb-first task title, 6-15 words... MUST name a specific person/project/artifact" (TaskAssistant.swift:995) — matches audit's "≥6 words + proper noun" claim.
- `TaskSourceClassification` (category/subcategory) confirmed in `TaskModels.swift`: categories `direct_request/self_generated/calendar_driven/reactive/external_system/other`, each with 2-3 valid subcategories (message/meeting/mention, idea/reminder/goal_subtask, etc.).
- `TaskClassification` (personal/work/feature/bug/code/research/communication/finance/health/other) — `agentCategories = [.feature, .bug, .code]` trigger Claude Code agent, but `shouldTriggerAgent` is hardcoded `true` for all (comment says "any category can trigger").
- Extraction persists locally via `StagedTaskStorage.swift` (GRDB) then syncs to backend `/v1/staged-tasks` via `ScreenCandidateAdapter.swift`.

**Backend contract — `/v1/staged-tasks`** (`backend/routers/staged_tasks.py`, `backend/database/staged_tasks.py`, `backend/models/staged_task.py`) — **this already exists server-side, is not platform-gated, and is fully implemented**:
- `POST /v1/staged-tasks` — create (dedup by normalized description at creation time).
- `GET /v1/staged-tasks?limit&offset` — paginated list, `has_more` computed via `limit+1` fetch trick. Response: `StagedTaskListResponse{items, has_more}`.
- `DELETE /v1/staged-tasks` — clear all active (uncompleted) staged tasks for user.
- `DELETE /v1/staged-tasks/{task_id}` — delete one.
- `PATCH /v1/staged-tasks/batch-scores` — bulk `relevance_score` update (0-1000 int), used by the client-side prioritization pass.
- `POST /v1/staged-tasks/promote` — promote the single top-ranked (lowest `relevance_score`, ascending sort = most important first) active staged task to an `action_item`.
- `POST /v1/staged-tasks/{task_id}/promote` — promote a specific staged task by id.
- `POST /v1/staged-tasks/migrate` — one-time migration moving excess AI-sourced `action_items` (source contains `'screenshot'`) into `staged_tasks`, keeping top 3.
- `POST /v1/staged-tasks/migrate-conversation-items` — moves conversation-derived action items (has `conversation_id`, no `source`) into staged_tasks.

`StagedTask` model fields (`models/staged_task.py`): `id, description, completed, created_at, updated_at, due_at?, source?, priority?, metadata?, category?, relevance_score? (0-1000)`. **`relevance_score` is present** (confirms audit's claim it exists).

**Promote flow** (`database/staged_tasks.py::promote_staged_task`): staged→action_item is NOT purely mechanical — it has a dedup guard: before creating a new `action_item`, it checks `get_active_action_item_by_description` (case-insensitive, `[screen]`-marker-stripped normalization) and if a match exists, merges enrichment fields (`due_at`/`priority`/`category`) into the existing item instead of creating a duplicate, marking the staged task `completed=True, promotion_skipped='duplicate', promoted_to=<existing_id>`. Otherwise builds `action_item` from staged fields (`from_staged: True` marker) via `action_items_db.create_action_item`.

**Platform gating check**: grepped `routers/staged_tasks.py` and `database/staged_tasks.py` for `X-App-Platform`/`platform` — **zero matches**. The staged-tasks router/db layer has no platform awareness at all; it is uid-scoped only. Nothing here would reject or special-case a Windows client. (This is a different subsystem from the "platform-variant divergence" issue found elsewhere in this project's memory — that was about conversation/plan-catalog payloads, not staged-tasks.)

### DECISION GATE G-A — resolved by evidence, not a live migration

The brief's premise ("Mac is mid-migration server-side between staged-tasks and a Candidate/workstream model") **does not match what's in source**. Evidence:
1. **Server-side**: grepped the entire `backend/` tree for `Candidate|Workstream|candidate|workstream` — the ~50 hits are all in unrelated subsystems (memory ingestion, working-memory candidate schema, hybrid retrieval, promotion_proposals for the *memory* domain, etc.). **Zero backend hits reference a task/staged-task "Candidate" or "Workstream" model.** There is exactly one task data model server-side: `staged_tasks` → `action_items`. No competing or successor schema exists.
2. **Client-side "Candidate" and "Workstream" are two unrelated concepts, neither of which is a backend model migration:**
   - `TaskIntelligenceAttributionEvent` (`TaskModels.swift`) uses `candidateCaptured`/`candidateResolved` as **attribution/analytics event names** for screen-extracted staged tasks under review (accepted/rejected/expired) — this is telemetry vocabulary, not a data model.
   - `SuggestedTasksSection.swift` / `SuggestedTasksStore` (`MainWindow/Tasks/`) render a "Suggested" quiet-capture UI whose items are called `SuggestedCandidate` — this is the UI-layer name for a **staged task pending review** (do-now / later / dismiss actions), not a different backend entity.
   - `TaskWorkstreamContinuity.swift` (`ProactiveAssistants/Assistants/TaskAgent/`) is about the **Task Agent** (Claude Code CLI in tmux) persisting/restoring its own long-running coding-agent session across app restarts (`prepare_workstream_continuity`, `persist_workstream_continuity`, kernel bridge calls) — a completely separate subsystem (autonomous code execution) from task extraction/staging/promotion.
3. **Conclusion (evidence, not a decision):** there is no server-side migration in flight for the staged-task model. `/v1/staged-tasks` is the one and only task-staging contract, is fully built, unused by Windows, and platform-agnostic. Windows can build directly against it with no ambiguity from a competing schema. **Flagging this back to Chris only because the gate explicitly said not to decide it** — but the source shows nothing to decide between; there is one model.

## (B) Tasks Page UI (Mac) — `TasksPage.swift`, `SuggestedTasksSection.swift`

**Due-date grouping** (`TaskCategory` enum, `TasksPage.swift:10-14`) — **only 4 buckets, no separate "Overdue" bucket**:
```
today = "Today", tomorrow = "Tomorrow", later = "Later", noDeadline = "No Deadline"
```
(Overdue items apparently fold into "Today" — not confirmed further; not in scope to trace `getOrderedTasks` bucketing logic beyond the enum.) This differs from Windows' 5-bucket scheme (`overdue/today/tomorrow/upcoming/nodate`, `Tasks.tsx` lines 129-148) — Windows already has a finer grouping than Mac in this one respect.

**Rich multi-group filter surface** (`TaskFilterGroup` enum, `TasksPage.swift:60-66`) — **GATED per brief instruction G-D, reported not built**:
```
status, "Date Range", category, source, priority, origin
```
`TaskFilterTag` (`TasksPage.swift:69-110`) enumerates: status (`todo/done/removedByAI/removedByMe`), category (10 values matching `TaskClassification`), source (`sourceScreen/sourceOmi/sourceDesktop/sourceManual/sourceOmiAnalytics`), priority (`high/medium/low`), date (`last7Days`), origin (6 values matching `TaskSourceCategory`). This is a large filter chip UI — explicitly out of scope per the brief's gate; do not build.

**Inline create**: `viewModel.isInlineCreating` + `InlineTaskCreationRow` at top of list (Cmd+N shortcut implied by comment), supports inserting after a specific task (`inlineCreateAfterTaskId`).

**Suggested-tasks quiet-capture** (`SuggestedTasksSection.swift`): shows a "Suggested" card group above the main list (hidden when filtered to done-only/deleted-only or in multi-select mode) with a count badge and "Quietly captured for your review" subtitle. Each `SuggestedCandidateCard` offers `onDoNow(editedTitle)`, `onLater`, `onDismiss(reason)` — a lightweight per-card action set (not a full detail sheet). Presented-impression tracked via `.task { await store.presented(candidateID:) }`.

**Detail sheet**: `TaskDetailViews.swift` exists (not read in full — file confirmed present, contents out of scope for this pass beyond confirming it's the filter/detail companion to `TasksPage.swift`).

**Sort/indent/drag-reorder**: confirmed in `tasksListView` — `viewModel.getIndentLevel`, `incrementIndent`/`decrementIndent`, `onMoveTask`/`onDragStarted`/`onDragEnded`/`onDragHoverChanged` full drag-and-drop with indent levels 0-3 (matches `indent_level` field, `ge=0, le=3`, in backend `UpdateActionItemRequest`).

**Keyboard navigation**: `keyboardSelectedTaskId`, `isKeyboardSelectedFor`, modifier-flag handling (`event.modifierFlags.intersection(.deviceIndependentFlagsMask)` at line 1102) — present but not traced key-by-key.

## Task endpoints (correct contract, confirmed from `routers/action_items.py`)

- `GET /v1/action-items?limit(1-500,default 50)&offset&completed&conversation_id&start_date&end_date&due_start_date&due_end_date` → `{action_items: [...], has_more}`. `has_more` is computed by checking if a result-length equals `limit`, then doing a 1-item lookahead fetch at `offset+limit` — a real pagination contract, not a hard cap.
- `POST /v1/action-items` — create, content-idempotent via SHA-256 of `(uid, normalized description)`.
- `PATCH /v1/action-items/{id}` — general update (description/completed/due_at/exported/sort_order/indent_level).
- `PATCH /v1/action-items/{id}/completed?completed=bool` — dedicated complete/uncomplete toggle (query param, not body).
- `DELETE /v1/action-items/{id}` — 204, hard delete (no soft-delete/"removed by me" flag server-side — Mac's `removedByAI`/`removedByMe` filter distinction is client-side-only bookkeeping, not a backend field visible in `ActionItemResponse`).
- `POST /v1/action-items/batch`, `PATCH /v1/action-items/batch` (sort_order/indent_level), `POST /v1/action-items/batch-delete`, share/accept endpoints also present.

## Windows current-state verification — 300-cap / no-refresh claims

**Already fixed on this branch** (`desktop/windows/src/renderer/src/pages/Tasks.tsx`, verified by reading the full file + git log):
- `git log` on this file shows commit `d750654` (2026-07-13, "fix(windows): Tasks page 300-item cap and permanent staleness") — **this is the exact bug the audit doc describes, already remediated before this ground-truth pass**.
- Current code (`Tasks.tsx:37-58`, `fetchAllActionItems`): pages through `/v1/action-items` following `has_more`, `TASKS_PAGE_SIZE = 100`, `pageCap = 100` (i.e., up to 10,000 items) — no 300-item hard cap.
- Auto-refresh: mount-time fetch (`useEffect` at line 186) **and** a `window.addEventListener('focus', ...)` refetch (`Tasks.tsx:209-215`) — so switching away and back to the Tasks page (or to the app) re-fetches. Comment at line 181-185 explicitly documents this was the fix for "a revisit used to stick with whatever was cached."
- **Conclusion: the audit's 300-cap/no-refresh claims were accurate when written but are stale now — no further Windows work needed for this specific pair of bugs.** (Verify this wasn't reverted before relying on it further; last checked commit `d750654`.)

## Summary of what Windows should build against (no gate blocking this)

- `/v1/staged-tasks` is fully built, unused, platform-agnostic — safe to consume directly (list w/ pagination, promote, delete, batch-scores if a prioritization pass is ever built).
- `/v1/action-items` contract (list/create/update/complete-toggle/delete) is already correctly wired in Windows `Tasks.tsx` — no gap there.
- Mac's due-date grouping is simpler (4 buckets, no explicit overdue) than Windows' current 5-bucket scheme — no parity action needed, Windows is arguably ahead here.
- The rich multi-group filter UI (`TaskFilterGroup`/`TaskFilterTag`) is explicitly gated (G-D) — do not build without further sign-off.
