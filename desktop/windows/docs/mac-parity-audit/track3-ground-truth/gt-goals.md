# Ground Truth — Goals (Track 3)

Verified against real source (not doc summaries) 2026-07-14. Sources read in full:
- `backend/routers/goals.py`, `backend/models/goal.py`, `backend/database/goals.py`, `backend/utils/llm/goals.py`
- Mac (frozen v0.12.72, `.worktrees/mac-ref/desktop/macos/`): `GoalsAIService.swift`, `GoalGenerationService.swift`,
  `GoalPrompts.swift`, `GoalCelebrationView.swift`, `GoalsWidget.swift`, `APIClient.swift` (goals extension, lines 3264-3410)
- Windows (`.worktrees/track3-proactive/desktop/windows/`): `src/renderer/src/lib/goals.ts`,
  `src/renderer/src/pages/Goals.tsx`, `omiApi.generated.ts` (goals advice bindings)

## 1. Backend goals routes — DEFINITIVE list (ground truth; Mac and Windows must conform to this, not the reverse)

All routes live in `backend/routers/goals.py`. This is the complete set — nothing else exists under `/v1/goals*`:

| Method | Path | Handler | Notes |
|---|---|---|---|
| GET | `/v1/goals` | `get_current_goal` | back-compat, first active goal or null |
| GET | `/v1/goals/all` | `get_all_goals` | up to 4 active goals |
| POST | `/v1/goals` | `create_goal` | body = `GoalCreate` (title, goal_type, target_value **required**, current_value, min_value, max_value, unit) |
| PATCH | `/v1/goals/{goal_id}` | `update_goal` | body = `GoalUpdate` (see §2) |
| PATCH | `/v1/goals/{goal_id}/progress` | `update_goal_progress` | **query param** `current_value: float` (not body) |
| GET | `/v1/goals/{goal_id}/history` | `get_goal_history` | query `days` (HistoryDays, default 30) |
| DELETE | `/v1/goals/{goal_id}` | `delete_goal` | hard delete |
| GET | `/v1/goals/suggest` | `suggest_goal` | rate-limited (`goals:suggest`), **zero caller payload** |
| GET | `/v1/goals/{goal_id}/advice` | `get_goal_advice` | rate-limited (`goals:advice`), 404 if goal not found |
| GET | `/v1/goals/advice` | `get_current_goal_advice` | advice for current active goal (delegates to the one above) |
| POST | `/v1/goals/extract-progress` | `extract_and_update_progress` | body `{text}`, rate-limited (`goals:extract`) |

**No `/v1/goals/completed` route exists anywhere in this file or `database/goals.py`.** `database/goals.py::get_all_goals(uid, include_inactive=True)` exists as a DB-layer helper but is **not wired to any router endpoint** — there is no way to fetch completed/inactive goal history over HTTP today.

## 2. `GoalUpdate` Pydantic model (`backend/models/goal.py:35-43`) — exact accepted fields

```python
class GoalUpdate(BaseModel):
    title: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = None
```

**No `is_active`, `completed_at`, `ended_at`, or `status` field exists.** Pydantic v2 default (`extra` unset = `'ignore'`) means unknown keys in the PATCH body are silently dropped during parsing — they never even reach `model_dump(exclude_unset=True)`. The router (`goals.py:71-74`):

```python
update_data = updates.model_dump(exclude_unset=True)
if not update_data:
    raise HTTPException(status_code=400, detail="No updates provided")
```

## 3. Confirmed: Mac's `completeGoal()` gets a 400, `getCompletedGoals()` gets a 404

`APIClient.swift:3382-3400` (`completeGoal(id:)`):
```swift
struct CompleteGoalRequest: Encodable {
  let is_active: Bool
  let completed_at: String
}
// PATCH v1/goals/{id} with { is_active: false, completed_at: <ISO8601> }
```
Since `GoalUpdate` has neither field, sending only these two produces an **empty** `update_data` after parsing → router raises **400 "No updates provided"**. Confirmed exactly (traced Pydantic parse → `exclude_unset` → router check).

`APIClient.swift:3376-3379` (`getCompletedGoals()`):
```swift
func getCompletedGoals() async throws -> [Goal] {
  let goals: [Goal] = try await get("v1/goals/completed")
  ...
}
```
`GET /v1/goals/completed` is **not a registered route** (§1) → FastAPI returns **404**. Confirmed.

Both calls are made from `GoalsAIService.fetchRichContext()` (`GoalsAIService.swift:176-187`, used by automatic `generateGoal()`) and from `GoalGenerationService.removeStaleGoals()` (`GoalGenerationService.swift:41-58`, which calls `completeGoal(id:)` on every stale AI goal it finds). **Both Mac features that depend on these calls are silently broken today** (errors are caught and logged, not surfaced) — this is not a hypothetical, it's Mac's live behavior against the live backend.

