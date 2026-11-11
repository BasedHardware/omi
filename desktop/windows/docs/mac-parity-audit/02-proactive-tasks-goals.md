# Mac→Windows Parity Audit — Proactive Assistants: Tasks & Goals

> **Re-audit of 2026-08-22.** The 2026-08-20 version of this file is materially stale: it
> called several features "Absent" that had shipped on Windows *weeks* earlier (screen-based
> task extraction landed 2026-07-15; automatic goal generation, stale-goal cleanup, the goal
> celebration overlay, and the goal-insight panel all landed 2026-07-15 too), and it called the
> AI user profile "Mac-local-only" nine days after a shared Mac+Windows synthesis module shipped
> (2026-08-09). This version re-verifies every claim against current source (`git log` dates
> included) rather than trusting the previous pass. See "Changed since the 2026-08-20 audit"
> below for the full list.
>
> Scope: AI task extraction/dedup/prioritization/promotion, the terminal + chat "task agent,"
> and AI goal generation/advice/progress-tracking. Windows baseline checked: the whole
> `desktop/windows/src/main/assistants/{tasks,goals,aiUserProfile}/` trees (extraction loop,
> prompt, tool backends, context assembly, create/promote lifecycle, goal generation/schedule/
> stale-cleanup), `src/main/tasks/{taskEmbeddingService,taskSyncEngine}.ts`,
> `src/main/ipc/{tasks,taskStore,db}.ts`, the renderer pages/widgets
> (`pages/{Tasks,Goals}.tsx`, `components/home/{QuickTaskWidget,QuickGoalsWidget}.tsx`,
> `components/goals/{GoalCelebration,GoalInsightPanel}.tsx`,
> `components/onboarding/{GoalStep,AutoCreatedTasksStep}.tsx`), and the coding-agent/ACP tree
> (`src/main/codingAgent/*`, `src/renderer/src/lib/agentTask.ts`) to check whether it is wired to
> any task-specific surface. Backend checked directly where Windows depends on it:
> `backend/routers/{goals,staged_tasks}.py`, `backend/utils/llm/goals.py`,
> `backend/utils/conversations/process_conversation.py`, `backend/routers/chat.py`, and (briefly)
> the newer `backend/utils/task_intelligence/*` "Candidates" system that `staged_tasks.py` now
> sits on top of. `git log --format=%ad -1` on every cited file establishes ship date relative to
> the 2026-07-19 coordinator landing and the 2026-08-20 audit date.

## Changed since the 2026-08-20 audit

- **Screen-based AI task extraction is fully present, not absent, and shipped 2026-07-15** — over
  five weeks before the audit that called it "Absent." `src/main/assistants/tasks/` is a
  line-for-line port: the same 15-app whitelist + 7-browser keyword filter
  (`appLists.ts`), the same context-switch/fallback/messaging-fast-path triggers with a
  per-window dedupe TTL (`taskAssistant.ts`), the same 5-tool (`search_similar`,
  `search_keywords`, `extract_task`, `reject_task`, `no_task_found`) up-to-8-iteration
  tool-calling loop (`loop.ts`, `tools.ts`), the same title-specificity validator and 0.75
  confidence gate (`models.ts`, `create.ts`), and the same source-category/subcategory
  classification. This was the single largest claimed gap in the old file; it does not exist.
- **The staged→action-item promotion pipeline is present**, including the 30s inline debounce,
  a 60s-floor backoff-ladder safety-net timer, and a startup promote
  (`assistants/tasks/promotionService.ts`, shipped the same day as the old audit,
  2026-08-20 — a same-day miss, not a stale one, but still wrong now). It does **not** fire a
  native/toast notification on promotion (confirmed still true, see below) — that specific
  sub-gap survives even though the pipeline around it doesn't.
- **The AI user profile is present and shared**, not "Mac-local-only" as the old file's
  cross-reference section claimed. `assistants/aiUserProfile/{service,synthesis}.ts` shipped
  2026-08-09 as an explicit "SSOT AI user profile synthesis for Mac and Windows" and is read
  by the task-extraction context assembler (`tasks/context.ts`).
- **Automatic daily goal generation and stale-goal auto-completion are both present**, shipped
  2026-07-15 (`assistants/goals/{generate,schedule,staleCleanup}.ts`). The trigger mechanism
  is a deliberate, documented deviation from Mac (a 4-hour heartbeat + once-per-calendar-day
  gate, because Windows main has no per-conversation hook) but the net behavior — silently
  generate a goal from rich local context when the user has fewer than 3 active goals and
  hasn't generated today, and delete a zero-progress auto-goal after 3 days of staleness so the
  gate doesn't clog — matches Mac's.
- **Goal suggestion richness is present on the Goals page**, and in one respect *exceeds* Mac:
  the "Suggest" button (`Goals.tsx`) now calls a local two-phase generate→preview→create flow
  (`goals/generate.ts::generateGoalCandidateNow` / `acceptGoalCandidate`) that assembles the
  same five-source context Mac's `GoalsAIService.generateGoal` does (persona, 500 memories, 100
  conversations, 100 tasks, full goal history) and lets the user see and reject the suggestion
  before it's created — Mac blind-creates. The old audit's "thin `/v1/goals/suggest`" citation
  is stale for this surface. **Nuance the old audit couldn't have known to look for:** the Home
  page's one-tap widget (`QuickGoalsWidget.tsx::generate`) was *not* upgraded — it still calls the
  thin backend `GET /v1/goals/suggest` and blind-creates with no preview, so the two "generate a
  goal" entry points on Windows now have visibly different quality, an inconsistency worth its
  own line item below.
