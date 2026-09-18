# Mac→Windows Parity Audit — Proactive Assistants: Focus & Insight

> **Audit date: 2026-08-22 (rewrite).** Verified against the CURRENT repo, not against
> the 2026-08-20 audit's citations. Windows baseline actually checked this pass:
> `src/main/assistants/core/{coordinator,contextDetection,distributionGate,privacy,session,notify}.ts`,
> `src/main/assistants/focus/{focusAssistant,gating,context,prompt,models,gemini,persist,promptStore,stats,register}.ts`,
> `src/main/assistants/insight/{insightAssistant,gating,context,prompt,models,gemini,sql,persist,promptStore,register}.ts`,
> `src/main/glow/{glowWindow,glowGeometry,glowPresets}.ts`, `src/renderer/src/{glow.tsx,components/glow/GlowWindow.tsx}`,
> `src/renderer/src/pages/Insights.tsx` + `.test.tsx`, `src/renderer/src/components/insight/InsightToast.tsx`,
> `src/renderer/src/routes/manifest.ts`, `src/main/appSettings.ts`, `src/main/ipc/assistantSettings.ts`,
> `src/main/ipc/db.ts`, `src/renderer/src/components/settings/tabs/{NotificationsTab,RewindTab,GeneralTab}.tsx`,
> `src/renderer/src/lib/insightEngine.ts` (now retired — see below), `src/main/insight/{state,toastWindow}.ts`, plus
> `git log` on every file above to date each claim against both the coordinator's 2026-07-19 landing and the
> 2026-08-20 audit date. Also spot-checked corresponding tests (`*.test.ts`) for behavioral confirmation.

## Changed since the 2026-08-20 audit

**The old audit's Windows baseline was already obsolete on the day it was written.** A full
proactive-assistant framework — coordinator, Focus (with glow, cooldown, backend sync), and a rewritten
two-phase Insight — shipped to `src/main/assistants/` between **2026-07-14 and 2026-07-19**, more than a
month before the audit's 2026-08-20 date. The old audit's Windows citations (`insightEngine.ts`,
`insightGate.ts`, `insightPrompt.ts`, `insightActivity.ts` as the *live* Insight implementation) describe
code that was **retired on 2026-07-15** — `insightEngine.ts` itself now opens with the comment "RETIRED
(Track 3 P4): the Insight extraction loop moved to the main process." The old audit never found the
replacement and graded the dead code as current.

Concretely, of the ~19 rows in the table below, **12 changed status** from Absent/weaker to Present or
Partial:

- **Pluggable assistant coordinator** — claimed absent; a full port exists (`core/coordinator.ts`,
  `contextDetection.ts`, `distributionGate.ts`, `privacy.ts`), committed 2026-07-14, hardened 2026-07-19.
- **Focus Assistant** — claimed absent entirely; a complete vision-based focused/distracted pipeline exists
  (`focus/focusAssistant.ts`), committed 2026-07-14.
- **Focus glow overlay** — claimed absent; a click-through halo exists (`main/glow/*`), committed 2026-07-14,
  refined 2026-07-19. It is arguably a *better* implementation than Mac's (see below), not merely a port.
- **Focus session storage/stats** — claimed absent; a data model, persistence, and stats computation exist
  and are unit-tested (`focus/persist.ts`, `focus/stats.ts`), though still with no reader UI (see caveats).
- **Focus coaching notifications** — claimed absent; implemented with the same distraction/refocus
  asymmetry and cooldown as Mac (`focus/gating.ts`).
- **Insight two-phase SQL-investigation + vision confirmation** — claimed entirely absent ("Windows sends
  only an OCR-text summary, no image, no tool-calling"); a faithful two-phase, tool-calling, vision-grounded
  pipeline exists (`insight/gemini.ts`, `insight/sql.ts`, 867 lines of hardened read-only SQL sandboxing),
  committed 2026-07-14/15.
- **Insight history/browse UI** — claimed absent; a routed `Insights.tsx` page exists with search, category
  filters, mark-all-read, dismiss, and clear, committed 2026-07-16 as "persistent Insights history page (Mac
  parity)."
