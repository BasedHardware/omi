# Mac→Windows Parity Audit — Onboarding

> Scope: depth comparison of the onboarding flow itself, especially the AI-driven profile-bootstrapping
> intelligence (web research, data-source reading, memory-log import, exports, enrichment synthesis).
> Windows baseline checked: `desktop/windows/src/renderer/src/pages/Onboarding.tsx` (14-step flow) and
> every file in `desktop/windows/src/renderer/src/components/onboarding/`, plus supporting libs
> (`lib/goals.ts`, `lib/appMemories.ts`, `lib/onboardingGraph.ts`, `lib/onboardingGraphModel.ts`,
> `lib/appSelection.ts`, `lib/preferences.ts`).

## Summary table

| Onboarding step/capability | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Name step | `OnboardingWelcomeStepView` | Present-equivalent (`NameStep.tsx`) | — |
| Language step (multi-select, primary) | `OnboardingLanguageStepView` | Partial (`LanguageStep.tsx` — single language, no multi-select) | M |
| How did you hear | `OnboardingHowDidYouHearStepView` | Present-equivalent (`HowDidYouHearStep.tsx`) | — |
| Trust / permissions preview | `OnboardingTrustStepView` | Present-equivalent (`TrustStep.tsx`) | — |
| Screen Recording permission | `OnboardingPermissionStepView` | Present-equivalent, real OS round-trip not yet wired (`ScreenPermissionStep.tsx`) | L |
| Full Disk Access permission (standalone) | `OnboardingPermissionStepView` (step 5) | **Absent as a distinct step** — folded into file scan | L |
| Accessibility permission (active-app awareness) | `OnboardingPermissionStepView` (step 8) | **Absent** — no equivalent step or preference | M |
| Automation permission | `OnboardingPermissionStepView` | Present-equivalent, but local pref flag not an OS grant (`AutomationPermissionStep.tsx`) | — |
| Microphone permission | `OnboardingPermissionStepView` | Present-equivalent (`MicPermissionStep.tsx`) | — |
| Background/privacy consent (always-on listening, launch-at-login) | *(no dedicated Mac step; handled ambiently)* | Windows-only, extra step (`BackgroundPrivacyStep.tsx`) | — |
| File scan / local discovery | `OnboardingFileScanStepView` + `OnboardingPagedIntroCoordinator.refreshSnapshotIfAvailable` | Partial (`BuildProfileStep.tsx` — app names only, no projects/tech/folders) | H |
| Web research (search the user by name/email/org) | `OnboardingWebResearchService` | **Absent** | H |
| Data Sources step (Gmail, Calendar, Apple Notes reading + AI synthesis) | `OnboardingDataSourcesStepView` + `OnboardingPagedIntroCoordinator.startBackgroundInsightsIfNeeded` | **Absent** | H |
| Memory-log import (ChatGPT/Claude paste-in) | `OnboardingMemoryLogImportService` + `OnboardingDataSourcesStepView` | **Absent** | M |
| Enrichment synthesis (LLM merges scan+email+calendar+web into profile summary + KG entities + goal ideas) | `OnboardingPagedIntroCoordinator.analyzeEnrichment` | **Absent** | H |
| Exports step (Notion/Obsidian/ChatGPT/Claude/Gemini/agent MCP setup) | `OnboardingExportsStepView` | **Absent** | M |
| Floating-bar shortcut setup | `OnboardingFloatingBarShortcutStepView` | Present-equivalent (`ShortcutSetupStep.tsx`) | — |
| Floating-bar demo (real AI round trip) | `OnboardingFloatingBarDemoView` | Partial (`AskDemoStep.tsx` — scripted/static image, no real query) | M |
| Voice shortcut test | `OnboardingVoiceShortcutStepView` | Folded into `VoiceIntroStep.tsx` (no separate shortcut-only test) | L |
| Voice demo (waits for real AI response) | `OnboardingVoiceDemoView` | Partial (`VoiceIntroStep.tsx` — waits for capture, not response completion) | M |
| Goal step | `OnboardingGoalStepView` | Present, shallower suggestions (`GoalStep.tsx`) | M |
| AI goal generation | `GoalsAIService` fed by full enrichment context | Partial (`generateGoal` in `lib/goals.ts` — single LLM call, app names only) | M |
| Auto-created Tasks closing screen | `OnboardingTasksStepView` | Present-equivalent (`AutoCreatedTasksStep.tsx`) | — |
| Post-onboarding prompt suggestions | `OnboardingPromptSuggestionBuilder` / `PostOnboardingPromptSuggestions` | **Absent** | L |
| Onboarding-completion side effects (welcome task, `GoalGenerationService.generateNow()`, agent VM pipeline, launch-at-login) | `OnboardingView.handleOnboardingComplete` | Partial (`completeOnboarding()` only stamps a timestamp; launch-at-login handled earlier in `BackgroundPrivacyStep` instead) | L |
| Versioned step-migration for in-flight upgrades | `OnboardingFlow.migratedStep` (11-flag migration ladder) | Partial (`clampOnboardingStep` — clamps to range only, no reordering/insertion logic) | L |
| Knowledge-graph richness during onboarding | Nodes for user, languages, projects, technologies, apps, folders, goals, integrations (Gmail/Calendar/Apple Notes/ChatGPT/Claude), web-research entities (organizations/places/things/concepts) | Nodes for user, one language, apps only (`onboardingGraphModel.ts`: `buildUserNode`, `buildLanguage`, `buildApps`) | H |