- **AI goal insight/advice has a UI now.** `components/goals/GoalInsightPanel.tsx` (shipped
  2026-07-15) wires a per-goal "Get insight" sheet to `GET /v1/goals/{id}/advice` — the old
  audit's "not exposed in Windows UI at all" is no longer true.
- **Goal completion celebration is a full-screen 4-phase confetti overlay**, not a plain toast.
  `components/goals/GoalCelebration.tsx` (shipped 2026-07-15, wired into `Goals.tsx`) replicates
  Mac's dim→confetti→text→fade choreography timing-for-timing.
- **Goal progress auto-extraction resolves to Present**, not "need to confirm." The old audit
  correctly flagged this as needing separate backend verification rather than guessing; that
  verification is done here: `backend/utils/llm/goals.py::extract_and_update_goal_progress` is
  called from both `backend/utils/conversations/process_conversation.py:737` (every processed
  conversation, any platform) and `backend/routers/chat.py:449` (every chat message, any
  platform) — a backend-shared pipeline that predates this feature area's Mac implementation by
  months and requires zero Windows client code to already apply to Windows users.
- **The old audit's own aside about the ACP/coding-agent integration is now wrong.** It said
  Windows' "unrelated ACP/coding-agents integration... is separately tracked as not
  implemented." `src/main/codingAgent/` (Claude Code / Codex / OpenClaw / Hermes adapters over
  ACP) is implemented and shipped 2026-07-15, and is reachable from ordinary chat via
  `lib/agentTask.ts`'s delegation-phrase detector. It is real, but — confirmed below — it is not
  wired to any task-row action, so "Terminal Task Agent" and "Execute" remain genuine Tasks-area
  gaps; only the framing of *why* they're gaps changes (missing wiring, not a missing engine).
- **Corrected, not reversed:** "no staged-tasks concept at all" (old audit, promotion pipeline
  section) is wrong on its face — Windows has a local `staged_tasks` SQLite table and a synced
  backend row per extracted task (`create.ts`, `ipc/taskStore.ts`) — but the richer per-item
  filter/sort/tag surface the old audit was really describing (category/source/priority/origin
  chips, manual sort/indent) is still genuinely absent from `Tasks.tsx`; only the top-line
  "no staged-tasks concept" phrasing was wrong, not the underlying UI-richness gap.
- **Confirmed still accurate, unchanged:** the per-task "Investigate" chat sidebar, a
  task-row-triggered terminal Claude Code agent, daily recurring-task re-investigation, a
  task-row "Execute" agentic action, the task-agent status indicator, the dev-only prompt editor
  and historical test runner, client-side staged-task semantic deduplication, and client-side
  relevance re-prioritization are all still absent on Windows. One infra note worth flagging for
  whoever picks up the per-task-chat gap: `src/main/agentKernel/types.ts` already defines a
  `task_chat` surface kind in its type system (used nowhere else, no renderer reference) — the
  substrate has a slot for this feature reserved, even though nothing has been built on it.

## Summary table