- **Insight synced to backend as a memory** — claimed absent for both Focus and Insight; both now dual-write
  to `/v3/memories` on every verdict/insight (`focus/persist.ts`, `insight/persist.ts`).
- **User-profile/goals/tasks context in prompts** — claimed entirely absent; Focus's prompt now includes the
  AI user profile, up to 10 goals, 50 tasks, and 50 core memories (`focus/context.ts`, `focus/prompt.ts`),
  matching Mac's caps exactly. (Insight correctly has no goals/tasks block — neither does Mac's.)
- **Notification frequency throttle (0–5 levels)** — claimed absent; a global + per-assistant rate limiter
  with snooze exists (`core/notify.ts`) and is exposed as the existing 0–5 slider in Settings → Notifications.
- **Developer test-runner tooling** — claimed absent; dev-gated IPCs exist for both assistants
  (`focus:analyzeNow`, `insight:analyzeNow`, `insight:transportSmoke`, `insight:debugActivity`,
  `insight:debugSql`, `insight:debugIsEnabled`) — not a dedicated replay-UI window like Mac's, but real QA
  tooling, so this moves from Absent to Partial.

**Confirmed still accurate** (the old audit got these right): no Focus dashboard/stats *page* exists; the
Insight confidence threshold and system prompt are still hardcoded/unwritable from any UI; Focus's own
excluded-apps list and cooldown-minutes setting exist in the data model but have **zero write path** — a
narrower and more specific gap than the old audit described, not a broader one; the per-app exclusion
mechanism for Insight is still a substring denylist, not an exact list; Gemini model-fallback telemetry
(`record_fallback`) does not exist, though the "why" turned out to be a deliberate, evidenced
model-tiering strategy rather than a missing feature (see the Gemini section below).

## Summary table

