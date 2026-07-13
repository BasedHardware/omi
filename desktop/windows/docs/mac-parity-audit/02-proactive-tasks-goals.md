# Mac→Windows Parity Audit — Proactive Assistants: Tasks & Goals

> Scope: AI task extraction/dedup/prioritization/promotion, the terminal + chat "task agent," and AI goal generation/advice/progress-tracking. Windows baseline checked: `desktop/windows/src/renderer/src/pages/{Tasks,Goals}.tsx`, `components/home/{QuickTaskWidget,QuickGoalsWidget}.tsx`, `components/layout/TasksGoalsToggle.tsx`, `components/ui/GenerateGoalsButton.tsx`, `components/onboarding/{GoalStep,AutoCreatedTasksStep}.tsx`, and a repo-wide grep of `desktop/windows/src` for any task/goal engine, dedup, prioritization, promotion, or agent code (none found outside the renderer's thin CRUD pages). Backend endpoints (`backend/routers/goals.py`, `backend/utils/llm/goals.py`) checked directly to separate backend-shared logic from Mac-local-only logic.

## Summary table

| Feature | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Screen-based AI task extraction (whitelisted apps, tool-calling loop) | `TaskAssistant.swift`, `TaskAssistantSettings.swift` | **Absent** | H |
| Task source classification (category/subcategory) | `TaskModels.swift` | **Absent** | L |
| Staged-task semantic deduplication (hourly Gemini pass) | `TaskDeduplicationService.swift` | **Absent** | M |
| Task relevance prioritization + daily AI user profile | `TaskPrioritizationService.swift`, `AIUserProfileService` | **Absent** | M |
| Staged→action-item promotion pipeline + notification | `TaskPromotionService.swift` | **Absent** (Windows has no staged-task concept at all) | M |
| Terminal "Task Agent" (Claude Code in tmux, autonomous code tasks) | `TaskAgentManager.swift`, `TaskAgentSettings.swift` | **Absent** | M |
| Per-task "Investigate" AI chat sidebar | `TaskChatCoordinator/Runtime/State.swift`, `TaskChatPanel.swift` | **Absent** | H |
| Daily recurring task auto re-investigation | `TaskChatCoordinator.investigateInBackground`, `DailyTaskCreationSheet.swift` | **Absent** (no recurrence field/UI at all) | M |
| "Execute" full-desktop agentic task execution from a notification | `ProactiveTaskExecute.swift` | **Absent** | M |
| Task agent status indicator / terminal icon on task rows | `TaskAgentViews.swift` | **Absent** | L |
| Rich Tasks page: filter tags (source/category/priority/origin), sort/indent, "Removed by AI" vs "Removed by me" | `TasksPage.swift`, `TaskDetailViews.swift`, `TaskFilterTag` | **Partial** — Windows `Tasks.tsx` only has open/done/all + due-date bucketing | M |
| Dev tools: prompt editor + historical-screenshot test runner | `TaskPromptEditorWindow.swift`, `TaskTestRunnerWindow.swift` | **Absent** (dev-only, no user-facing loss) | L |
| Automatic daily goal generation (rich local context) + stale-goal auto-completion | `GoalGenerationService.swift`, `GoalsAIService.generateGoal` | **Absent** — replaced by a manual, thinner backend call | H |
| Goal suggestion richness (memories+conversations+tasks+persona+goal history, task linking) | `GoalsAIService.swift`, `GoalPrompts.generateGoal` | **Present-but-weaker** — Windows calls `GET /v1/goals/suggest` → `backend/utils/llm/goals.py::suggest_goal`, which only uses the last ~20 memories, no conversations/tasks/persona/goal-history, no task linking | H |
| AI goal insight/advice ("what should I do this week") | `GoalsAIService.getGoalInsight` (local) vs `GET /v1/goals/{id}/advice` (backend, richer — vector search + recent convos + chat + memories) | **Present** via backend, and not exposed in Windows UI at all — no "Get insight" affordance | M |
| Goal progress auto-extraction from conversations/chat | `GoalsAIService.extractProgressFromAllGoals` | **Absent** locally — need to confirm backend post-processing does this pathway; not visible in Windows UI regardless (no passive progress capture) | M |
| Goal completion celebration (confetti overlay) | `GoalCelebrationView.swift` | **Absent** — Windows shows a plain toast ("Goal complete 🎉") | L |
| Onboarding goal AI generation | `GoalsAIService.normalizeOnboardingGoalInput` (local Gemini) | **Present-but-weaker** — `GoalStep.tsx` calls `lib/goals.ts::generateGoal` (needs separate backend-vs-local check; UI flow itself — 2 canned suggestions + "Let AI generate it" + free text — is comparable) | L |
| Onboarding "auto-created tasks" explainer | `AutoCreatedTasksStep.tsx` | **Present** (illustrative sample rows only — real extraction depends on conversation-derived tasks; screen-based extraction gap above still applies) | — |

## Screen-based AI task extraction

**What it is:** Mac watches the screen for unaddressed requests/commitments (Slack/Telegram/WhatsApp messages, email, Linear/Jira tickets, etc.) and auto-creates tasks without any user action.

**Where (Mac):** `TaskAssistant.swift` (actor, conforms to `ProactiveAssistant`), `TaskAssistantSettings.swift`.

**How it works:** Runs off the shared screen-capture pipeline (`CapturedFrame`). Only analyzes apps on an explicit whitelist (`TaskAssistantSettings.defaultAllowedApps`: Telegram, WhatsApp, Messages, Slack, Discord, Zoom, browsers, Notes, Superhuman); browser apps get an additional window-title keyword filter. Trigger is event-driven: a context-switch (leaving an app) or a 10-minute fallback timer, plus a fast-path (~15s) for messaging apps so an in-app new message doesn't wait for a context switch. Per-(app, normalized-window) dedupe TTL prevents re-analyzing the same chat repeatedly. On trigger, `extractTaskSingleStage` sends the JPEG screenshot + a large system prompt (`TaskAssistantSettings.defaultAnalysisPrompt`, ~170 lines of instructions/examples) to Gemini with 5 tools (`search_similar`, `search_keywords`, `extract_task`, `reject_task`, `no_task_found`) in an up-to-8-iteration tool-calling loop — it can extract multiple distinct commitments from one screenshot. Task titles are hard-validated (≥6 words, must include a proper noun) with a retry-with-feedback loop. Extracted tasks get a hard-coded due-date parser (ISO8601, several date formats, NSDataDetector NL fallback; rejects past dates), a `TaskSourceClassification` (category/subcategory, e.g. `direct_request/message`), and a confidence score gated by a user-configurable threshold (default 0.75). Results are saved locally (SQLite `staged_tasks`, GRDB) with a Gemini embedding for future dedup search, then synced to the backend's staged-tasks table.

**Windows status:** Absent. No screen-capture-driven task pipeline exists at all in `desktop/windows` (repo-wide grep for `TaskAgent|TaskExtraction|staged_task|screenshot.*task` under `desktop/windows/src` returns nothing). Windows tasks only originate from conversation-derived backend extraction (same as mobile) — confirmed by `AutoCreatedTasksStep.tsx`'s copy: "omi listens to your conversations and automatically creates tasks." There is no local screen-watching for message/chat commitments.

**Value / notes:** High — this is the single biggest Tasks-feature gap; it's the mechanism that makes Mac tasks feel proactive rather than reactive.

## Staged-task deduplication

**What it is:** An hourly background pass that finds semantic duplicates among not-yet-promoted staged tasks and hard-deletes the weaker copy.

**Where (Mac):** `TaskDeduplicationService.swift` (actor, singleton, `start()`/`stop()` lifecycle).

**How it works:** Every hour (30-min cooldown, 60s startup delay, needs ≥3 staged tasks), fetches up to 200 staged tasks from the backend and sends them all in one Gemini call with a structured JSON schema asking for duplicate groups + a "keep" pick (criteria: specificity, due date, priority, source reliability, recency). Validates returned IDs against the input set, logs each deletion to a local `TaskDedupLogRecord`, then hard-deletes the losing task via the backend API.

**Windows status:** Absent — no dedup pass anywhere; duplicate tasks from repeated mentions simply accumulate.

**Value / notes:** Medium — matters more once screen-based extraction (above) exists, since that's what produces near-duplicate tasks in the first place.

## Task prioritization / relevance scoring

**What it is:** An hourly re-ranking of staged tasks by relevance to the user's goals, profile, and engagement history, plus a daily-refreshed "AI user profile."

**Where (Mac):** `TaskPrioritizationService.swift` (actor), `AIUserProfileService`.

**How it works:** Every 5 minutes, checks if the AI user profile is >24h stale and regenerates it; every hour (min 2 staged tasks), sends the entire current ranking (position + description + priority + due date) plus user profile, active goals, and a "reference context" of completed tasks to Gemini, asking only for the tasks that are *misranked* (not a full re-sort) with new positions. Applies a selective re-ranking (`applySelectiveReranking`) to local SQLite and syncs all scores to the backend. `relevanceScore` (1 = most important) then drives display order in `TasksPage`/`TodaysTasksWidget`.

**Windows status:** Absent — Windows `Tasks.tsx` sorts purely by due-date bucket + created-at tiebreak; no AI relevance ranking, no user profile, no goal-alignment signal in ordering.

**Value / notes:** Medium — Windows' due-date sort is a reasonable fallback, so the loss is "smart ordering of no-due-date/AI-noise tasks," not full unusability.

## Staged→action-item promotion pipeline

**What it is:** Event-driven promotion of the single top-ranked staged task into the user-visible `action_items` list, with a native notification, whenever a task completes/deletes or on a 60s safety timer.

**Where (Mac):** `TaskPromotionService.swift` (actor).

**How it works:** Purely programmatic (no AI) — calls a backend "promote top staged task" endpoint, debounced 30s, promoting exactly one task per trigger (deliberately not bursting, since users perceived batch promotion as notification spam). On success, syncs the promoted task into local `ActionItemStorage` and fires `NotificationService` with structured `FloatingBarNotificationContext` (source app, reasoning built from priority/category/due date/source) so a follow-up chat can explain "why was I notified."

**Windows status:** Absent, and structurally so — Windows has no staged-tasks concept at all; every task created (locally or via `/v1/action-items` POST) is immediately a first-class action item. There is no promotion gate, no rate-limited notification-per-new-task flow.

**Value / notes:** Medium — this exists specifically to pace screen-extraction volume; without screen extraction on Windows the gap is partly moot today, but it also means Windows has no "new task" native notification of any kind.

## Terminal Task Agent (autonomous Claude Code execution)

**What it is:** For code/bug/feature-classified tasks, a one-click way to spawn a real Claude Code CLI session in a background `tmux` session that investigates/implements the task, with live output polling and edited-file tracking.

**Where (Mac):** `TaskAgentManager.swift` (`ObservableObject`, singleton), `TaskAgentSettings.swift`.

**How it works:** `launchAgent(for:context:)` shells out (`/bin/zsh -c`) to verify `tmux`/`claude` are installed, writes the built prompt (`TaskAgentSettings.buildTaskPrompt`, which composes the task description + custom prefix + instructions template) to a temp file, and launches `tmux new-session -d ... claude --dangerously-skip-permissions "$(cat promptfile)"`. A polling loop (5s interval) reads `tmux capture-pane` output, parses `Update(...)/Edit(...)/Write(...)` patterns to track edited files, detects completion via a list of Claude Code plan-mode phrase markers ("would you like to proceed", "ready to implement", etc.) or 3 consecutive unchanged polls (idle detection). Sessions persist to SQLite (`ActionItemRecord.agent*` fields) and are restored across app restarts, re-checking liveness/idleness. `openInTerminal` opens the live tmux session via AppleScript. Settings expose skip-permissions toggle, custom working directory, and prompt template editing.

**Windows status:** Absent entirely — no tmux/Claude Code CLI spawning, no polling, no `AgentStatusIndicator` UI, no settings surface. (Not to be confused with Windows' unrelated ACP/coding-agents integration, which per the parity-audit baseline is separately tracked as not implemented.)

**Value / notes:** Medium — highly powerful but narrow (only fires for code-classified tasks with tmux+claude CLI present; opt-in, `isEnabled` defaults false).

## Per-task "Investigate" AI chat sidebar (Task Chat)

**What it is:** A full agentic chat session scoped to one task — opened from a task row's "Investigate" action — that can use tools (browser, filesystem, Omi data queries) to research or act on the task, with persisted per-task transcript history.

**Where (Mac):** `TaskChatCoordinator.swift` (`ObservableObject`), `TaskChatRuntime.swift` (shared `AgentBridge` transport), `TaskChatState.swift` (per-task UI state + streaming), `TaskChatPanel.swift` (UI), `TaskChatMessageStorage` (GRDB persistence).

**How it works:** `openChat(for:)` gets-or-creates a `TaskChatState` per task, wires a system-prompt builder from `ChatProvider`, and loads persisted messages. `sendMessage` streams via the shared `TaskChatRuntime.query` (kernel-owned `task_chat` surface, same `AgentBridge` used elsewhere in the app) with full tool-call/thinking/streaming-delta handlers, chat-mode (`ask`/`act`), and content-block persistence. `TaskChatCoordinator` tracks per-task streaming/unread state (supports multiple tasks investigating in parallel) and status registration in `TaskAgentStatusRegistry` (voice/PostHog-visible summaries). `investigateInBackground(for:)` lets other code (e.g. daily-recurring-task refresh) kick off an investigation without opening the panel UI, and marks the task's `chatSessionId` to prevent duplicate re-triggers.

**Windows status:** Absent — no per-task chat concept, no `chatSessionId` field surfaced, no "Investigate" action anywhere in `Tasks.tsx`. Windows' task row only supports edit-text/set-due-date/complete/delete.

**Value / notes:** High — this is Mac's second-largest Tasks gap after screen extraction; it's the mechanism that turns a task into something Omi can actively work rather than just track.

## Daily recurring task auto re-investigation

**What it is:** Tasks can be marked `recurrenceRule: "daily"`; each day the task-chat investigation re-fires automatically and the due date auto-advances.

**Where (Mac):** `TaskChatCoordinator.investigateInBackground` (advances `dueAt` +86400s for `recurrenceRule == "daily"`), `DailyTaskCreationSheet.swift` (UI for creating a daily-recurring task with priority), `ActionItemRecord.recurrenceRule`/`recurrenceParentId`.

**Windows status:** Absent — `ActionItemResponse` types used by Windows have no recurrence fields surfaced in UI; no sheet/flow to create a recurring task.

**Value / notes:** Medium — a specific but useful pattern (e.g. "check my inbox for X every day") with no Windows equivalent.

## "Execute" — full-desktop agentic task execution

**What it is:** An "Execute" action on a proactive task notification that tells the agent to *carry out* the task end-to-end (send the message, draft the email, write the file) rather than just describe it, with explicit desktop-automation permission (browser via Playwright MCP, native macOS apps via AppleScript/osascript, filesystem) and a "verify before reporting done" requirement.

**Where (Mac):** `ProactiveTaskExecute.swift` (prompt-building only — `buildQuery`, `systemPromptSuffix`; the actual execution runs through the same floating-bar agent bridge as chat).

**Windows status:** Absent — no execute-mode prompt override, and more fundamentally no equivalent floating-bar agent with desktop-automation tool access on Windows tasks.

**Value / notes:** Medium — powerful but depends on Mac's floating-bar agent + native automation stack, which is a larger cross-cutting gap outside this audit's scope (see below).

## Tasks page richness (filters, source/category/priority/origin tags, sort/indent)

**What it is:** `TasksPage.swift` supports a much larger filter surface than Windows: status (todo/done/removed-by-AI/removed-by-me), date range, category (personal/work/feature/bug/code/research/communication/finance/health/other), source (screen/OMI/desktop/manual/OMI-analytics), priority, and origin (the `TaskSourceClassification` category, e.g. direct-request/self-generated/calendar-driven/reactive/external-system). It also carries `sortOrder`/`indentLevel` for manual drag-reordering/nesting (declared in `ActionItemRecord`, `TaskActionItem`).

**Where (Mac):** `TasksPage.swift` (`TaskFilterTag`/`TaskFilterGroup`), `TaskDetailViews.swift`.

**Windows status:** Partial. `Tasks.tsx` has: open/done/all status filter, and a due-date bucketing (overdue/today/tomorrow/upcoming/no-date) for display grouping only — no category/source/priority/origin filter chips, no distinction between "removed by AI" (dedup/backend cleanup) vs "removed by me" (soft delete stays local-only via hard `DELETE /v1/action-items/{id}`), no sort-order/indent/manual-reorder UI.

**Value / notes:** Medium — mostly matters once the AI extraction/classification pipeline above exists to actually populate these dimensions; today Windows tasks are almost entirely manual so most of these tags would be empty anyway.

## Dev tools: prompt editor + historical test runner

**What it is:** `TaskPromptEditorWindow.swift` lets a dev/power-user edit and reset the extraction system prompt live; `TaskTestRunnerWindow.swift` replays the extraction pipeline against historical Rewind screenshots over a chosen time window and reports task/error/search counts.

**Windows status:** Absent — moot without the screen-extraction feature it tests.

**Value / notes:** Low — internal tooling, not user-facing.

## Automatic daily goal generation + stale-goal cleanup

**What it is:** Once per day (after each conversation is saved, gated on a "last generated today?" check), if the user has <3 active goals, silently generates and creates one new goal from rich local context, with a native notification. Separately, any AI-created goal with no progress update in 3+ days is auto-completed (deactivated) and the user is notified via `.goalAutoCreated`.

**Where (Mac):** `GoalGenerationService.swift` (`onConversationCreated()` hook, `kAutoGenerationEnabled` toggle — **defaults to off**), `GoalsAIService.generateGoal()`.

**How it works:** `generateGoal()` fetches, in parallel, up to 500 memories, 100 completed conversations, 100 active action items, the user's persona, all active goals, and full goal history (split completed vs. abandoned) — with **no truncation** on any of these (unlike the backend's `suggest_goal`, see next section). It builds a 5-step reasoning prompt (`GoalPrompts.generateGoal`: understand the persona → look at active work → review goal history to avoid repeats → synthesize one specific measurable goal → link relevant existing tasks by ID) and calls Gemini directly from the desktop client with a structured schema. On success it creates the goal via the backend API, syncs locally, and links any tasks the model identified as relevant (`updateActionItem(id:goalId:)`).

**Windows status:** Absent as an automatic background process — Windows goal generation is exclusively the manual "Suggest"/"Generate goals with AI" button (`Goals.tsx`, `QuickGoalsWidget.tsx`, `GenerateGoalsButton.tsx`) calling `GET /v1/goals/suggest`. No daily cadence, no conversation-triggered check, no stale-goal auto-completion, no `kAutoGenerationEnabled`-style setting.

**Value / notes:** High — this is the flagship "Omi thinks about your goals for you" behavior; Windows requires the user to remember to click a button.

## Goal suggestion context richness (backend-shared endpoint, but thinner)

**What it is:** Both platforms can call a "suggest one goal" flow, but the context and reasoning depth differ substantially.

**Where (Mac, local):** `GoalsAIService.generateGoal()` (see above — persona + memories + conversations + tasks + full goal history, task-linking, 5-step prompt).
**Where (backend, shared):** `backend/routers/goals.py::suggest_goal` → `backend/utils/llm/goals.py::suggest_goal()` — used by Windows' `GET /v1/goals/suggest`.

**How it works (backend):** Fetches up to 100 memories, uses only the first 50 (locked ones excluded), truncates to the first 20 for the prompt context. No conversations, no action items, no persona, no existing/completed/abandoned goal list (so it can suggest a duplicate or already-completed goal), no task linking, and a much shorter single-step prompt. On failure or empty memories, falls back to a hardcoded "Learn something new every day" / "Track your daily progress" suggestion.

**Windows status:** Present-but-weaker — Windows gets *a* suggestion, but it's meaningfully less personalized and can duplicate existing/completed/abandoned goals since the backend endpoint has no visibility into goal history.

**Value / notes:** High — same underlying capability exists cross-platform, but the quality gap is large and is compounded by Windows lacking the automatic-generation feature that would otherwise mask an occasional weak suggestion.

## AI goal insight/advice ("what should I do this week")

**What it is:** Given a goal, get one specific actionable step for the week, grounded in recent conversations/chat/memories.

**Where (Mac):** `GoalsAIService.getGoalInsight(goal:)` (local Gemini call, `GoalPrompts.goalAdvice`, fetches 15 memories + 10 completed conversations) — surfaced via `GoalRowView`'s "Get insight" action in `GoalsWidget.swift`.
**Where (backend, shared, richer):** `GET /v1/goals/{goal_id}/advice` → `backend/utils/llm/goals.py::get_goal_advice` / `_get_goal_context` — actually richer than the Mac-local version (hybrid retrieval: vector search for goal-relevant conversations + last-7-days recent conversations + recent chat messages + memories).

**Windows status:** Absent from the UI — `Goals.tsx` has no "Get insight"/advice affordance at all, even though the backend endpoint Windows could call is arguably the best version of this feature across all three implementations.

**Value / notes:** Medium — pure UI gap; the backend capability already exists and is unused by Windows.

## Goal progress auto-extraction from conversations

**What it is:** After every conversation/chat message, Mac checks all active goals for a mentioned progress value (e.g., "just hit 1k users") and updates progress automatically without the user touching the Goals page.

**Where (Mac):** `GoalsAIService.extractProgressFromAllGoals(text:)` / `extractProgress(text:goal:updateIfFound:)` (local Gemini call per goal, `GoalPrompts.extractProgress`).

**Windows status:** Not found in the Windows renderer or a repo-wide grep of `desktop/windows/src`; progress can only be set manually (typing a number) on the Goals page or Home widget. Whether the *backend's* conversation post-processing pipeline independently does anything equivalent for goal progress is outside this audit's file scope (backend `utils/llm/` conversation post-processing) and would need separate verification, but there is no Windows-side hook triggering or displaying automatic progress capture either way.

**Value / notes:** Medium — silent, ambient progress tracking is a meaningful "Omi does this for you" feature; its absence means Windows goals only move when manually updated.

## Goal completion celebration

**What it is:** A full-screen dim + confetti + animated "Goal Completed!" overlay (3-phase animation) triggered by a `.goalCompleted` notification.

**Where (Mac):** `GoalCelebrationView.swift`.

**Windows status:** Present-but-weaker — `Goals.tsx`'s `updateProgress` fires a plain toast (`toast('Goal complete 🎉', ...)`) when progress reaches target; no full-screen animation.

**Value / notes:** Low — cosmetic, but a designed moment-of-delight Mac has and Windows doesn't.

## Cross-references

- **AI user profile** (`AIUserProfileService`, daily-regenerated, feeds both task prioritization and goal generation) is itself a Mac-local-only artifact with no Windows equivalent — flagged here since both Tasks and Goals gaps above depend on it, but it's not owned by this audit area specifically.
- The floating-bar agent + desktop-automation tool stack that `ProactiveTaskExecute` depends on is a large cross-cutting capability outside Tasks/Goals scope.

## Spotted outside my scope

- Focus/Insight/Memory assistant local-Gemini patterns (own `*AIService`/`*Storage` per assistant) mirror the same "local Gemini call + local SQLite + backend sync" architecture seen here in Tasks/Goals — worth a consistent write-up if not already covered by the Focus/Insight audit agent.
- `backend/utils/llm/goals.py::get_goal_advice`'s hybrid-retrieval context building is genuinely good and entirely unused by Windows — a quick win if the Windows Goals page ever adds an "insight" button, independent of any Mac-parity work.
