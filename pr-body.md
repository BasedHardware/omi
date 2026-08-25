fix(desktop/llm): cache-efficient datetime injector; stop 2026-is-wrong Insight/Focus cards

Closes SCA-358

Base: `origin/main` @ `b059e8cdf08af55d72dc2cd69376615c69e06919`

## Why

Community report (desktop-app, ~2026-08-21): Omi Insight/Focus cards claimed the
system clock is stuck in 2026 and that an email dated 2026 should be
double-checked — while the real calendar date IS 2026. Root cause (verified on
main, swarm-reviewed in SCA-358):

1. The shipped Insight and Suggestion (Focus) default prompts carried a GOOD
   EXAMPLE teaching the model that 2026 dates are mistakes
   (`"You've scheduled this for 2026 — double-check the year"`), with a verbatim
   port on Windows.
2. Those lanes never told the model the current date: Insight's user prompt sent
   `Time: h:mm a, EEEE` (time-of-day + weekday, no year), Suggestion sent no
   date at all. With no anchor the model fell back to its training-cutoff year —
   and the example confirmed the misread.

## What changed

**The reported bug (macOS + Windows):**
- `InsightAssistantSettings` v3 / `SuggestionAssistantSettings` v8 (mac) and
  insight `CURRENT_PROMPT_VERSION` 3 (Windows): retire the wrong-year example in
  favor of the year-agnostic `"scheduled this for yesterday — double-check the
  date"`, and add a `DATE GROUNDING` section — dates in the current year or
  later are normal; never say the clock/calendar/year is wrong; flag a date only
  when it is wrong on its own terms (#8501-style critic). Version bumps wipe
  saved custom prompts via the existing migration paths.
- Insight's per-call user prompt now carries
  `Date/Time: Tuesday, August 25, 2026 at 3:45 PM (America/New_York)` — the
  model also hand-writes SQL over UTC timestamps and needed the anchor.
  Suggestion's user prompt carries `Today is yyyy-MM-dd (EEEE)`.

**Shared injector (extend, don't reinvent):**
- macOS `ChatPromptBuilder` (beside the existing `currentTimePrompt`):
  `currentCalendarDay(at:timeZone:)` → `yyyy-MM-dd (EEEE)` (day-stable) and
  `currentLocalDatetime(at:timeZone:)` → full local datetime + IANA zone.
- Windows: `currentTimeBlock` extracted from `desktopChatPrompt.currentTimePrompt`.
- Backend: `utils.llm.temporal.current_date_for_uid` (existing).

**Other sites the swarm verified as judging "now" (refuter dropped goals,
director, home suggestions, profile merge, and working-observations as not
date-dependent or already anchored):**
- macOS task re-ranking (`TaskPrioritizationService.rerankPrompt`): states
  today + labels dues as UTC ISO (was: due-proximity judged with no anchor).
- macOS `TaskChatRuntime.query`: wraps the user prompt with
  `ChatPromptBuilder.currentTimePrompt` — the same wrap main chat applies.
- Backend proactive notifications: `_process_mentor_proactive_notification` now
  passes `current_date_for_uid(uid)` to gate/generate/critic (was: silent UTC
  fallback, wrong by up to a day for non-UTC users; desynced the year guard
  near local midnight).
- Windows `assembleTurnContext`: injects the current-time block for every
  surface except main_chat (which wraps upstream in mainChat.ts) — pill/task/
  workstream agents resolve "Friday"/"due next week" against
  `create_action_item due_at` and previously had no clock anywhere.

## Cache contract

Every static/cached system prompt stays byte-stable: no live clock enters a
cached prefix. Live datetime rides only in per-call user turns (or Gemini
`uncachedPrompt`-style volatile sections); calendar-day agents get date-only
`yyyy-MM-dd (EEEE)`, day-stable within a timezone; full local datetime + IANA
zone where local times or UTC timestamps are discussed.

## Tests

- macOS `ProactiveDateGroundingTests`: (a) wrong-year example retired from both
  defaults + DATE GROUNDING present, (b) user prompts carry today's date from a
  controllable clock seam (`analysisClockLine`, `SuggestionAssistant.userPrompt`,
  `rerankPrompt`), (c) default system prompts contain no live timestamp,
  (d) rerank prompt labels UTC dues.
- macOS `TaskChatKernelIdentityTests`: source tripwire pins the task-chat
  current-time wrap (with `omi-test-quality` annotation).
- Windows `insight/prompt.test.ts`: example retired, version bump wipes saved
  custom prompts, deterministic `formatDateTime`, Phase-1 head regex.
  `turnContext.test.ts`: clock block for floating/task surfaces, absent for
  main_chat, injected clock used. `desktopChatPrompt.test.ts` unchanged and
  green against the refactored helper.
- Backend `test_pipeline_anchors_prompts_to_user_timezone_date`: drives the real
  3-step pipeline with a sentinel date; every rendered prompt must carry it.

## Verification

- macOS: `xcrun swift test --package-path Desktop --filter
  'ProactiveDateGroundingTests|TaskChatKernelIdentityTests'` — 34 tests, 0
  failures; broader affected suites (`SuggestionAssistantTests`,
  `SuggestionPromptContractTests`, `TaskAssistantPromptTests`, `ChatPromptsTests`,
  `ContextBucketPromptAssemblerTests`) — 38 tests, 0 failures.
- Windows: `pnpm vitest run src/main/assistants/insight/
  src/main/agentKernel/desktopChatPrompt.test.ts
  src/main/agentKernel/turnContext.test.ts src/main/ipc/mainChat.test.ts` —
  156 passed; `pnpm typecheck:node` clean.
- Backend: `backend/.venv/bin/python -m pytest
  tests/unit/test_mentor_notifications.py` — 50 passed;
  `test_insight_date_grounding.py` — 16 passed;
  `test_connector_synthesis_helper.py` — 6 passed.
- Not dogfooded in a signed production app (per task constraints: no launch of
  `/Applications/Omi.app`); the changed surfaces are prompt builders exercised
  through the above tests.

## Product invariants

- INV-CHAT-1 — chat turn recording paths touched only additively
  (`TaskChatRuntime` prompt wrap; no journal/dedup semantics changed); the
  double-record guard suites above pass.
- INV-TASK-2 — no new automatic task-writing path; re-ranking prompt change
  only adds date grounding to the existing review prompt.

Failure-Class: FC-machine-timezone-timestamp-in-prompt