**Correct way to mark a goal complete, per the actual backend contract:** there is no dedicated completion endpoint. The only two paths that exist and work:
- `PATCH /v1/goals/{id}/progress?current_value=<target>` — drives progress to target. This is what Windows does today (`Goals.tsx` `toggleComplete` → `updateProgress(g, target)`), and derives "completed" client-side as `current_value >= target_value`.
- `PATCH /v1/goals/{id}` with `is_active`/other real `GoalUpdate` fields — could theoretically add an `is_active` field to the Pydantic model + a DB update path, but that is a **backend change**, not something Windows (or Mac) can do from the client today.

Windows' current approach (drive progress to target, treat `is_active === false` from `/v1/goals/all` as also-completed for goals the backend itself deactivates via `create_goal`'s max-goals eviction) is the only workable client-side pattern against the real API. This matches the wiring-audit's C10 finding exactly — Windows has already independently arrived at and documented this same conclusion in `Goals.tsx:49-57` comments.

## 4. `GET /v1/goals/{goal_id}/advice` — confirmed exists, request/response shape

- **Request:** no body, no query params beyond auth. Path param `goal_id`. Rate-limited via `auth.with_rate_limit(..., "goals:advice")`.
- **Response:** `AdviceResponse { advice: str }` (single field, plain string).
- **Backend implementation** (`utils/llm/goals.py::get_goal_advice` + `_get_goal_context`, lines 24-242): hybrid retrieval —
  1. Vector search (`query_vectors`, k=10) for conversations semantically related to the goal title, top 5 non-locked, overview truncated to 300 chars, tagged `[Relevant]`.
  2. Recent conversations (limit 20, completed, last 7 days), up to 10 more, overview truncated to 250 chars, tagged `[Recent]`.
  3. Recent chat messages (limit 15, last 10 kept, 200 chars each, chronological).
  4. Memories (limit 30, first 15 non-locked, 150 chars each).
  Builds one prompt with goal title/progress + all four context blocks (capped at 1500/800/600 chars respectively at prompt-assembly time), calls `get_llm('goals_advice')` (a dedicated/better model lane), strips quotes, returns.
- **Windows status:** the generated API client (`omiApi.generated.ts:9372` `get_goal_advice_v1_goals__goal_id__advice_get`, and `:9278` for the current-goal variant) exists and is fully typed, but is **never called** anywhere in `desktop/windows/src/renderer` outside its own generated-file definition (grepped the whole renderer tree — zero call sites). `Goals.tsx` has no "Get insight"/advice UI at all. This confirms the audit's claim precisely: this is the richest of the three goal-advice implementations (richer than Mac's own local `GoalsAIService.getGoalInsight`, which only does memories(15)+conversations(10), no vector search, no chat context) and it sits completely unused on Windows today — a pure UI-wiring gap, zero backend work needed.

## 5. `GET /v1/goals/suggest` — confirmed zero caller payload

`routers/goals.py:118-121`:
```python
@router.get('/v1/goals/suggest', ...)
def suggest_goal(uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "goals:suggest"))) -> dict:
    return suggest_goal_llm(uid)
```
No request body, no query params — `uid` only (via auth dependency). Confirmed.

**Handler** (`utils/llm/goals.py::suggest_goal`, lines 106-182): fetches up to 100 memories (`memories_db.get_memories(uid, limit=100, offset=0)`); if none, returns a hardcoded fallback (`"Learn something new every day"`, scale 0-10). Otherwise takes the first 50 non-locked memories' content, then **truncates to the first 20** (`memory_texts[:20]`) for the actual prompt context. No conversations, no action items, no persona, no existing/completed/abandoned goal list — so it can and will suggest a duplicate of an existing/completed/abandoned goal. Single-step prompt, `get_llm('goals')`, regex-extracts a `{...}` JSON blob, falls back to a second hardcoded suggestion ("Track your daily progress") on parse failure, or a third ("Make progress every day") on any exception.

## 6. Mac's client-side goal generation — full data-gathering + prompt (for the per-item porting decision)