## Step-by-step mapping

| Mac step (index) | Windows step (index) | Notes |
|---|---|---|
| Name (0) | Name (0) | 1:1 |
| Language (1) | Language (1) | Mac is multi-select with a primary; Windows is single-choice |
| HowDidYouHear (2) | HowDidYouHear (2) | 1:1 |
| Trust (3) | Trust (3) | 1:1 |
| ScreenRecording (4) | — | folded into ScreenPermission (5) below |
| FullDiskAccess (5) | — | none — no distinct step |
| FileScan (6) | BuildProfile (6) | Windows scan is app-only, no project/tech/folder inference |
| Microphone (7) | MicPermission (7) | 1:1, plus Windows also flips `continuousRecording` here |
| Accessibility (8) | — | none |
| Automation (9) | AutomationPermission (8) | Windows: local pref flag, not an OS grant |
| — | BackgroundPrivacy (4) | Windows-only step, no Mac equivalent (ambient on Mac) |
| FloatingBarShortcut (10) | ShortcutSetup (9) | 1:1 |
| FloatingBar demo (11) | AskDemo (11) | Windows demo is scripted/static, not a live round trip |
| VoiceShortcut (12) | VoiceIntro (10) | Windows merges shortcut-test + voice-demo into one step |
| VoiceDemo (13) | (folded into VoiceIntro) | Windows doesn't wait for a completed AI response |
| DataSources (14) | — | none |
| Exports (15) | — | none |
| Goal (16) | Goal (12) | Windows goal suggestions/generation are far shallower |
| Tasks (17) | AutoCreatedTasks (13) | 1:1, both are static demo cards |

Windows has 14 steps total vs Mac's 18; the numeric mismatch is because Windows never introduces
DataSources/Exports and merges several Mac steps, not because it's simply "shorter" everywhere —
several Windows steps also carry meaningfully less capability behind an equivalent-looking screen.

## Per-step / per-capability detail

### File scan / local discovery
**What it is:** A step that indexes the user's local files and turns that index into onboarding
signal (indexed-file count, inferred projects, tech stack, key folders, recent files, installed apps).

**Where (Mac):** `OnboardingFileScanStepView` (UI) + `OnboardingPagedIntroCoordinator.startFileScanIfNeeded`
/ `refreshSnapshotIfAvailable` (`desktop/macos/Desktop/Sources/Onboarding/OnboardingPagedIntroCoordinator.swift:493-692`).