| Feature | Mac location(s) | Windows status (2026-08-22) | Value (H/M/L) |
|---|---|---|---|
| Pluggable assistant coordinator (`ProactiveAssistant` protocol, backpressure, context-switch gating, debounce/flush) | `Core/AssistantCoordinator.swift`, `AssistantProtocol.swift`, `ContextDetection.swift`, `ProactiveAssistantOrchestrationPolicy.swift` | **Present** — `main/assistants/core/coordinator.ts` (+ `contextDetection.ts`, `distributionGate.ts`, `privacy.ts`), a full port with per-assistant backpressure, title-normalizing context-switch detection, and a debounce/fallback distribution gate | M |
| Focus Assistant (real-time focused/distracted classification) | `Assistants/Focus/FocusAssistant.swift` | **Present** — `main/assistants/focus/focusAssistant.ts`, vision-based, cooldown + error backoff + stale-run guards | H |
| Focus glow overlay (colored ring around the active window) | `UI/GlowEdgeWindow.swift`, `GlowBorderView.swift`, `Services/OverlayService.swift` | **Present** — `main/glow/{glowWindow,glowGeometry,glowPresets}.ts`, a single click-through window that follows the target window; toggle in Settings → Notifications ("Focus glow") | H |
| Focus session history + stats computation | `Assistants/Focus/FocusStorage.swift`, `FocusModels.swift` | **Present (data layer only)** — `focus/persist.ts` writes rows, `focus/stats.ts` computes daily/all-time stats, both unit-tested; no IPC or UI reads them yet | M |
| Focus dashboard page (status banner, stats grid, distraction list, session history/search) | `MainWindow/Pages/FocusPage.swift`, `Components/FocusSummaryWidget.swift` | **Absent** — confirmed: no route, no IPC exposing `listFocusSessions`/stats to the renderer | M |
| Focus coaching notifications (distraction/refocus messages, cooldown) | `FocusAssistant.swift` + `NotificationService.swift` | **Present** — `focus/gating.ts` (`decideTransition`), routed through the shared throttle (`core/notify.ts`) | H |
| Focus exclusion list + custom system prompt editor | `FocusAssistantSettings.swift`, `UI/FocusTestRunnerWindow.swift` | **Absent from the UI** — `focusExcludedApps`/`focusCooldownMinutes` exist as settings and are read by the gate, but are **not** in `ipc/assistantSettings.ts`'s writable-key allowlist, so nothing can ever set them away from their defaults (`[]`, 10 min) | L |
| Insight Assistant (proactive tips) | `Assistants/Insight/InsightAssistant.swift` | **Present, close to parity** — `main/assistants/insight/insightAssistant.ts`, a from-scratch main-process rewrite that replaced the old renderer engine on 2026-07-15 | M |
| Insight two-phase SQL-investigation + vision confirmation | `InsightAssistant.swift` (`runAdviceExtraction`, `buildPhase1Tools`/`buildPhase2Tools`) | **Present** — `insight/gemini.ts` (`runTwoPhasePipeline`, ≤7 Phase-1 + ≤5 Phase-2 iterations, native tool-calling), `insight/sql.ts` (hardened read-only `execute_sql` sandbox) | M |
| Insight system prompt editor + confidence slider (user-tunable) | `Assistants/Insight/InsightAssistantSettings.swift`, `UI/InsightPromptEditorWindow.swift` | **Absent** — `insight/promptStore.ts` has the versioned-reset storage shape ready, but no setter/IPC/UI exists; `MIN_CONFIDENCE = 0.85` is still a hardcoded constant in `insight/gating.ts` | L |
| Insight history / browse UI (search, category filter, mark read, dismiss, delete) | `MainWindow/Pages/InsightPage.swift` | **Present, but local-only** — `pages/Insights.tsx`, routed (`routes/manifest.ts`, nav order 5), with search/category tabs/mark-all-read/dismiss/clear; reads the **local** `insights` table only, so read/dismissed state does not sync cross-device the way Mac's backend-memories-backed page does | M |
| Insight synced to backend as a searchable memory (cross-surface) | `InsightAssistant.swift` → `APIClient.shared.createMemory(...)` | **Present** — `insight/persist.ts` dual-writes to `/v3/memories` (category `interesting`, tags `["tips", category]`), epoch-guarded against sign-out races | H |
| User-profile/goals/tasks context injected into proactive prompts | `AIUserProfileService`, `GoalStorage`, `ActionItemStorage`, `MemoryStorage` in `FocusAssistant.refreshContext()` / `InsightAssistant.runAdviceExtraction()` | **Present for Focus** (profile + ≤10 goals + ≤50 tasks + ≤50 core memories, `focus/context.ts`/`prompt.ts`, matching Mac's caps exactly); **profile-only for Insight**, which matches Mac — Mac's own Insight has no goals/tasks block either | M |
| Per-app exclusion (exact list vs. keyword denylist) | `FocusAssistantSettings.isAppExcluded`, `InsightAssistantSettings.isAppExcluded` | **Still partial** — Insight uses a free-text substring `denylist` (`insight/gating.ts` `isUserDeniedApp`); Focus's settings model has an exact-match `focusExcludedApps` list (`focusAssistant.ts` `isExcludedApp`), but it has no UI path to populate (see above) | L |
| Notification frequency throttle (0–5 levels, global + per-assistant rate limit) | `NotificationService.swift` (`shouldAllowProactiveNotification`) | **Present** — `core/notify.ts` (`NotificationThrottle`), global clock + redundant per-assistant clock + snooze, backing the existing 0–5 slider in Settings → Notifications | M |
| Gemini client resilience (model fallback, retry/backoff, fallback telemetry) | `Core/GeminiClient.swift` | **Partial, different strategy** — retries transient 429/503 with Mac's exact 2s/8s backoff on both Focus and Insight; no Pro→Flash *runtime* fallback or `record_fallback` telemetry. Instead each assistant is deliberately pinned to a cost/quality-evidenced model tier (`modelPins.test.ts`, dated 2026-08-17): Focus stays on the PT-reserved `gemini-2.5-flash`, Insight runs on `gemini-2.5-flash-lite` | L |
| Developer test-runner / debug tooling | `UI/FocusTestRunnerWindow.swift`, `UI/InsightTestRunnerWindow.swift` | **Partial** — dev-gated IPCs exist (`focus:analyzeNow`, `insight:analyzeNow`, `insight:transportSmoke`, `insight:debugActivity`, `insight:debugSql`, `insight:debugIsEnabled`); no dedicated replay-past-screenshots window UI | L |
| Notification style choice (in-app toast vs. native) + denylist + test-send | `RewindTab.tsx` (insight section) | **Present**, Windows-only convenience (unchanged) | — |
| Meeting-detection toast sharing the same acrylic window | `main/insight/toastWindow.ts` (`showMeetingToast`) | **Present**, Windows-only, unchanged (different area) | — |

## Pluggable assistant coordinator

- **What it is:** The shared loop every proactive assistant plugs into: a `ProactiveAssistant` protocol
  (`isEnabled`, `analyze`, `handleResult`, optional `shouldAnalyze`/`onContextSwitch`/`needsFrameDuringDelay`/
  `clearPendingWork`), per-assistant backpressure (busy → skip, never queue), and pure policy gates deciding
  when to distribute a frame at all.
- **Where (Windows):** `src/main/assistants/core/coordinator.ts` (442 lines), `contextDetection.ts` (48
  lines), `distributionGate.ts` (67 lines), `privacy.ts` (25 lines). Wired up by each assistant's own
  `register.ts` calling `registerAssistant()`.
- **How it works:** Windows differs from Mac in one structural way the code documents explicitly: Mac's
  capture plugin *pushes* frames into the coordinator; Windows has no such push signal, so the coordinator
  *polls* `latestRewindFrame()` on its own tick (`coordinator.ts:9-17`), using a cheap "did the newest
  capture timestamp move" pre-check (`captureSignal`) to skip most DB reads, and a `lastFrameKey` dedup so a
  re-read of the same row (capture paused because the user is idle) is never re-distributed
  (`coordinator.tick`, lines 235–299). Cadence lives on the coordinator's own tick (3s base, ×3 on battery —
  `DEFAULT_BASE_INTERVAL_MS`/`DEFAULT_BATTERY_MULTIPLIER`), matching Mac's numbers exactly. Context-switch
  detection (`contextDetection.ts`) normalizes window titles — stripping braille spinner glyphs, other
  spinner glyphs, clock-style timers, terminal dimensions, and unread counts — so a re-rendering title is
  not treated as a switch, exactly Mac's rationale. On a real switch, every registered assistant's
  `onContextSwitch` fires (with the title withheld if the new context failed the privacy gate — the protocol
  explicitly documents this contract at `coordinator.ts:50-62`), a 60s post-switch quiet window opens
  (`DEFAULT_ANALYSIS_DELAY_MS`), and `clearPendingWork` fires so in-flight work targeting the old context is
  discarded. `distributionGate.ts` adds a 3s debounce that collapses rapid app-hopping into one distribution,
  with a fallback floor (60s generally, 15s for messaging apps — the same shared `MESSAGING_APPS` list the
  Task assistant reuses) so a title that never stops churning can't starve the assistants completely.
  Per-assistant backpressure (`analyzing` Set) means a slow `analyze()` causes the *next* frame to be skipped
  for that assistant only, never queued.