`GoalsAIService.fetchRichContext()` (`GoalsAIService.swift:144-237`), fetched **in parallel, no truncation**:
- `APIClient.shared.getMemories(limit: 500)`
- `APIClient.shared.getConversations(limit: 100, statuses: [.completed])`
- `APIClient.shared.getActionItems(limit: 100, completed: false)` (includes task IDs, used for linking)
- `APIClient.shared.getPersona()`
- `APIClient.shared.getGoals()` (active goals)
- `APIClient.shared.getCompletedGoals()` — **broken, 404 (§3)**, so `goalHistory` is always `[]` in practice; `completed`/`abandoned` splits (by `completedAt != nil`) are therefore always empty too, silently degrading this to "memories + conversations + tasks + persona" only, not the full spec.

5-step prompt (`GoalPrompts.generateGoal`, `GoalPrompts.swift:24-79`): (1) understand persona/ambitions from persona+memories, (2) look at active conversations/tasks for unmet needs, (3) review existing/completed/abandoned goals to avoid duplicates, (4) synthesize one specific measurable goal with numeric target + implied timeframe, (5) link relevant existing task IDs. Structured JSON response incl. `linked_task_ids`. On success, calls `createGoal(..., source: "ai_suggested")` then links each valid task ID via `updateActionItem(id:goalId:)`.

**Cadence** (`GoalGenerationService.swift`): gated behind `kAutoGenerationEnabled` (**defaults to `false`** — off by default even on Mac), triggered from `onConversationCreated()` hook. On trigger: `removeStaleGoals()` first (any active AI-sourced goal — `source == "ai_suggested"` or legacy `"ai"` — with no `updated_at` change in ≥3 days gets `completeGoal()` called on it, which **currently 400s and silently no-ops per §3**), then `checkDailyGeneration()` — generates once if `<3` active goals and a new calendar day has passed since `kLastGenerationDate` (UserDefaults). `generateNow()` is the manual-trigger variant (used by the "Generate AI Goal" button in `GoalsWidget.swift`), retries up to 3x with 5s backoff.

