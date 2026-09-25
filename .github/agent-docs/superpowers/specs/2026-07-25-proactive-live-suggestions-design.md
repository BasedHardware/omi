# Live Proactive Suggestions — design

**Date:** 2026-07-25
**Status:** proposed
**Surface:** macOS desktop (`desktop/macos`), notch / floating control bar

## Problem

Omi watches the screen all day and knows a great deal about the user, but surfaces
none of it in the moment. The proactive stack that used to do this is still compiled
and registered — it is dark at default settings, and when it was on it did not earn
its interruptions.

This design turns it back on in a form that earns them.

## What actually happened to the old feature

Nothing was deleted. `desktop/macos/Desktop/Sources/ProactiveAssistants/` still builds,
and `ProactiveAssistantsPlugin.continueStartMonitoring()` still registers all four
assistants (Focus, Task, Insight, Memory). It went dark in three steps:

| Commit | Date | Effect |
|---|---|---|
| `815409b0` | 2026-04-24 | Proactive notifications became floating-bar/notch only, no macOS system banner |
| `48239de8` | 2026-06-07 | Default frequency **3 (Balanced) → 0 (Off)**, plus a one-time migration flipping existing users to Off |
| `4584c0a9` | 2026-06-23 | `assistant.isEnabled` now also requires `notificationsEnabled` — no notifications means no screen analysis at all |

The stated reason for `48239de8`, verbatim:

> Desktop's proactive notifications had ~25% click-through and high dismiss rates
> (PostHog, 90d). Make them opt-in instead of opt-out, keeping the feature fully intact.

And for `4584c0a9`:

> …this burned Gemini calls (and battery) for output users never saw.

**So the constraint is precision, not capability.** Rebuilding the same trigger at the
same threshold reproduces ~25% CTR and gets switched off again. Any design that does not
answer "why is this one better?" is not worth building.

## Why the old one missed

The existing `InsightAssistant` is not badly built. Its prompt
(`InsightAssistantSettings.defaultAnalysisPrompt`) is careful — a high bar, a
`no_advice` escape hatch, and explicit good/bad example sets including
`"Replying to group thread, not DM — check the recipient"`. The prompt is not the defect.

Two structural defects are:

1. **It fires on a blind timer.** `processLoop()` polls every 0.5s and analyzes whenever
   `extractionInterval` (default **600s**) has elapsed. The moment of firing is unrelated
   to what the user is doing. A suggestion routinely lands about a context the user left
   minutes ago — correct, but stale, which reads as noise.
2. **It is not grounded in what Omi knows.** Its only inputs are the current screenshot and
   SQL over the local `screenshots` table. It never consults the user's memories, open
   action items, or people. So it can only ever tell the user something derivable from
   their own screen — which is precisely the class of suggestion the prompt's own
   BAD EXAMPLES section rejects as obvious.

A suggestion is worth an interruption when it carries information the user does not
already have. The old assistant was structurally incapable of that.

## Design

A new `SuggestionAssistant` conforming to the existing `ProactiveAssistant` protocol,
registered alongside the other four. It keeps full breadth — any app, anything useful
or interesting — and buys precision from timing and grounding instead of narrowing.

### Scope

Explicitly **not** narrowed to a domain. LinkedIn, a code editor, a doc, a messaging
thread, a booking page — anywhere there is something worth doing or worth knowing, it
should be able to say so.

### Trigger: event-driven, never polled

Fires on **context switch** (`onContextSwitch`), which `AssistantCoordinator.checkContextSwitch`
already computes from app + normalized window title via `ContextDetection.didContextChange`.
It does **not** implement a `processLoop` timer.

Gates, in order, cheapest first — all mechanical, no model call until every one passes:

1. `isEnabled` — settings on (see Enablement below)
2. Not excluded — `RewindSettings.shared.isAppExcluded(appName)`
3. Cooldown elapsed since the last *evaluation* (not the last suggestion)
4. Not snoozed — `FloatingControlBarManager.shared.isSnoozed`
5. Not in a call / screen share — inherited from the capture loop's existing yields

This directly preserves the `4584c0a9` promise: an idle user costs zero Gemini calls,
because with no context switch there is no evaluation. Cost scales with genuine
app-switching, not with wall-clock time.