- **Verdict on the old audit:** The old claim — "Absent... one hand-rolled interval timer... no
  `distributeFrame`/`shouldAnalyze`/`onContextSwitch`-shaped abstraction anywhere" — is simply false as of
  2026-08-22, and was already false when written: `coordinator.ts` was committed 2026-07-14 and hardened
  2026-07-19 (`fix(windows): coordinator audit — port Mac's distribution gate, fail-safe the throttle`),
  five weeks before the 2026-08-20 audit date.
- **Value / notes:** Medium, as before — it's scaffolding, not directly user-visible, but everything else in
  this document depends on it existing, and it does.

## Focus Assistant

- **What it is:** A background loop that screenshots the active window, asks Gemini whether the user is
  focused or distracted (grounded in profile/goals/tasks/memories), and reacts on a *transition*: halo,
  optional coaching notification, session persistence, cooldown.
- **Where (Windows):** `main/assistants/focus/focusAssistant.ts` (311 lines) is the wiring; the pure
  decisions live in `gating.ts` (145 lines), `models.ts` (68 lines), `prompt.ts` (144 lines), `context.ts`
  (125 lines); the network call is `gemini.ts` (188 lines); persistence is `persist.ts` (117 lines).
  Committed 2026-07-14 (`feat(windows): Focus assistant — first proactive assistant (faithful Mac port)`).