**Two options for Windows, with tradeoffs (no nav-placement decision made here — flagged as G-C):**
- **A. Match Mac's client-side generation:** call `getMemories(500)/getConversations(100)/getActionItems(100)/getPersona()/getGoals()` directly from the Windows renderer via the existing `callAgentLLM`/agent-LLM path (already used in `lib/goals.ts` for onboarding), replicate the 5-step prompt, and skip `getCompletedGoals()`/`completeGoal()` (dead ends per §3) or replace them with a client-side filter over `/v1/goals/all` + `is_active`. Pro: matches Mac's much richer signal (500 memories vs backend's 20, task linking, no-duplicate goal history awareness once the 404 is worked around). Con: duplicates business logic Mac already has bugs in (the broken history fetch), couples Windows to the agent-LLM call path for a background/automatic feature, more surface to test.
- **B. Use the backend `/v1/goals/suggest` endpoint as-is (or extend it server-side):** Windows already calls this for the manual "Suggest" button. Pro: single source of truth, no client-side prompt duplication, backend changes benefit Mac too once Mac is fixed to also call the shared endpoint instead of local Gemini. Con: today's backend version is meaningfully thinner (20 memories, no conversations/tasks/persona/history, can suggest duplicates) — would need a backend enhancement PR to add conversations+tasks+persona+goal-history context before Windows would actually match Mac's quality; that's out of this audit's scope to implement, only to flag.

Automatic daily cadence + stale-goal cleanup itself (independent of which context-gathering option is chosen) has no Windows equivalent at all today — Windows is 100% manual-button-triggered.

## 7. Goals page UI spec — emoji, progress bar, confetti (all worth porting per brief)

**Emoji auto-icon** (`GoalsWidget.swift:363-534`, `goalEmoji` computed property): pure client-side keyword matching over `goal.title.lowercased()`, ~30 category buckets checked in a fixed priority order (money → growth/users → startup → invest → workout → running → weight → meditation → sleep → water → health → reading → learning → coding → language → writing → video → music → art → photo → tasks → habits → time/focus → project → travel → home → saving → social → family → relationship → win → growth/improve → star), each a simple `.contains()` substring check against a keyword list, first match wins. Default/fallback emoji is `🎯`. Rendered in a 36x36 rounded-rect tile (`backgroundRaised.opacity(0.9)`, corner radius 12) to the left of the goal row.

**Progress bar color** (`GoalsWidget.swift:168-181`, `progressColor` on `GoalRowView`) — this is a **discrete threshold-based solid color**, not a true gradient, keyed off `displayProgress` (0-1 fraction):
- ≥ 0.8 → `#22C55E` green
- ≥ 0.6 → `#84CC16` lime
- ≥ 0.4 → `#FBBF24` yellow
- ≥ 0.2 → `#F97316` orange
- < 0.2 → `OmiColors.textTertiary` (neutral gray)
Bar itself: 6px height (8px while dragging), rounded corners radius 3, background track `Color.white.opacity(0.12)`, draggable (drag gesture updates progress live, commits on release, rounds to nearest integer scaled between `minValue`/`targetValue`). White circular drag thumb (14x14, black shadow) always visible at the current fill edge.

**Completion celebration** (`GoalCelebrationView.swift`) — triggered by posting `NotificationCenter` `.goalCompleted` with the `Goal` object. Full-screen overlay, 4-phase animation:
1. **Dim** (t=0, 0.3s ease-out): black overlay fades to 0.4 opacity.
2. **Confetti** (t=0.3s, 0.3s ease-out): dim deepens to 0.5, `GoalConfettiView` appears — 40 particles (random mix of circles/rounded-rects), 9-color palette (yellow, gold `#FFD700`, green `#22C55E`-ish, blue, pink, orange, cyan, mint, purple + purple-70%), random size 4-10pt, random radial angle/distance (80-300pt) burst from center with random rotation up to 1080°, 0.8s ease-out animate-in, fades out starting at t=1.5s (relative to confetti view's own appear).
3. **Text** (t=0.8s, spring response 0.5/damping 0.7): "Goal Completed!" in 32pt bold with a yellow→orange→yellow horizontal gradient + yellow glow shadow, goal title below (18pt, white, centered), "`<target> <unit> reached`" caption (14pt, 70% white).
4. **Fade out** (t=3.0s, 0.5s ease-out): everything fades, state resets after +0.5s.

**Windows current state:** `Goals.tsx:174` — `updateProgress()` fires `toast('Goal complete 🎉', { tone: 'success', body: g.title })` when `value >= target_value`. No emoji-per-goal (goals list uses a plain checkbox, no icon), no color-threshold progress bar (flat `bg-white/45` / `bg-emerald-400/70` on completion only — two states, not five), no confetti/full-screen animation.

## 8. Windows current state — `lib/goals.ts` + `pages/Goals.tsx` full read

`lib/goals.ts` is **onboarding-only** (2 pure helpers + 2 network wrappers): `buildGoalPrompt(apps)` builds a single-shot prompt asking the agent-LLM for one measurable goal sentence (feeds in known apps from the onboarding brain-map for personalization, generic productivity goal otherwise); `parseTargetValue(text)` regex-extracts the first number from the goal text (defaults to 1, since `POST /v1/goals` 422s without `target_value`); `generateGoal(apps)` calls `callAgentLLM` with that prompt and trims/strips quotes; `createGoal(title)` POSTs to `/v1/goals` with the parsed target. This is a distinct, much thinner code path from the main Goals page — used only by `GoalStep.tsx` in onboarding.

`pages/Goals.tsx` (663 lines) is the main page: fetches `/v1/goals/all` (no `/v1/goals/completed` call — comment at line 40 explicitly notes it doesn't exist), splits active/completed **client-side** via `isCompleted()` (`is_active === false` OR `current_value >= target_value`), computes `progressPct`/`progressLabel` client-side. CRUD: create (POST, target_value defaulted to 1 if blank/invalid — comment notes POST 422s without it), inline-edit title (PATCH `/v1/goals/{id}` with just `{title}` — a real accepted field), delete (DELETE), update progress (PATCH `/v1/goals/{id}/progress?current_value=`, optimistic with rollback-on-failure). `toggleComplete()` explicitly documents (lines 184-187) that it drives progress to target/0 because "the live backend has no write path for is_active/status (PATCH rejects them with 400 'No updates provided') and no /complete route" — i.e., Windows engineers already independently verified §3 and §1 findings and wrote them into the source as comments. `getSuggestion()`/`acceptSuggestion()` call `GET /v1/goals/suggest` and preview-then-POST. **No advice/insight UI, no automatic generation, no goal-history/completed-goals view** (the "Completed" filter tab only shows goals that are `is_active === false` or progress-complete from the single `/v1/goals/all` fetch — there's no way to see goals from further back that have been fully evicted/aged out, since no history endpoint exists).

## Flags for orchestrator

- **G-C (nav placement / where automatic-generation UI or a settings toggle lives)** — not decided here, per brief. Flagging for the orchestrator/parity-lead to resolve.
- Whether to add a backend `include_inactive`/history-returning goals route (to fix Mac's 404 and give Windows a real "Completed" history view beyond what `/v1/goals/all` already returns) is a **backend-side decision** outside this ground-truth doc's scope — noting it here since both Mac and Windows would benefit, but it requires a backend PR (wiring `database.goals.get_all_goals(uid, include_inactive=True)` to a new route) that neither platform's client code can do unilaterally.