**How it works:** Calls the `scan_files` tool, then queries the local Rewind SQLite DB
(`indexed_files` table) directly with several SQL queries: project-indicator files
(`package.json`, `Cargo.toml`, `Package.swift`, etc.), installed `.app` bundles, most-recently-modified
files, file-extension histogram mapped to a technology name table (Swift/TypeScript/Python/Rust/Go/…),
and folder-name histogram (Projects/Documents/Downloads/Desktop/Apple Notes store). Builds a
`ScanSnapshot` (fileCount, projectNames, applications, technologies, folders, recentFiles), writes
knowledge-graph nodes for each category (`project_*`, `tech_*`, `app_*`, `folder_*`), and separately
batches "the user works on project X" / "active work in technology Y" facts into durable memories via
`OnboardingImportEvidenceService` (batched `POST` to the import-evidence endpoint, with legacy
memory-batch fallback on 403/404, retry/backoff on 429/5xx).

**Windows status:** Partial. `BuildProfileStep.tsx` calls `window.omi.indexFilesScan()` for a raw file
count and separately `window.omi.indexFilesApps(200)` for installed apps, which become graph app nodes
via `addAppNodes`/`buildApps` (`onboardingGraphModel.ts`). There is no project inference, no technology
inference, no folder histogram, no recent-files list, and no memory-batch write from the scan — the
scan's only durable output is app nodes in the local graph. `lib/appMemories.ts` explicitly documents
that "app→memory synthesis was removed to match the macOS app" (a stated but inaccurate rationale —
Mac's real behavior graphs *and* memory-imports project/tech signal, it just never memory-imports
individual app names).

**Value / notes:** High. This is the seed data for the goal step, the profile summary, and the graph —
Windows onboarding users get a visibly emptier "2nd brain" graph than Mac users after the same step.

### Web research (OnboardingWebResearchService)
**What it is:** Background best-effort web search for the signed-in user, run during onboarding to
enrich their profile with information found publicly (their name + inferred workplace/org, cross-referenced
with project names/technologies from the file scan).

**Where (Mac):** `desktop/macos/Desktop/Sources/Onboarding/OnboardingWebResearchService.swift`, invoked from
`OnboardingPagedIntroCoordinator.maybeStartWebResearch` / `buildWebQueries`.