- **How it works:**
  - `passesLocalGates` (lines 118–144) hard-skips the lock screen (`logonui`/`lockapp`), the user's own
    `focusExcludedApps`, then defers to `shouldSkipAnalysis` (`gating.ts:59-79`) — Mac's exact priority
    order: error backoff first (so an outage doesn't retry every frame forever), then cold start, then a
    context change (which *bypasses* the cooldown), then the cooldown, then "focused + unchanged context"
    (the steady-state no-op that makes a static IDE window free to watch).
  - The Gemini call (`gemini.ts`) is a single vision request against `gemini-2.5-flash` with a strict JSON
    schema (`models.ts` `FOCUS_RESPONSE_SCHEMA`: `status`/`app_or_site`/`description` required, `message`
    optional), retried on transient 429/503 with Mac's 2s/8s backoff.
  - `context.ts` assembles the grounding block: the AI user profile (local read), plus goals/tasks/core
    memories fetched from the backend and cached 120s so the 3s tick doesn't hammer the API; each source
    degrades to `[]` independently on failure. `prompt.ts` formats this with Mac's exact caps (10 goals, 50
    tasks, 50 memories) plus up to the last 10 analyses as a history block, so the model can vary its
    coaching language and reason about trends — matching the old audit's Mac description almost verbatim.
  - `gating.ts`'s `decideTransition` is the state machine: going *distracted* is always reported (persist +
    red halo + cooldown + a notification prefixed with the app name); going *focused* is silent unless the
    previous notified state was `distracted` (green halo + a plain "back on track" message, no app prefix);
    a cold-start `focused` verdict persists silently. This is the exact asymmetry the old audit attributed to
    Mac, reproduced.
  - A monotonic `seq`/`lastCommittedSeq`/`minValidSeq` triple discards stale results — including one
    deliberate *improvement* over Mac documented in the code: `clearPendingWork` here also raises the
    validity floor, so a verdict formed against a context the user has since left is actually discarded;
    Mac's equivalent bumps its counter but never the floor its own guard checks, so the same discard is dead
    code on Mac (`focusAssistant.ts:81-91`).
  - Every verdict is epoch-guarded against the backend session (`persist.ts`) and dual-written: a local
    `focus_sessions` row plus a `/v3/memories` POST (category `system`, tags `["focus", status,
    "app:<name>"]`) — so Focus events are searchable cross-surface, matching Mac.
- **Verdict on the old audit:** The old claim of "Absent entirely" is false; it has been false since
  2026-07-14, five weeks before the audit.
- **Value / notes:** High, unchanged — this is one of the two headline proactive features. The only
  meaningfully open piece is user-facing configurability (see the exclusion-list and dashboard rows).

## Focus glow overlay

- **What it is:** A colored ring drawn around the active window for ~3.5s (red = distracted, green =
  refocused), click-through and non-focus-stealing.
- **Where (Windows):** `main/glow/glowWindow.ts` (391 lines), `glowGeometry.ts` (295 lines), `glowPresets.ts`
  (45 lines); renderer side `renderer/src/glow.tsx` + `components/glow/GlowWindow.tsx`. Committed 2026-07-14
  (`feat(windows): Focus halo — a click-through glow around the active window`), with a follow-up fix on
  2026-07-19 for a ring that could target the empty desktop.