### Grounding: the part that is new

Before judging, the assistant assembles a context bundle from what Omi already knows,
scoped to the current app/window:

- **Memories** — local memory store, so the model can connect the screen to the user's
  own history
- **Open action items / commitments** — what the user owes and to whom
- **Recent screen history** — the existing FTS5 `screenshots_fts` index over `ocrText`
  and `windowTitle`, for "you were looking at this two hours ago" connections

These are on-device reads. The bundle is passed to the model alongside the screenshot.
The bar in the prompt then becomes answerable: *does this card tell the user something
they do not already have?*

### Judgment

One structured-output Gemini call via the existing `GeminiClient`
(`ModelQoS.Gemini.proactive`, through the Rust proxy `/v1/proxy/gemini/*` — no client
API key). Structured JSON, not the multi-iteration tool loop, so latency stays inside a
context switch.

Result carries `shouldSuggest`, `suggestion` (<100 chars), `reasoning`, `confidence`,
`category`. Suppressed unless `confidence >= minConfidence` (default **0.85**) and it is
not a semantic duplicate of a recent suggestion (last 10 retained, matching Insight's
existing dedup approach).

### Delivery

`NotificationService.sendNotification(...)` with a new `assistantId` of `"suggestion"`,
which routes through the already-hardened path to
`FloatingControlBarManager.shared.showNotification` and renders in the notch.
`FloatingControlBarView.barNotification(_:)` gains a `"suggestion"` branch.

Reusing this path inherits, for free: runtime-owner identity gating, the snooze gate,
the notification queue, the frequency throttle, and tap-to-open-as-chat with full
provenance via `FloatingBarNotificationContext`.

Deliberately **no** system banner (`deliverSystemBanner: false`) — that decision was made
in `815409b0` for a good reason and is not revisited here.

### Enablement

Ships behind its own setting, default **off**, consistent with the `48239de8` posture.
Turning it on does not require turning the other four assistants on. The existing 0–5
frequency ladder still applies as an upper bound on delivery rate.

## Files

**New**
- `ProactiveAssistants/Assistants/Suggestions/SuggestionAssistant.swift` — the actor
- `ProactiveAssistants/Assistants/Suggestions/SuggestionAssistantSettings.swift` — settings + prompt
- `ProactiveAssistants/Assistants/Suggestions/SuggestionModels.swift` — result types
- `Desktop/Tests/SuggestionAssistantTests.swift` — gate + dedup behavior

**Modified**
- `ProactiveAssistantsPlugin.swift` — register the assistant
- `FloatingControlBar/FloatingControlBarView.swift` — `"suggestion"` card branch
- `changelog/unreleased/20260725-live-proactive-suggestions.json`

Note: `ProactiveAssistantsPlugin.swift` is at its ratchet baseline of 1628 lines
(`.github/scripts/product_file_line_count_ratchet_baseline/desktop-swift-proactiveassistants.json`,
threshold 1500). Registration must stay minimal, and the baseline raise needs a
justification entry.

## Testing

- **Gate behavior** — excluded app, cooldown not elapsed, snoozed, and disabled each
  produce no model call. This is the cost contract from `4584c0a9` and is the most
  important thing to hold.
- **Confidence floor** — a result below `minConfidence` produces no notification.
- **Dedup** — a semantically repeated suggestion is suppressed.
- **Context-switch wiring** — a switch into a non-excluded app with cooldown elapsed
  reaches evaluation.

Tests call production APIs through a seam, not source-string inspection. No wall-clock
sleeps. Run via `./scripts/dev-feedback.py --once swift '<filter>'`, then the suite per
`desktop/macos/AGENTS.md`.

Live verification is a named dev bundle (`OMI_APP_NAME=omi-proactive ./run.sh`), driving
a real context switch and observing a real card — not a compile check.

## Risks

- **It fires too rarely and reads as broken.** Mitigation: cooldown and confidence are
  settings, tunable without a release. Accepted: a quiet feature beats a dismissed one.
- **Context switches are bursty** — cmd-tabbing through five apps could queue five
  evaluations. The cooldown is on evaluation, not delivery, which bounds this.
- **Grounding costs latency.** On-device reads only; if the bundle is slow the assistant
  should proceed with what it has rather than delay the card past relevance.
