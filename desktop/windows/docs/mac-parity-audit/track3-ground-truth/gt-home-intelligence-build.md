# Home intelligence loop — build note (closes P8)

The Windows port of macOS's What Matters Now recommendation loop, canonical
goals with focus, and personalized home suggestions. Ground truth extracted from
`DashboardIntelligenceStore.swift`, `WhatMattersNowSection.swift`,
`CanonicalGoalsStore.swift`, `HomeSuggestionsStore.swift`, and
`DashboardPage.swift` (the knows-list composition, rotation, and dismiss rules),
then verified against the backend contracts in
`backend/routers/task_recommendations.py` and `backend/routers/goals.py` before
any TypeScript was written.

## Module map

| Module | Mac source | Owns |
|---|---|---|
| `lib/intelligence/wireTypes.ts` | OmiApi.generated.swift structs | Snake_case wire types, lenient enum decode (unknown → `_unknown`, rows dropped later, payload never fails) |
| `lib/intelligence/feedbackOutbox.ts` | `PendingDashboardFeedback` queue | Durable per-owner outbox: `whatMattersNowFeedbackOutbox.v1.<uid>`, write-ahead, same-key overwrite, one-pass sequential replay, generation purge, pending later/dismiss row suppression |
| `lib/intelligence/dashboardStore.ts` | `DashboardIntelligenceStore` | Load gating on the candidates control (read mode only), 404-silent WMN, verbatim projection rules, do_now/later/dismiss with mac's exact idempotency-key formats, canonical goal create/focus/unfocus/lifecycle, `openRecommendation` with load-retry and open-before-feedback ordering, the declared-unused outcome seam |
| `lib/intelligence/knowsComposer.ts` | `HomeKnowsComposer` | Four diverse rows, per-source rotation `((r%n)+n)%n`, ask ≠ tip, question dedupe-by-text, `canRotate` |
| `lib/intelligence/homeSuggestions.ts` | `HomeSuggestionsStore` + composer | Daily per-owner personalized questions: context reads with per-source fault isolation, unavailable/thin/available classification, generation via the structured agent lane, 48-char first-person rules, `homePersonalizedSuggestions.v1.<owner>` day-stamped cache |
| `lib/intelligence/attribution.ts` | `TaskIntelligenceAttributionEvent` | `intervention_presented` once per intervention per store lifetime; `feedback_recorded` on server acceptance only, with the attribution chain id |
| `components/home/knows/*` | `HomeKnowsRowView` + knows list | 46px rows, insight reason popover ("Optional reason": already_handled / not_mine / not_useful; closing without choosing still dismisses with null), context menu (Later / Dismiss), error card with Retry, 7s rotation paused while a send is in flight, `rolling` chat-mode variant (top three over an empty thread) |
| `components/home/goals/*` | `FocusedGoalsSection` sheets | Focused chip row (≤5), All goals (Current/History, lifecycle menu, focus-replacement flow with mac's copy verbatim), Add goal (occurrence-id idempotency stable per sheet), goal detail |
| `pages/Goals.tsx` additions | canonical goals on the page | Focus star per card, focused count in the subtitle, page-palette replacement dialog driven by the store's 409 flow |
| `hub` wiring | DashboardPage lifecycle | The knows slot replaces the wordmark when rows exist (the branch HomeHub's comment called unreachable); `HubSuggestions` consumes the personalized feed; the chat panel's empty state hosts the rolling knows |

## Contract facts the port depends on

- Every WMN recommendation already carries a server-registered `intervention_id`
  (the server registers interventions during evaluation), so this surface never
  calls `POST /v1/task-intelligence/interventions`. The client-side
  ensureIntervention pattern belongs to the Suggested rail only.
- `GET /v1/what-matters-now` runs a full evaluate server-side and 404s for
  accounts outside the intelligence product; 404 clears the surface with no
  error. `POST /v1/what-matters-now/evaluate` is the context-director's entry
  point (mac: TaskContextualResurfacingService) and is deliberately unused here;
  `applyContextProjection` is the seam a future director port will call.
- Canonical goal mutations require `Idempotency-Key` + `X-Account-Generation`
  and are generation-fenced at the store boundary; the account generation comes
  from `GET /v1/candidates/control`, the same control the Suggested rail uses.
- Outbox entries minted under a superseded account generation are purged
  without sending (mac parity): the server would 409 them and the feedback no
  longer describes live state.

## Deliberate deviations from mac

- Out-of-rollout accounts see the legacy `HomeGoalsChips` active-goals row
  instead of nothing (mac renders nothing when the generation is unbound). A
  fallback beats an empty row during rollout; the legacy component is unchanged.
- Recommendation destinations all navigate to the Tasks surface: Windows has no
  workstream-thread UI yet, so thread destinations open Tasks rather than being
  dropped, and do_now feedback still records after the open.
- "Work on this with Omi" on the goal detail navigates to Tasks; mac starts an
  agent thread on the goal (`goal-detail-primary-v1`), which needs the kernel
  task_chat surface.
- The refresh/open/focus automation tools mac registers on
  `DesktopAutomationBridge` are not ported: Windows has no agent-action registry
  yet (the agentKernel control-tool manifest is a different, coordinator-scoped
  system). Tracked as a follow-up alongside the registry itself.
- Task-row dismissals in the knows list are session-only state (mac parity), and
  learned-insight rows are inert on open (mac parity) — both intentional.

## Verification

`npx vitest run` full suite green; the new suites cover the projection rules,
outbox semantics, feedback key formats, goal flows, composer slots, suggestion
classification/caching, attribution emission, and the component surfaces.
Mutation checks: widening the projection row cap and deleting the composer's
tip fallback each fail exactly the tests that pin them.