- **How it works, and where it genuinely diverges from Mac (by design, not gap):**
  - **One window, not four.** The code's header explains why this is deliberate, not a shortcut: four
    axis-aligned edge windows (Mac's Accessibility-API workaround) cannot form a continuous rounded ring —
    each band owns a hard-cornered piece. Windows doesn't need the workaround: `setIgnoreMouseEvents(true)`
    makes a *whole* window click-through at the OS level, so one window draws one seamless ring.
  - **DWM extended frame bounds**, not `GetWindowRect`, for the target rectangle — the fix for a stray-bar
    defect the team hit and documented (`glowWindow.ts:20-22`).
  - **The window is primed once, off-screen, and never hidden** — parked at `(-32000, -32000)` and moved
    with `setBounds` for its whole life. A transparent frameless Windows `BrowserWindow` re-fades on every
    hide→show, so "hide" is a park and "show" is an unpark (`glowWindow.ts:24-28`, `prime`/`park`).
  - A paint-ack handshake (renderer confirms it painted via double-`requestAnimationFrame`, main unparks
    only on that ack, with a 150ms fallback) avoids ever revealing a stale composited frame at the new
    position.
  - While the halo is up, a 32ms `followTick` re-samples the foreground window and moves the ring with it
    (or dismisses it the instant the target minimizes, closes, or the user switches away) — Mac's version is
    a one-shot effect that does not track a moving/resizing target at all, so this is a case where Windows'
    port is *more* capable than the reference implementation, not less.
  - Appearance: three layered hue rings sharing one shadow stack (`glow.css`) at a fixed 0.85 peak opacity —
    the code carries an explicit product note not to brighten it (`glowPresets.ts:9-20`), the same "faint,
    not an alarm" intent the old audit attributed to Mac's SwiftUI gradient.
  - Gated by `AppSettings.glowOverlayEnabled` (default **off**, matching Mac's `assistantsGlowOverlayEnabled`
    default), toggled from Settings → Notifications ("Focus glow" — `NotificationsTab.tsx:141-150`).
- **Verdict on the old audit:** The old claim of "Absent... no overlay window infrastructure for this
  exists" is false; it shipped 2026-07-14.
- **Value / notes:** High, unchanged in importance, but the Windows implementation is worth calling out as a
  genuine improvement on the Mac reference (continuous ring, live target-tracking) rather than a lesser port.

## Focus session history, stats, and dashboard

- **What it is:** A local history of focused/distracted transitions with computed stats (minutes, focus
  rate, top distraction apps), and (on Mac) a page to browse them.
- **Where (Windows):** `focus/persist.ts` writes each verdict as a `focus_sessions` row (`ipc/db.ts
  insertFocusSession`); `focus/stats.ts` (96 lines) computes `FocusDayStats` — focused/distracted minutes,
  session/verdict counts, top-5 distracting apps by accumulated seconds, and a focus-rate percentage — from
  a newest-first session list, inferring each session's duration from the *next* (more recent) row's
  timestamp exactly as Mac's `FocusStorage.computeStats` does (documented at length in `stats.ts:1-10` to
  avoid a duration-direction bug). Both are unit-tested (`persist.test.ts`, `stats.test.ts`).
- **What's missing:** No IPC channel exposes `listFocusSessions`/`computeStats`/`todayStats` to the
  renderer (confirmed: grepping `main/ipc` for any `focus:*` handler beyond the dev-only `focus:analyzeNow`
  returns nothing), and no route/page reads them. The data model the old audit said was entirely absent
  actually exists and is well-tested; what's still true is that a user has no way to see it.
- **Value / notes:** Medium, unchanged rating, but the remaining work is now "wire up an IPC + build a page
  over an existing, tested data layer" rather than "build a Focus data model from scratch."

## Insight Assistant (Proactive Insights)

- **What it is:** A periodic pass that reviews recent screen activity and surfaces at most one high-value,
  non-obvious tip.
- **Where (Windows):** `main/assistants/insight/insightAssistant.ts` (204 lines) is the wiring; pure logic in
  `gating.ts` (55 lines), `context.ts` (101 lines), `prompt.ts` (190 lines), `models.ts` (255 lines); the
  network/tool-loop client is `gemini.ts` (409 lines); the SQL sandbox is `sql.ts` (867 lines); persistence
  is `persist.ts` (90 lines). Committed 2026-07-14/15 (`feat(windows): Insight assistant — faithful 2-phase
  tool-calling port of macOS`, `fix(windows): consult the user Insight denylist before sending screen content
  to Gemini`).