**How it works:** Builds up to 4 queries (`"<name> <org>"`, `"<name> <project>"`, etc. — org is inferred
from the email domain, skipping public providers like gmail.com/icloud.com), scrapes DuckDuckGo HTML
search (`https://html.duckduckgo.com/html/?q=…`) with a spoofed desktop Chrome UA, regex-parses result
titles/snippets/URLs (including unwrapping DDG's redirect wrapper), dedupes by URL. Only runs after
Gmail + Calendar + Apple Notes reads have all finished. Results feed `analyzeEnrichment`, which sends
scan + email + calendar + Apple Notes + web results to an LLM (`AgentClient.run`) asking for strict JSON:
a 1–2 sentence profile summary, up to 12 graph entities (with `node_type` and a relation like
`works_with`/`researches`/`follows`), and up to 6 goal suggestions — which then populate the knowledge
graph and the goal step's suggestion chips.

**Windows status:** Absent. No file, no equivalent network call, no entity extraction from web results.

**Value / notes:** High — this is the single largest "the app already seems to know me" moment on Mac
onboarding and has no Windows counterpart at all.

### Data Sources step (Gmail, Calendar, Apple Notes reading)
**What it is:** A dedicated onboarding screen that reads the user's Gmail, Google Calendar, and Apple
Notes in parallel with the file scan, shows live per-source scan progress/counts, and turns each into
durable memories + a synthesized profile summary + graph nodes.

**Where (Mac):** `OnboardingDataSourcesStepView.swift` (UI) +
`OnboardingPagedIntroCoordinator.startBackgroundInsightsIfNeeded` (background orchestration,
`OnboardingPagedIntroCoordinator.swift:694-901`).

**How it works:** Three parallel `Task`s: `GmailReaderService.readRecentEmails(maxResults: 300, query:
"newer_than:365d")`, `CalendarReaderService.readEvents(daysBack: 365, daysForward: 90, maxResults: 1000)`,
`AppleNotesReaderService.readRecentNotes(maxResults: 250)`. Each source is (a) batch-saved as raw import
evidence (`saveAsMemories`) and (b) LLM-synthesized into a profile-summary sentence
(`synthesizeFromEmails`/`synthesizeFromEvents`/`synthesizeFromNotes`), each producing its own KG
integration node (`integration_gmail`, `integration_calendar`, `integration_apple_notes`) plus a
`checks`/`plans_with`/`captures_in` edge from `user`. The UI shows live source/memory counts and a
per-row status (scanning / error / done) with toggles; Apple Notes additionally requires the user to pick
a folder via an `NSOpenPanel` (Apple Notes' group-container path isn't sandboxed-readable by default).
Finishing all three unblocks the web-research stage (`maybeStartWebResearch`).

**Windows status:** Absent entirely — no step, no Gmail/Calendar/Apple Notes reader services, no
per-source UI, no synthesis calls. (There's no Windows equivalent of Apple Notes anyway, but Gmail and
Google Calendar are platform-agnostic integrations Mac already has elsewhere in the app — this step is
the only place they're wired into onboarding on either platform.)

**Value / notes:** High — this is the second-largest "instant personalization" surface on Mac and is
completely missing on Windows; a Windows user's onboarding graph never grows from anything but their
name, one language, and installed apps.

### Memory-log import (ChatGPT / Claude paste-in)
**What it is:** Lets the user paste an exported ChatGPT or Claude memory log (via a pre-filled prompt
that opens the chat app in the default browser) so Omi can extract durable facts from it.

**Where (Mac):** `OnboardingMemoryLogImportService.swift`, wired into `OnboardingDataSourcesStepView`
(`compactMemoryLogRow`/`memoryLogPanel`) via `OnboardingPagedIntroCoordinator.importMemoryLog`.

**How it works:** Copies a canned prompt to the clipboard and opens `chatgpt.com`/`claude.ai` with it
pre-filled as a query param; the user pastes the response back into a `TextEditor`. An LLM call
(`AgentClient.run`, `ModelQoS.Claude.synthesis`) extracts 12–18 durable memory strings + a 2–3 sentence
profile summary as JSON, which are saved via the same `OnboardingImportEvidenceService` batch path used
by the file scan and graphed as an `integration_chatgpt`/`integration_claude` node.

**Windows status:** Absent — no UI, no service, no prompt.

**Value / notes:** Medium — a manual/opt-in feature (most users won't use it), but zero Windows
equivalent, and it's part of the same `DataSources` screen that's entirely missing.

### Exports step (Notion / Obsidian / ChatGPT / Claude / Gemini / agent MCP setup)
**What it is:** A step after the graph is live that lets the user push their new memory context *out* to
tools they already use — Notion (copy-ready page), Obsidian (auto-refreshing vault file), ChatGPT/Claude/
Gemini (prompt + memory pack, opens the site), a generic "Agents" MCP setup-prompt copy, or pointers to
connect Claude Code/Codex/OpenClaw/Hermes via MCP later from Apps.

**Where (Mac):** `OnboardingExportsStepView.swift`, backed by `MemoryExportService` /
`MemoryExportDestination` / `MemoryExportDestinationSheetModel`.

**How it works:** Renders one row per `MemoryExportDestination` where `supportsMemoryPack ||
supportsAgentSetup`, each with a live status (`exportedCount`, `isConfigured`) and an inline
connect/export panel per destination type (Notion copy+open, Obsidian vault picker, chat-site copy+open,
agent-prompt copy).

**Windows status:** Absent — no step, no `MemoryExportService`/destination model of any kind found in
the Windows renderer.

**Value / notes:** Medium — this is a distribution/retention feature (make Omi useful in tools the user
already lives in) rather than a data-collection one, but it's a full step with zero Windows footprint.

### Enrichment synthesis / goal intelligence
**What it is:** The LLM call that turns everything gathered so far (file scan + Gmail + Calendar + Apple
Notes + web research) into a single coherent profile summary, a compact list of extra knowledge-graph
entities, and concrete goal suggestions — this is the "brain" behind the `connectedContextSummary` shown
throughout later steps and the goal step's suggestion chips.

**Where (Mac):** `OnboardingPagedIntroCoordinator.analyzeEnrichment` (`OnboardingPagedIntroCoordinator.swift:981-1092`)
and `buildSuggestedGoals`.

**How it works:** A single structured-JSON LLM call fed the full multi-source context (scan lines, email
summary, calendar summary, Apple Notes summary, top 6 web results) with explicit rules ("use only facts
grounded in the provided context", entity `node_type` enum, goals must be "concrete and specific, not
generic"). `buildSuggestedGoals` also has a lighter, deterministic heuristic path (context-aware chip
text like "Stay ahead of important follow-ups" when email data exists) used before the LLM result lands.

**Windows status:** Partial/shallow equivalent only in `lib/goals.ts`. `generateGoal(apps)` builds one
prompt from just the app-name list ("I work with these apps and tools: X, Y. Suggest ONE specific
personal-productivity goal…") and calls `callAgentLLM` for a single sentence — no email, calendar, web,
or notes context (because none of those are collected), no entity extraction, no profile summary, no
multi-goal suggestion list (the two starter cards in `GoalStep.tsx` are hardcoded strings, not generated).

**Value / notes:** High — this is the connective tissue that makes Mac's later onboarding steps feel
personalized; Windows's goal step is functional but generic by comparison.

### Language step: multi-select vs single-select
**What it is:** Picking the language(s) Omi should recognize during transcription/voice interaction.

**Where (Mac):** `OnboardingLanguageStepView.swift` + `OnboardingPagedIntroCoordinator.confirmLanguages`.

**How it works:** Multi-select chip grid (10 common languages Deepgram's multi-language mode covers,
plus a free-text "Other…" field normalized via `AssistantSettings.normalizeTranscriptionLanguageCode`).
Selection order matters — first pick is primary, saved as the account's `language` (LLM output language)
via `APIClient.updateUserLanguage` with one automatic retry on transient failure; the full ordered list is
saved locally to drive per-turn language identification in the voice assistant, deliberately *not*
touching ambient always-on transcription settings.

**Windows status:** Partial. `LanguageStep.tsx` is a binary English/Other choice with a single free-text
field (`resolveLanguageCode`) — no multi-select, no primary/secondary distinction, no chip grid of common
languages.

**Value / notes:** Medium — multilingual users on Windows can only declare one language, and there's no
UI hint at all that the voice assistant might understand more than one.

### Floating-bar demo: scripted vs live round trip
**What it is:** The step that has the user actually trigger the floating "Ask Omi" bar and see a real AI
answer, to prove the feature works before onboarding ends.

**Where (Mac):** `OnboardingFloatingBarDemoView.swift`.

**How it works:** Sets up the real `FloatingControlBarManager`/`GlobalShortcutManager`, waits (polling
every 0.25s) for the user to actually press the shortcut and open the bar, then polls up to 60s for a
real, non-streaming AI response in `barState.currentAIMessage(from:)` before revealing Continue.

**Windows status:** Partial. `AskDemoStep.tsx` enables the overlay (`window.omiOverlay?.setEnabled(true)`)
but never waits for a keypress or a real response — it shows a static `macs.png` "Mac comparison" image
on a timed fade-in and Continue is available immediately regardless of whether the user touched the bar.
The prompt text ("Which computer should I buy?") and payoff image are hardcoded, not a live query result.

**Value / notes:** Medium — functionally this can't fail (good for onboarding funnel completion), but it
never actually proves the floating bar or the backend works, unlike the Mac version.

### Voice demo: capture vs response confirmation
**What it is:** Verifying push-to-talk voice input actually reaches the AI and gets a spoken/text answer.

**Where (Mac):** `OnboardingVoiceShortcutStepView.swift` (shortcut-only test) is a separate step from
`OnboardingVoiceDemoView.swift` (full ask-and-wait-for-response demo, with volume-mute/zero-volume
detection via `SystemAudioMuteController` and a nudge to turn the volume up before proceeding).

**How it works:** `OnboardingVoiceDemoView` polls up to 20s for a completed, non-streaming AI message in
the floating bar before unlocking Continue, and separately detects and warns about muted/zero system
output before the user even tries.

**Windows status:** Partial, merged into one step. `VoiceIntroStep.tsx` listens for
`window.omiOverlay?.onVoiceCaptured()` and unlocks Continue as soon as a PTT *capture* completes — it does
not wait for or confirm an actual AI response, and there's no separate shortcut-only pre-test step, and no
output-volume/mute detection.

**Value / notes:** Medium — a silent failure in the voice pipeline (e.g. backend down, STT failing) would
still let a Windows user sail through this step showing "success," where Mac would keep them on the step
past the 20s timeout.

### Accessibility / active-app-awareness permission
**What it is:** A permission step explaining Omi needs to know which app is currently focused (used for
context-aware suggestions/automation targeting).

**Where (Mac):** `OnboardingPermissionStepView` instantiated with `permissionType: "accessibility"`
(`OnboardingView.swift` step 8, `eyebrow: "Permission"`, `title: "Let Omi see the active app."`).

**Windows status:** Absent — no onboarding step, and no corresponding Windows preference/permission
surfaced anywhere in `components/onboarding/`.

**Value / notes:** Medium — this may reflect a genuine platform difference (Windows automation/UI Automation
permission model differs from macOS Accessibility), but there's no equivalent messaging or consent step at
all, so a capability Mac explicitly asks consent for is silently assumed/unexplained on Windows.

### Post-onboarding prompt suggestions
**What it is:** After onboarding completes, a small set of contextual first-chat prompt suggestions
(informed by what was learned: email follow-ups, calendar focus time, the goal just set) are saved and
shown to the user as a popup on first landing in the app.

**Where (Mac):** `OnboardingPromptSuggestionBuilder.build` + `PostOnboardingPromptSuggestions`
(`OnboardingPromptSuggestions.swift`), invoked in `OnboardingView.handleOnboardingComplete`.

**Windows status:** Absent — no equivalent file or call found.

**Value / notes:** Low — a nice-to-have nudge into first use, but downstream of all the missing intelligence
above (it has nothing personalized to build from on Windows anyway).

## Spotted outside my scope
- `OnboardingChatView.swift` (a full ~2,168-line AI-chat-driven onboarding flow with quick-reply buttons,
  Gemini-vision-based "permission help" screenshots, parallel exploration/Gmail/Calendar reading cards, and
  its own goal/task-creation heuristics) exists in the Mac codebase and is fully built, but a repo-wide grep
  confirms it is **not instantiated anywhere in the current `OnboardingView.swift` paged flow** — it appears
  to be superseded/legacy code, referenced only by `ChatToolExecutor.swift`, `FloatingControlBarWindow.swift`,
  and an e2e flow fixture. Not counted above since it isn't live Mac behavior today, but it's a large amount
  of "AI onboarding intelligence" (permission-help vision calls, parallel background reads) that used to be
  the primary flow and may be worth the orchestrator's attention as dead code / migration debt on the Mac
  side, independent of Windows parity.
- `OnboardingNotificationStepView.swift` is similarly present in the Mac source tree but not wired into
  `OnboardingFlow.steps` (the flow's own migration comments confirm the notification step was deliberately
  removed). Not counted as a gap.
- Windows-only `BackgroundPrivacyStep` (always-on listening + launch-at-login consent) has no Mac onboarding
  equivalent — Mac handles this ambiently (permissions granted piecemeal, launch-at-login force-enabled at
  completion) rather than as an explicit consent screen. Flagged for the orchestrator in case this is worth
  recommending back to Mac rather than only closing gaps in the Windows→Mac direction.