| Feature | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Screen-based AI task extraction (whitelisted apps, 5-tool loop, confidence gate) | `TaskAssistant.swift`, `TaskAssistantSettings.swift` | **Present** — `assistants/tasks/{taskAssistant,loop,tools,models,create,appLists}.ts`, shipped 2026-07-15 | — (closed) |
| Task source classification (category/subcategory) | `TaskModels.swift` | **Present internally** — captured + stored in staged/backend metadata (`create.ts`); not surfaced as a filter chip in `Tasks.tsx` | L |
| Staged-task semantic deduplication (hourly Gemini pass over the whole staged pool) | `TaskDeduplicationService.swift` | **Absent** on Windows (no client job). Backend has only a lightweight exact-normalized-string duplicate guard at promote time (`routers/staged_tasks.py` via `candidate_service`), not a semantic hourly pass | M |
| Task relevance prioritization (hourly re-rank) + daily AI user profile | `TaskPrioritizationService.swift`, `AIUserProfileService` | **Absent** as a ranking job — `relevance_score` is a real synced column (`ipc/taskStore.ts`) but nothing on Windows computes it; `Tasks.tsx` still sorts by due-date bucket only. AI user profile itself **is present** (`assistants/aiUserProfile/`, shared w/ Mac, 2026-08-09) and already feeds task-extraction context | M |
| Staged→action-item promotion pipeline | `TaskPromotionService.swift` | **Present** — inline post-extraction promote, 30s debounce, 60s-floor backoff safety net, startup promote (`assistants/tasks/{create,promotionService}.ts`, 2026-08-20). Native/toast notification on promotion is the one piece still missing (explicit code comment: "No glow, no notification") | M (partial) |
| Terminal "Task Agent" (Claude Code in tmux, tied to a specific task) | `TaskAgentManager.swift`, `TaskAgentSettings.swift` | **Absent for tasks specifically.** The underlying engine exists generally (`codingAgent/` ACP adapters, chat-delegation via `agentTask.ts`) but nothing in `Tasks.tsx` invokes it | M |
| Per-task "Investigate" AI chat sidebar | `TaskChatCoordinator/Runtime/State.swift`, `TaskChatPanel.swift` | **Absent** — no `chatSessionId`, no "Investigate" action in `Tasks.tsx`. A `task_chat` surface kind is reserved in `agentKernel/types.ts`'s type system but has zero wiring | H |
| Daily recurring task auto re-investigation | `TaskChatCoordinator.investigateInBackground`, `DailyTaskCreationSheet.swift` | **Absent** — no recurrence field surfaced anywhere client-side (the backend wire type carries `recurrence_rule`/`recurrence_parent_id` unused) | M |
| "Execute" full-desktop agentic task execution from a notification | `ProactiveTaskExecute.swift` | **Absent as a task action.** A general desktop-automation "agent kernel" / control-tools stack now exists on Windows (`agentKernel/controlTools.ts`, `automation/foregroundTarget.ts`, shipped 2026-07-29) but no task-row "Execute" routes into it | M |
| Task agent status indicator / terminal icon on task rows | `TaskAgentViews.swift` | **Absent** | L |
| Rich Tasks page: filter tags (source/category/priority/origin), sort/indent, "Removed by AI" vs "Removed by me" | `TasksPage.swift`, `TaskDetailViews.swift`, `TaskFilterTag` | **Partial**, mostly unchanged from the old audit — `Tasks.tsx` still has only open/done/all + due-date bucketing. (Correction: Windows *does* have a local staged-tasks concept now — the old audit's "no staged-tasks concept at all" was wrong — it's the filter/sort UI on top of it that's still missing, same as before) | M |
| Dev tools: prompt editor + historical-screenshot test runner | `TaskPromptEditorWindow.swift`, `TaskTestRunnerWindow.swift` | **Absent** (dev-only, no user-facing loss) | L |
| Automatic daily goal generation (rich local context) + stale-goal auto-completion | `GoalGenerationService.swift`, `GoalsAIService.generateGoal` | **Present** — `assistants/goals/{generate,schedule,staleCleanup}.ts`, shipped 2026-07-15. Trigger mechanism differs (4h heartbeat + calendar-day gate vs. Mac's per-conversation hook) but net behavior matches | — (closed) |
| Goal suggestion richness (memories+conversations+tasks+persona+goal history, task linking) | `GoalsAIService.swift`, `GoalPrompts.generateGoal` | **Present, and ahead of Mac on the Goals page** (generate→preview→create; Mac blind-creates). Task linking is a documented no-op — the live backend has no `goal_id` field on action items. **Still weaker on the Home widget**: `QuickGoalsWidget.tsx` calls the thin `GET /v1/goals/suggest` with no preview — the two "generate" entry points on Windows are now inconsistent with each other | M (was H; mostly closed, one inconsistency remains) |
| AI goal insight/advice ("what should I do this week") | `GoalsAIService.getGoalInsight` (local) vs `GET /v1/goals/{id}/advice` (backend, richer) | **Present** — `components/goals/GoalInsightPanel.tsx` (2026-07-15) wires the richer backend endpoint into a real "Get insight" sheet | — (closed) |
| Goal progress auto-extraction from conversations/chat | `GoalsAIService.extractProgressFromAllGoals` | **Present via a backend-shared pipeline** — `utils/llm/goals.py::extract_and_update_goal_progress`, called from both conversation post-processing and the chat endpoint, applies to Windows automatically with no client code | — (closed; old audit's uncertainty resolved) |
| Goal completion celebration (confetti overlay) | `GoalCelebrationView.swift` | **Present** — `components/goals/GoalCelebration.tsx` (2026-07-15), a faithful 4-phase dim→confetti→text→fade overlay, wired into `Goals.tsx` | — (closed) |
| Onboarding goal AI generation | `GoalsAIService.normalizeOnboardingGoalInput` (local Gemini) | **Present-but-weaker**, confirmed unchanged — `GoalStep.tsx` → `lib/goals.ts::generateGoal` is a single generic agent-LLM prompt, not the rich context generator the main Goals page now has | L |
| Onboarding "auto-created tasks" explainer | `AutoCreatedTasksStep.tsx` | **Present**, and now literally true rather than aspirational — the screen-extraction feature its copy describes ("mentioned in Slack") is real and shipped | — |

## Screen-based AI task extraction — PRESENT (old audit's headline claim was wrong)

**What it is:** Watch the screen for unaddressed requests/commitments and auto-create tasks
without user action.

**Where (Windows):** `src/main/assistants/tasks/taskAssistant.ts` (301 lines, the coordinator
peer implementing `ProactiveAssistant`), `loop.ts` (the dispatch loop), `tools.ts` (tool
schemas), `models.ts` (parse/validate), `create.ts` (save/sync/embed/promote), `context.ts`
(prompt-context assembly), `appLists.ts` (whitelist), `prompt.ts` (system/user prompt),
`toolBackends.ts` (search backends), `geminiWire.ts` (transport). All shipped 2026-07-15, per
`git log`, more than five weeks before the 2026-08-20 audit that called this "Absent" with a
repo-wide-grep citation.

**How it works, verified against the current file:**
- **Whitelist + window gate**: `appLists.ts` ports Mac's exact 15-app whitelist (Telegram,
  WhatsApp, Messages, Slack, Discord, Zoom, Chrome/Arc/Safari/Firefox/Edge/Brave/Opera, Notes,
  Superhuman) and the ~50-keyword browser-window filter, matched by lowercase substring —
  `isAppAllowed`/`isWindowAllowed` (lines 141–156).
- **Triggers**: `taskAssistant.ts`'s `analyze()` (the coordinator's cadence path — 15s for a
  messaging app via `MESSAGING_INTERVAL_MS`, else `taskFallbackIntervalMin` minutes, default 10)
  and `onContextSwitch()` (the primary trigger, extracting from the departing frame). Both funnel
  into the shared `runPipeline`, which takes a re-entrancy lock (`running`) and a per-window
  dedupe TTL (`analyzedWindows`, 60s non-messaging / 15s messaging) so the two triggers can't
  double-analyze the same window (lines 178–200).
- **Tool-calling loop**: `loop.ts::runExtractionLoop` forces a tool call on iteration 0 (JPEG
  present from the start) and dispatches up to `TASK_MAX_ITERS = 8` model calls across the same 5
  tools Mac has — `search_similar`, `search_keywords`, `extract_task`, `reject_task`,
  `no_task_found` (`tools.ts` lines 40–235) — with the same "look again, is there another
  distinct commitment" re-prompt after a successful extract, so one frame can yield multiple
  tasks (lines 74–94).
- **Validation + confidence gate**: `models.ts::validateTaskTitle` ports Mac's ≥6-word +
  proper-noun-after-the-verb + generic-pattern-rejection heuristic verbatim (lines 175–206).
  `create.ts::createStagedTaskFromExtraction` gates on `DEFAULT_MIN_CONFIDENCE = 0.75` (line 41),
  matching the user-configurable Mac default.
- **Source classification**: `ExtractedTask.sourceCategory`/`sourceSubcategory` (`models.ts`
  lines 41–42) are parsed from the model's `extract_task` call and written into both the local
  staged row and the backend `metadata` JSON (`create.ts` lines 165–166, 189–190) — present, just
  not exposed as a UI filter (see the Rich Tasks page item).
- **Dedup/prioritization search tools**: `toolBackends.ts` ports Mac's vector (`> 0.3` cosine
  similarity, top 10) and FTS5 keyword (prefix-OR, ≥3-char tokens) search backends 1:1, including
  the exact `TaskSearchResult` JSON shape the model sees.