- **The single most important correction in this rewrite:** the old audit's entire "How it works (Windows)"
  section for Insight describes `src/renderer/src/lib/insightEngine.ts` — a renderer-hosted, single-shot,
  text-only summarizer — as the live implementation. That file was retired on **2026-07-15**, over a month
  before the 2026-08-20 audit, and now opens with: *"RETIRED (Track 3 P4): the Insight extraction loop moved
  to the main process... The renderer-side single-shot summarize+schema engine that used to live here
  (runInsightOnce) is gone."* Its only remaining job is starting unrelated session-relay hosts (AI profile,
  Rewind embeddings, pi-mono auth) under the same exported function name so `Home.tsx`'s caller didn't need
  to change. The old audit graded dead code.
- **How the current pipeline actually works (two-phase, tool-calling, vision-grounded — matching the old
  audit's *Mac* description almost feature-for-feature):**
  1. `context.ts` builds the Phase-1 grounding: a SQL aggregate over `rewind_frames` (top 30 app/window
     groups by count within the lookback window — Mac's exact shape), the AI user profile text, the last 30
     previous insights for dedup, and the user's preferred language (cached 1h) for a language directive.
  2. **Phase 1** (`gemini.ts` `runTwoPhasePipeline`, ≤7 iterations): native Gemini function-calling with
     `execute_sql`, `request_screenshot`, and `no_advice` as tools. The prompt (`prompt.ts:176`) explicitly
     tells the model to *"Scan OCR from the TOP 3-5 apps (not just the dominant one)... Skip apps with < 10
     screenshots"* — verbatim the instruction the old audit attributed only to Mac.
  3. `execute_sql` is backed by `sql.ts`: read-only `SELECT`/`WITH` only, a two-table allowlist
     (`rewind_frames`, its FTS mirror), an unsuppressible outer `LIMIT` wrap the model cannot smuggle past
     via a string literal or subquery, a 200-row cap with 500-char cell truncation, and structural rejection
     of recursive CTEs / cartesian joins (since `better-sqlite3` runs synchronously on the main thread with
     no query-interrupt API, either shape would freeze the app). This is materially *more* hardened than a
     minimal "give the model SQL access" implementation would need to be.
  4. **Phase 2** (≤5 iterations): the requested screenshot is loaded and sent as `inlineData` alongside the
     Phase-1 findings; the model may cross-reference via `execute_sql` again — the prompt explicitly says to
     check "if the issue was already resolved" before calling `provide_advice` — before calling
     `provide_advice` or `no_advice`.
  5. `gating.ts`'s `passesConfidence` applies the same `MIN_CONFIDENCE = 0.85` floor as Mac, still hardcoded.
  6. `persist.ts` dual-writes: a local `insights` row plus a `/v3/memories` POST (category `interesting`,
     tags `["tips", category]`), epoch-guarded against a sign-out mid-pipeline exactly like Focus.
  7. Delivery goes through the same shared `core/notify.ts` throttle Focus uses — Insight never glows, it
     only ever notifies (a genuine, correctly-modeled Mac asymmetry, not a gap).
  8. Model tier is `gemini-2.5-flash-lite` for both the primary and (nominal) fallback slot — a deliberate,
     evidenced choice (`modelPins.test.ts`, 2026-08-17: Flash-Lite is the shared/on-demand tier so Insight
     never competes with Task extraction for a saturated Provisioned-Throughput reservation), not Mac's
     Pro-with-Flash-fallback. There is no `record_fallback`-style telemetry event.
- **What's still genuinely missing vs. Mac:** the confidence threshold and system prompt remain hardcoded —
  `promptStore.ts` has the versioned-reset *storage* shape ready (mirroring `focus/promptStore.ts`) but no
  setter is wired to any IPC or UI, so a user-authored custom prompt can never actually be saved; there is no
  prompt-editor or confidence-slider UI (confirmed: no `confidence` string appears in any settings component
  except the read-only display in `Insights.tsx`).
- **Verdict on the old audit:** "Present, but materially weaker," with (a)-(g) as the listed gaps, is false
  for (a) vision, (b) the SQL investigation loop, (c) the cross-reference-before-advising step, (f) backend
  sync, and half of (g) (the history page now exists, just local-only). What survives from that list: (d)
  confidence/prompt are still not user-tunable, and (e) still no goals/tasks context — though that second
  point matches Mac, whose own Insight also omits goals/tasks (only Focus gets that block on either
  platform), so it was never actually a gap.
- **Value / notes:** Medium, unchanged rating, but the remaining gap is now narrow and specific (prompt/
  confidence tunability, cross-device sync of read state) rather than "no vision, no investigation, dead-end
  local storage."

## Insight history / browse UI

- **What it is:** A page listing past insights with search, category filtering, mark-as-read, dismiss, and
  clear.
- **Where (Windows):** `renderer/src/pages/Insights.tsx` (306 lines), routed at `/insights` with a nav entry
  (`routes/manifest.ts:182-186`, order 5, `Lightbulb` icon) — reachable from the sidebar like any other page,
  not a hidden dev route. Committed 2026-07-16 as `feat(windows/insights): persistent Insights history page
  (Mac parity)`, with a nav-transition polish pass on 2026-07-19.
- **How it works:** Reads `window.omi.insightRecent(100)` (backed by the local `insights` SQLite table via
  `ipc/db.ts`) into a module-level cache for instant back-navigation. Supports free-text search over
  headline/advice/source-app, five category tabs (`productivity`/`communication`/`learning`/`health`/`other`
  — `health` kept, matching Mac's "legacy" note), an expandable detail row showing reasoning + confidence % +
  absolute timestamp, per-item dismiss (marks read, keeps the row), "mark all read", and "clear" (a
  confirm-gated permanent wipe of all rows via `insight:clearAll`).
- **What's different from Mac:** it reads and mutates the **local** `insights` table only — there is no
  per-item permanent delete distinct from the bulk clear, and dismissed/read state does not sync to another
  device the way Mac's page does (Mac's `InsightPage` is really a filtered view over the backend `memories`
  API with the `tips` tag, so read state travels with the account; Windows' page is device-bound).
- **Verdict on the old audit:** the claim "Absent... nothing in the renderer ever lists, searches, or lets
  the user revisit past insights... once a toast auto-dismisses, that insight is effectively gone" is false;
  it has been false since 2026-07-16.
- **Value / notes:** Medium, unchanged rating for the remaining gap (backend-memory-backed cross-device
  sync), but the UI itself — the larger part of the old "Medium" line item — already exists.

## Spotted outside my scope

- `src/main/usage/foregroundMonitor.ts` + `category.ts` + `usageAccumulator.ts` + `usageDay.ts` — unchanged
  from the old audit's note: a static foreground-app time tracker, not LLM-judged distraction detection.
  Still a different feature, likely owned by a usage/analytics area.
- `src/main/assistants/memory/*`, `src/main/assistants/tasks/*`, `src/main/assistants/goals/*`,
  `src/main/assistants/aiUserProfile/*` — **update from the old audit**: these are not merely "registered in
  the same pipeline" as a hypothetical future port — they are themselves complete, tested, actively
  maintained implementations (memory: 2026-07-15→2026-08-18; tasks: 2026-07-15→2026-08-20; goals:
  2026-07-15→2026-08-20; AI profile: 2026-07-14→2026-08-20) sharing the exact coordinator/backpressure/
  context-switch infrastructure documented above. Explicitly out of scope for this file (owned by other
  audit areas), but the old audit's framing of them as not-yet-built is as stale as its framing of Focus and
  Insight — worth flagging so whichever area covers them doesn't repeat the same staleness error.
- `Assistants/MemoryExtraction/MemoryAssistant.swift` and Mac's Task/Goal assistants — unchanged note: their
  Mac-side existence was never in question; see above for the Windows side.
- `main/assistants/aiUserProfile/service.ts` (`getLatestProfileText`) — the profile text both Focus and
  Insight inject; still likely a Memory-area concern, flagged only because Focus's context quality now
  depends on it directly (`focus/context.ts:112`).
- `src/main/screenSynth/state.ts` (RewindTab's "Synthesize now") — unchanged note: closer to
  Memory/Task-extraction territory than Focus/Insight.
