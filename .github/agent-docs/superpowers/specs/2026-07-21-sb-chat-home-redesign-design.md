# Second Brain — Chat-First Home Redesign (dark)

**Date:** 2026-07-21
**Branch:** `redesign/second-brain-ui`
**Author:** Archit (design direction) + Claude

## Goal

Make the signed-in desktop experience a minimal, chat-first "second brain" that feels
like one cohesive dark app — matching the onboarding and sign-in the user already loves,
and the user's own home direction (reference: dark "Hey Archit. I'm ready." artifact).
Clean up the elements the user finds ugly (stat pills, chunky Capture/Listening buttons,
noisy tool-use chips), surface previously-orphaned pages, and keep everything the user
likes intact.

## Non-goals (do NOT touch)

- Sign-in (`SignInView.swift`) — untouched.
- Onboarding (`Onboarding/SecondBrain/SBOnboardingView.swift` + `SBOnboardingModel.swift`) — untouched.
- The floating control bar / notch (`FloatingControlBar/*`) — untouched.
- No new chat/session backend; the session model already exists and is reused as-is.
- No light theme this round. Dark only.

## Design decisions (locked with user)

| Decision | Choice |
|---|---|
| Aesthetic | Dark, one ink system (reuse `Theme/SecondBrainTokens.swift`) |
| Accent | White / neutral ink. **No purple** (Omi brand rule); no amber this round |
| Navigation | Keep the thin left icon rail; previous chats in a slide-out history panel |
| Home landing | Open directly into chat; hero "ready" empty-state when no messages |
| Home stats | Removed from home entirely — counts live on their own pages |
| Focus / Insights | Surface in the rail + light dark restyle (keep current layout) |

## Phases

Each phase is independently built, run in a named bundle (`omi-second-brain`), and shown
to the user before the next begins.

### ① Chat-first home  *(build first — highest priority)*

Rework `MainWindow/Pages/DashboardPage.swift` `redesignedHome` / `homeStage`:

- **Empty state (hero):** big greeting "Hey <Name>. I'm ready." + one muted subline
  ("I'm listening — follow-ups appear as conversations end.") + 1–2 suggestion chips
  (e.g. "What does my day look like?"). Reuses existing suggestion data
  (`HomeSuggestionsStore` / `HomeKnowsComposer`), trimmed.
- **Active chat:** once a message is sent, the stage shows the thread via the existing
  `MainWindow/Components/ChatMessagesView.swift`, with the ask bar pinned at the bottom.
- **Remove** `homeStatTextStrip` / `HomeStatTextCell` from the home hero (stat pills gone).
- **Header controls** (`homeHeader`): replace the chunky `HomeStatusButton` ("Capture"),
  `HomeListeningStatusButton` ("Listening"), and settings button with minimal toggles —
  `Listening ●` + `Screen` + gear — in the restrained style of the reference artifact.
- **Palette:** retire the local `enum HomePalette`; drive colors from `SecondBrainTokens`
  (`SBTheme` / `SBInk`) so home matches onboarding.

### ② Ask bar + Connect

- Keep `HomeAskBar` (`DashboardPage.swift`) — the user likes it. Restyle: sparkle icon,
  "Ask omi anything", ⌘K hint, subtle rounded border on dark.
- Connect (`HomeAskBarConnectButton`) stays in the bar, restyled unobtrusive. If it still
  crowds the bar in review, move it to a floating affordance at the rail bottom.

### ③ Previous chats — history panel

- Add a clock/history entry point in the chat header.
- Open a slide-out panel (or restyled `ChatHistoryPopover`) backed by the existing
  `Providers/ChatProvider.swift` (`ChatSession`, `groupedSessions`, select/delete/star/rename)
  and `MainWindow/Components/ChatSessionsSidebar.swift`.
- Contents: **New chat**, search transcripts, Recents grouped by date. Dark-minimal restyle.

### ④ Surface Focus + Insights

- `MainWindow/SidebarView.swift`: add `.focus` and `.insight` to `mainItems` (or a
  secondary rail group) so they render as rail icons and are reachable.
- Light restyle of `MainWindow/Pages/FocusPage.swift` and `MainWindow/Pages/InsightPage.swift`
  to the dark ink system; keep existing layout/data (`FocusViewModel`, `InsightViewModel`).

## Files touched (map)

- `MainWindow/Pages/DashboardPage.swift` — home hero, stage, header, ask bar, remove stat strip, palette.
- `MainWindow/Components/ChatMessagesView.swift`, `ChatBubble.swift` — tool-use chip polish (phase ②/④ polish).
- `MainWindow/SidebarView.swift` — add Focus/Insight to rail.
- `MainWindow/Pages/FocusPage.swift`, `InsightPage.swift` — dark restyle.
- `MainWindow/Pages/ChatPage.swift` / `Components/ChatSessionsSidebar.swift` — history panel entry + restyle.
- `Theme/SecondBrainTokens.swift`, `MainWindow/SecondBrain/SBComponents.swift` — reused; extend only if a token is missing.

No changes to `Providers/ChatProvider.swift` data model, sign-in, onboarding, or backend.

## Verification (per phase)

- Build + launch the `omi-second-brain` named bundle via `run.sh` (dark ink, prod backend).
- **Re-sign fix required after every build** (machine-wide library-validation bug): re-sign
  the installed bundle with `com.apple.security.cs.disable-library-validation` using
  `"Omi Local Dev Signing"` before launch (see `~/.claude/omi-local-build/RUNBOOK.md`).
- Exercise each surface with `agent-swift` (snapshot + screenshot evidence): home hero,
  send a message → thread, open history panel, navigate to Focus + Insights from the rail.
- Compile-gate for cross-file type changes: `xcrun swift build -c debug --package-path Desktop`.

## Risks

- `DashboardPage.swift` is ~4500 lines; edits must stay surgical within `redesignedHome`.
- Removing the stat strip must not break navigation targets that other code relies on.
- Restyling `FocusPage`/`InsightPage` could touch shared components — verify no regression
  on other pages that use them.