- **Context grounding**: `context.ts::assembleTaskContext` reads the AI user profile (local),
  merges top-relevance + recent-active + staged tasks for dedup evidence, lists recently
  completed tasks, and fetches active goals (300s-cached) — the same five-slice merge order as
  Mac's `refreshContext`, minus Mac's "user-deleted tasks" slice (Windows hard-deletes, so
  there's no `deleted=1` row to read — a documented, intentional deviation).

**Windows status:** Present, essentially feature-complete relative to Mac's extraction engine.
The old audit's "Absent... single biggest Tasks gap" verdict is simply wrong for current source;
it was already wrong on the audit's own date.

**Value / notes:** This closes what was the highest-value item in the old audit. The genuine
remaining gaps are downstream of extraction (dedup, prioritization, notification, UI richness),
not extraction itself — see the items below.

## Staged-task deduplication — still absent, but the backend has a much narrower guard

**What it is:** An hourly background pass that finds *semantic* duplicates among staged tasks
and removes the weaker copy.

**Where (Mac):** `TaskDeduplicationService.swift`.

**Windows status:** Absent as a client job — no file in `assistants/tasks/` runs a periodic
semantic-dedup pass, and no such job is scheduled anywhere in `src/main`. What does exist,
verified this pass and *not* mentioned in the old audit at all: `backend/routers/staged_tasks.py`
sits on a "Candidates" system (`backend/database/candidates.py`,
`backend/utils/task_intelligence/candidate_service.py`) whose `promote_staged_task` path runs a
duplicate guard (`backend/tests/unit/test_staged_tasks_dedup.py`) — but it's a normalized
case-insensitive **exact-string** match against existing active `action_items` at promote time,
not a semantic Gemini judgment across the whole staged pool the way Mac's hourly pass is. It
narrows the gap (an obvious literal repeat won't get promoted twice) without closing it (two
staged tasks that say the same thing in different words still both exist, and duplicates within
the staged pool itself are never proactively cleaned up the way Mac's service does).

**Value / notes:** Medium, unchanged from the old audit — this matters more now that screen
extraction (confirmed present, above) is actually producing near-duplicate staged tasks on
Windows too.

## Task prioritization / relevance scoring — still absent as a Windows job

**What it is:** An hourly re-ranking of staged tasks by relevance to goals/profile/engagement,
plus the AI user profile that feeds it.

**Where (Mac):** `TaskPrioritizationService.swift`, `AIUserProfileService`.

**Windows status:** Absent as a ranking job. `relevance_score` is a real, actively-used column —
`ipc/taskStore.ts` reads/writes it, `PATCH /v1/staged-tasks/batch-scores` exists on the backend
for exactly this purpose — but nothing on the Windows client ever computes a value to write
there; the column is populated only when the backend (or another client) supplies one, and
`Tasks.tsx` still sorts by due-date bucket + created-at tiebreak only. The **AI user profile
itself is present**, correcting the old audit's cross-reference note that called it
"Mac-local-only" — `assistants/aiUserProfile/{service,synthesis}.ts` (2026-08-09) generates it
locally on the same ~24h cadence as Mac and it already feeds `tasks/context.ts`'s prompt
grounding; it is simply not (yet) wired into a Windows-side ranking pass.

**Value / notes:** Medium, unchanged — due-date sort remains a reasonable fallback, so the loss
is "smart ordering of no-due-date/AI-noise tasks," not unusability.

## Staged→action-item promotion pipeline — PRESENT, notification sub-gap remains

**What it is:** Event-driven promotion of the top-ranked staged task into `action_items`, paced
so extraction volume doesn't spam the user.

**Where (Windows):** `assistants/tasks/create.ts::promoteIfNeeded` (lines 371–422) and
`assistants/tasks/promotionService.ts` (both shipped 2026-08-20 — the same calendar day as the
old audit, which is why this one is a same-day miss rather than a stale one, but it's still
wrong in the current file).

**How it works, verified:** Purely programmatic (`POST /v1/staged-tasks/promote`, no AI),
30s-debounced inline promote right after a successful staged-task sync
(`create.ts` line 324), a 60s-floor self-scheduling backoff-ladder safety net
(`promotionService.ts` — `SAFETY_BACKOFF_MS = [60_000, 120_000, 300_000, 600_000]`, lines 36–53,
added specifically because a flat 60s timer was "the single loudest request source in the app" —
per the file's own comment — before the backoff was added), and a startup promote that fires
immediately if a session already exists or polls briefly for one. At most one task promotes per
trigger, matching Mac's deliberate anti-spam design. On success the promoted `action_item` is
reflected into the local store and every window is told via `tasks:changed`
(`create.ts::broadcastTasksChanged`).

**What's still missing:** No native OS notification or toast fires on promotion — confirmed by
the module's own header comment ("No glow, no notification in PR-B — it stages durable tasks
silently") and by a repo-wide grep for `Notification` in the tasks tree turning up nothing but
that comment and unrelated string literals. This is the one sub-piece of the old audit's
promotion-pipeline claim that's still accurate: Windows has no "new task" notification of any
kind, even though the pipeline that would trigger one now exists.

**Value / notes:** Medium. The pipeline itself is done; the remaining gap is narrowly "add a
`notifyProactive`-style call on a successful promote," which is a small, well-scoped follow-up
now that the rest of the machinery exists (`assistants/core/notify.ts` — the shared throttle
used by Focus/Insight/Memory/Goals — is a drop-in candidate).

## Terminal Task Agent (autonomous Claude Code execution) — engine exists, not wired to tasks

**What it is:** A one-click way to spawn a real coding-agent session against a code/bug/feature
task.

**Where (Mac):** `TaskAgentManager.swift` (tmux + `claude --dangerously-skip-permissions`),
`TaskAgentSettings.swift`.

**Windows status:** Absent *for tasks specifically*, but the underlying engine is real and
shipped: `src/main/codingAgent/` implements ACP adapters for Claude Code, Codex, OpenClaw, and
Hermes (`taskRunner.ts`, `adapterRegistry.ts`, `acp.ts`, `claudeOAuth.ts`, etc., shipped
2026-07-15), reachable today only through ordinary chat via
`src/renderer/src/lib/agentTask.ts::detectAgentTask` — a delegation-phrase detector ("ask codex
to fix the failing test", "use claude code and...") that hands the message to the coding-agent
runner instead of normal chat. Nothing in `Tasks.tsx` or anywhere else calls `codingAgentRun`
from a task row; a repo-wide grep for a task-agent-specific entry point
(`ProactiveTaskExecute`, `taskExecute`, `TaskAgentManager`-equivalent) returns nothing. **This
corrects the old audit's own parenthetical**, which called the ACP integration "unrelated... per
the parity-audit baseline separately tracked as not implemented" — that baseline is stale; the
integration exists and is a real chat feature. The Tasks-area gap is narrower than the old audit
implied: it's "wire a task row's context menu to the existing coding-agent runner with a
task-shaped prompt," not "build a coding-agent execution engine from scratch."

**Value / notes:** Medium, same as before — narrow but powerful once wired; the hard part
(process spawning, streaming, adapter fallback, auth) is already built for the chat surface and
would need to be pointed at a task instead of a chat message.

## Per-task "Investigate" AI chat sidebar (Task Chat) — confirmed still absent

**What it is:** A full agentic chat session scoped to one task, with persisted per-task
transcript history.

**Where (Mac):** `TaskChatCoordinator.swift`, `TaskChatRuntime.swift`, `TaskChatState.swift`,
`TaskChatPanel.swift`.

**Windows status:** Absent, confirmed by grep — no `chatSessionId` field, no "Investigate"
action anywhere in `Tasks.tsx` (its row only supports edit-text / set-due-date / complete /
delete). One infrastructure note the old audit couldn't have found because the code didn't cite
it: `src/main/agentKernel/types.ts` already declares `'task_chat'` as a valid
`DesktopArtifactDeliveryTargetKind` / `DesktopContextSourceKind` value (lines 113–116, 158–162)
inside the broader agent-kernel type system that also backs the coding-agent chat surface — but
grepping the renderer tree for any reference to it returns nothing. The slot is reserved in the
schema; nothing has been built against it.

**Value / notes:** High, unchanged — still the largest genuine remaining Tasks gap after the
(now-closed) extraction gap; it's the mechanism that turns a task into something Omi can
actively work rather than just track.

## Daily recurring task auto re-investigation — confirmed still absent

**Where (Mac):** `TaskChatCoordinator.investigateInBackground`, `DailyTaskCreationSheet.swift`.

**Windows status:** Absent, confirmed — the generated API types carry `recurrence_rule`/
`recurrence_parent_id` fields (`lib/omiApi.generated.ts`, multiple call sites), but grepping the
whole renderer and main trees for any code that reads or sets them turns up nothing beyond that
generated type file. No sheet/flow creates a recurring task; no code advances a due date or
re-fires an investigation.

**Value / notes:** Medium, unchanged.

## "Execute" — full-desktop agentic task execution — engine exists generally, not wired to tasks

**What it is:** An "Execute" action that carries out a task end-to-end via desktop automation
(browser, native apps, filesystem), not just describes it.

**Where (Mac):** `ProactiveTaskExecute.swift`.

**Windows status:** Absent as a task-row action, but — unlike at the time of the old audit's
own framing — the underlying capability is no longer entirely missing on Windows: an
"agent kernel" / desktop control-tools stack exists (`src/main/agentKernel/controlTools.ts`,
`desktopToolPolicy.ts`, `automation/foregroundTarget.ts`, oldest of these shipped 2026-07-29)
exposing tools like `route_desktop_intent` and `build_desktop_context_packet`. A repo-wide grep
for anything task-specific invoking it (`ProactiveTaskExecute`, `taskExecute`, `executeTask`)
returns nothing, so no task notification or task row currently routes into this stack. This
system is large enough that it's almost certainly the subject of a separate audit file (the old
audit's own cross-reference section flagged the same stack as "outside Tasks/Goals scope") —
flagging it here only to correct the framing from "the whole capability is missing" to "the
capability exists generally; nothing routes a task into it."

**Value / notes:** Medium, unchanged in practice — still depends on a larger cross-cutting
stack, though that stack is closer to real than the old audit's framing suggested.

## Task agent status indicator on task rows — confirmed still absent

**Where (Mac):** `TaskAgentViews.swift`. **Windows status:** Absent — moot without a per-task
agent to show the status of. **Value:** Low.

## Tasks page richness (filters, tags, sort/indent) — confirmed still mostly absent, one framing fix

**What it is:** Category/source/priority/origin filter chips, manual sort-order/indent, and a
"removed by AI" vs "removed by me" distinction.

**Where (Mac):** `TasksPage.swift`, `TaskDetailViews.swift`.

**Windows status:** Partial, essentially unchanged from the old audit's assessment —
`src/renderer/src/pages/Tasks.tsx` (verified this pass, lines 112, 287–345) still has only an
open/done/all status filter and a due-date bucket grouping (today/tomorrow/later/no-date) for
display only; no category/source/priority/origin chips, no sort-order/indent UI. `sortOrder` and
`indentLevel` **are** real columns in the local schema (`shared/types.ts` lines 2345–2346,
2377–2378, 2459–2460) but a grep of the renderer tree finds zero references to either — the data
model has the fields, the UI does nothing with them. **One correction to the old audit's own
wording:** it framed the whole gap as "Windows has no staged-tasks concept at all," which is
false on its face now that staged tasks are a real local table synced with the backend (see the
extraction and promotion sections above) — the accurate framing is that the staged-tasks concept
exists, but the rich Mac-side filter/tag/sort UI built on top of it does not.

**Value / notes:** Medium, unchanged.

## Dev tools: prompt editor + historical test runner — confirmed still absent

**Where (Mac):** `TaskPromptEditorWindow.swift`, `TaskTestRunnerWindow.swift`. **Windows
status:** Absent — a grep for any dev-only prompt-editing or screenshot-replay surface
(`analyzeNowForDev` is the closest Windows analog and is a headless test hook, not a UI) finds
nothing UI-facing. **Value:** Low — internal tooling, not user-facing.

## Automatic daily goal generation + stale-goal cleanup — PRESENT (old audit's claim was wrong)

**What it is:** Silently generate a goal from rich context when the user has fewer than 3 active
goals and hasn't generated one today; separately, delete a zero-progress auto-goal after 3 days
of inactivity so that gate doesn't clog permanently.

**Where (Windows):** `assistants/goals/generate.ts` (candidate build + create, shipped
2026-07-15, model routing updated to `gemini-2.5-flash-lite` 2026-08-17),
`assistants/goals/schedule.ts` (the trigger + gates, 2026-07-15), `assistants/goals/staleCleanup.ts`
(2026-07-15).

**How it works, verified:** `schedule.ts::runGoalGenerationIfDue` gates in order — toggle on
(`goalAutoGenerationEnabled`) → session present → not already generated today
(`goalGenerationLastDate`, local-calendar-day granularity) → run `removeStaleGoals()` first (so
aged auto-goals can't wedge the count gate) → fewer than `MAX_ACTIVE_GOALS = 3` active goals
(line 32) → sufficient context (at least one memory, conversation, or task) → generate → stamp
today. `staleCleanup.ts::removeStaleGoalsWith` deletes an auto-attributed goal iff it's still
active, has made zero progress, and hasn't changed in `STALE_THRESHOLD_MS = 3 days` (line 20) —
matching Mac's threshold — and is safety-scoped to *only* goals in a local attribution record
(`goalAutoGeneratedIds`) so a user-created goal can never be auto-deleted (the backend returns no
`source` field to distinguish them otherwise, per the file's own safety-critical comment).

**Trigger mechanism deviates from Mac by necessity, not laziness:** Mac hooks
`onConversationCreated()`; Windows main has no such signal, so it re-checks every 4 hours
(`CHECK_INTERVAL_MS`, `schedule.ts` line 35) instead, with the once-per-calendar-day gate keeping
actual generation to at most one per day regardless of how often the heartbeat fires. Net
user-visible behavior matches.

**Windows status:** Present. The old audit's "Absent as an automatic background process...
Windows requires the user to remember to click a button" is flatly wrong for the current file
and was already wrong on the audit's own date (this shipped over a month earlier).

**Value / notes:** This closes what was the second-highest-value item in the old Goals half of
this audit.

## Goal suggestion context richness — PRESENT on the Goals page, still thin on the Home widget

**What it is:** How much context and reasoning depth backs a "suggest one goal" action.

**Where (Windows, rich path — Goals.tsx):** `assistants/goals/context.ts::fetchGoalContext`
(2026-07-15) assembles the same five sources Mac's `GoalsAIService.generateGoal` does — persona
(`/v1/personas`), up to 500 memories, up to 100 completed conversations, up to 100 incomplete
tasks, and the full active/completed goal split — with **no truncation beyond those caps**,
matching Mac's own no-truncation design (lines 26–29). `Goals.tsx`'s "Suggest" button calls
`window.omi.goalsGenerateCandidate` → `generate.ts::generateGoalCandidateNow` →
`buildCandidateWith`, which runs a structured Gemini call against this context and returns a
candidate for the renderer to preview (`Goals.tsx` lines 261–300) before the user accepts it via
`goalsCreateCandidate` → `acceptGoalCandidate`. This preview step is a Windows-only improvement
over Mac, which creates directly with no review (documented in `generate.ts`'s own comments as
"D2 — Windows is ahead of Mac here").

**Where (Windows, thin path — Home widget, unchanged from the old audit):**
`components/home/QuickGoalsWidget.tsx::generate` (lines ~93–109) still calls the plain backend
`GET /v1/goals/suggest` → `backend/utils/llm/goals.py::suggest_goal` (up to 100 memories, first
50 non-locked, truncated to 20 for the prompt; no conversations/tasks/persona/goal-history; a
hardcoded fallback suggestion on failure or empty memories) and blind-creates with no preview —
exactly the flow the old audit described as the *only* Windows path. It is now only one of two,
and the weaker one.

**Windows status:** Present-and-ahead-of-Mac on the Goals page; present-but-still-thin on the
Home widget. **This is a genuine new finding, not something the old audit could have caught**:
the two "generate a goal" entry points on Windows now diverge from each other in quality, which
is its own small parity/consistency issue worth a follow-up (point the widget at the same
candidate flow, or at minimum give it a preview step) independent of any Mac comparison.

**Value / notes:** The headline gap (thin vs. rich) is closed on the primary surface. The
residual gap is Windows-internal: bringing the Home widget up to the same standard as the Goals
page.

## AI goal insight/advice — PRESENT (old audit's claim was wrong)

**What it is:** Given a goal, get one specific actionable step for the week.

**Where (Windows):** `components/goals/GoalInsightPanel.tsx` (2026-07-15) — a modal wired to
`GET /v1/goals/{goal_id}/advice` → `backend/utils/llm/goals.py::get_goal_advice` /
`_get_goal_context`, which the old audit itself correctly identified as the richest version of
this feature across all three implementations (hybrid vector search + last-7-days conversations
+ recent chat + memories). The panel handles loading/error/rate-limit/not-found states and a
Refresh action with its own cooldown (lines 60–120).

**Windows status:** Present. The old audit's "no 'Get insight' affordance at all" is wrong for
the current file.

**Value / notes:** This closes what the old audit rightly called a "pure UI gap" — the backend
capability existed and was unused; now it's used.

## Goal progress auto-extraction from conversations — PRESENT via a shared backend pipeline

**What it is:** After a conversation or chat message, check active goals for a mentioned
progress value and update automatically.

**Where (Mac):** `GoalsAIService.extractProgressFromAllGoals`.
**Where (backend, shared, verified this pass):** `backend/utils/llm/goals.py::
extract_and_update_goal_progress` (a single LLM call evaluating every active goal at once,
line 248), called from `backend/utils/conversations/process_conversation.py:737` (every
processed conversation) and `backend/routers/chat.py:449` (every chat send, via
`llm_executor.submit`, i.e. fire-and-forget off the request path). Both call sites are
platform-agnostic backend code that runs identically regardless of which client produced the
conversation or chat message — this predates the current Mac Goals implementation by months
(earliest `extract_and_update_goal_progress` history found: Feb 2026).

**Windows status:** Present. The old audit explicitly declined to guess here ("outside this
audit's file scope... would need separate verification") rather than wrongly calling it absent —
that caution was well-placed, and the verification now resolves it to "present and automatic":
any conversation or chat message a Windows user produces already runs through this pipeline with
zero Windows client code required. Windows still has no UI that *shows* an auto-update happened
(matches Mac, which also updates silently) and no client-side hook of its own, but the ambient
behavior itself is there.

**Value / notes:** This closes the old audit's flagged-but-unresolved item; the silent,
ambient-tracking value proposition Mac markets already applies to Windows today.

## Goal completion celebration — PRESENT (old audit's claim was wrong)

**What it is:** A full-screen animated "Goal Completed!" moment.

**Where (Windows):** `components/goals/GoalCelebration.tsx` (2026-07-15), wired into
`Goals.tsx` line 729. A faithful 4-phase port of Mac's `GoalCelebrationView`: dim scrim → 40
particles of confetti bursting outward from center (with `motion-reduce:hidden` for accessibility)
→ gradient "Goal Completed!" text + goal title + target caption → fade out, timed at
`CELEBRATION_TIMINGS` (confetti at 300ms, text at 800ms, fade at 3000ms, done at 3500ms — lines
13–18), matching Mac's ~3.5s choreography. Two of Mac's nine confetti colors (purple) are
swapped for white per this codebase's neutral-palette invariant; otherwise timing-for-timing
faithful.

**Windows status:** Present. The old audit's "plain toast" is wrong for the current file.

**Value / notes:** Cosmetic, as the old audit correctly weighted it, but the designed
moment-of-delight gap it flagged no longer exists.

## Onboarding goal AI generation — confirmed unchanged, still present-but-weaker

**Where (Mac):** `GoalsAIService.normalizeOnboardingGoalInput` (local Gemini).
**Where (Windows):** `components/onboarding/GoalStep.tsx` → `lib/goals.ts::generateGoal` — a
single generic agent-LLM prompt ("Suggest ONE specific personal-productivity goal tailored to
me..."), unrelated to and much thinner than the rich `assistants/goals/context.ts` +
`generate.ts` pipeline the main Goals page now uses. The old audit flagged this as needing a
separate backend-vs-local check; that check is done — it's local (`callAgentLLM`), not a backend
call, and it doesn't reuse the rich context assembler at all despite one now existing elsewhere
in the codebase.

**Windows status:** Present-but-weaker, confirmed. **Value:** Low, unchanged.

## Onboarding "auto-created tasks" explainer — confirmed present, now literally accurate

**Where (Windows):** `components/onboarding/AutoCreatedTasksStep.tsx` — illustrative sample rows
("Task 1 — From today's meeting," "Task 2 — Mentioned in Slack") shown on the onboarding
completion screen. **Windows status:** Present, and — unlike at the time of the old audit, when
screen-based extraction genuinely didn't exist and the copy was describing an aspiration — the
feature this screen is illustrating (a Slack message becoming a task) is now real. No code
change needed here; noting only that this item's accuracy improved as a side effect of the
extraction gap closing.

## Cross-references

- **AI user profile** (`assistants/aiUserProfile/`) is present and shared with Mac (2026-08-09),
  correcting the old audit's cross-reference note that called it "Mac-local-only." It already
  feeds task-extraction context (`tasks/context.ts`); it does not yet feed a Windows-side task
  *ranking* pass, since no such pass exists (see the prioritization item above).
- The coding-agent/ACP stack (`codingAgent/`) and the desktop-automation "agent kernel"
  (`agentKernel/`) both exist generally on Windows now, correcting the old audit's framing of
  both as wholesale-missing. Neither is wired to a task-specific surface — that wiring gap, not
  the underlying engine, is what remains for "Terminal Task Agent" and "Execute" above. Given
  their size, both stacks are almost certainly the proper subject of their own audit file rather
  than a deep dive here.
- `backend/utils/llm/goals.py::get_goal_advice`'s hybrid-retrieval context building is genuinely
  good and, as of this pass, **is** used by Windows (`GoalInsightPanel.tsx`) — no longer a quick
  win sitting on the table; it's shipped.

## Spotted outside my scope

- The backend's "Candidates" system (`backend/database/candidates.py`,
  `backend/utils/task_intelligence/*`, including a "What Matters Now" recommendation engine in
  `recommendations.py`/`proactive_engine.py`) has substantially replaced the historical
  `staged_tasks` Firestore collection as the authority behind `routers/staged_tasks.py`, with the
  old collection now a compatibility read/write shim. This is a large, backend-owned
  restructuring that changes what "staged task" means underneath both Mac and Windows clients
  without either client necessarily knowing about it. It's out of scope for a Windows-vs-Mac
  desktop-client parity audit, but whoever owns backend architecture docs should know the
  `staged_tasks` collection is legacy-compat, not primary storage, going forward.
- Focus/Insight/Memory assistant local-Gemini patterns (own local job + local SQLite + backend
  sync per assistant) mirror the same architecture seen here in Tasks/Goals — still worth a
  consistent write-up if not already covered by the Focus/Insight audit area, and still true
  after this re-verification.
