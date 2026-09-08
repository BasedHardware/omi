# Mac→Windows Parity Audit — Onboarding

> **Re-audited 2026-08-22.** This replaces the 2026-08-20 version in place. Every claim below was
> re-verified against current source (file reads + `git log` on the cited files) rather than carried
> over from the previous pass — see "Changed since the 2026-08-20 audit" below for what that turned up.

> Scope: depth comparison of the onboarding flow itself, especially the AI-driven profile-bootstrapping
> intelligence (web research, data-source reading, memory-log import, exports, enrichment synthesis).
> Windows baseline checked: `desktop/windows/src/renderer/src/pages/Onboarding.tsx` (14-step flow) and
> every file in `desktop/windows/src/renderer/src/components/onboarding/`, plus supporting libs
> (`lib/goals.ts`, `lib/appMemories.ts`, `lib/appSelection.ts`, `lib/onboardingGraph.ts`,
> `lib/onboardingGraphModel.ts`, `lib/onboardingProgress.ts`, `lib/calendarConnect.ts`,
> `lib/googleSync.ts`, `lib/googleFeatureFlag.ts`, `lib/pasteImport.ts`, `lib/memoryExtract.ts`,
> `lib/onboardingImportCounts.ts`, `hooks/useGoogleConnection.ts`, `lib/preferences.ts`,
> `lib/backgroundConsent.ts`).

## Changed since the 2026-08-20 audit

The previous pass materially mis-described the Windows side in two places — both because the audited
code had already shipped *and moved on again* weeks before the audit was written, not because anything
changed afterward (`git log --since=2026-08-20` on every file below returns nothing; all of this
predates the audit):

1. **"Data Sources step: Absent" was wrong on 2026-08-20 — it had existed for over a month.**
   `components/onboarding/DataSourcesStep.tsx` landed 2026-07-15 (`7eb002b750`, "feat(windows/onboarding):
   add Mac-parity Data Sources step") and is wired into `Onboarding.tsx` at step index 12. It offers
   Calendar (Google Calendar OAuth), Email (Gmail OAuth), a read-only status row for the local file index,
   and ChatGPT/Claude memory-log paste-in — four of the old table's "Absent" rows in one step. It is
   real but genuinely partial (see detail section below), so this is a status change from **Absent →
   Partial**, not Absent → Present.
2. **"Memory-log import: Absent" was also wrong for the same reason.** The ChatGPT/Claude paste-in flow
   living inside `DataSourcesStep.tsx` (`MemoryLogRow`, backed by `lib/pasteImport.ts` +
   `lib/memoryExtract.ts`) is, per its own header comment, "the Windows port of macOS
   `OnboardingMemoryLogImportService`." This is now **Present**, with one real gap (the backend-returned
   profile-summary sentence is computed but discarded — see detail section).
3. **"Auto-created Tasks closing screen: Present-equivalent" is now the opposite — it flipped to Absent
   *before* the audit was written and the old audit missed it.** Commit `93dbeec0d4`
   ("fix(windows): simplify post-onboarding controls", 2026-07-23) made Goal the terminal step and routes
   straight to Chat on completion; `TOTAL_STEPS` dropped from 15 to 14 in the same commit.
   `AutoCreatedTasksStep.tsx` still exists on disk with a passing unit test, but `Onboarding.tsx` no
   longer imports or renders it — it is dead code, the same class of finding the *old* audit itself
   flagged on the Mac side for `OnboardingChatView.swift`. This inverts the row: it's a **new Windows
   gap** (Mac still ends on a Tasks preview; Windows now ends one step earlier, on Goal), not parity.
4. **The step-by-step mapping table was stale in its Windows column from step 9 onward** as a direct
   consequence of (1)-(3) — it lists Goal at Windows index 12 and AutoCreatedTasks at 13, and omits
   DataSources from the Windows side entirely. Both index assignments were already wrong when written.
   Rebuilt below from the current `renderStep()` switch.
5. **Everything else re-verified unchanged.** Web research, enrichment synthesis, the Exports step,
   post-onboarding prompt suggestions, Accessibility/Full Disk Access permission steps, language
   multi-select, file-scan project/tech/folder inference, AI goal generation depth, knowledge-graph
   richness, and the versioned step-migration logic all check out exactly as the old audit described —
   confirmed by reading current source, not assumed from the prior pass.
6. **Several of the old audit's own line-number citations were wrong, on both sides, independent of
   any drift over time.** Re-derived from source rather than trusted: the Windows-side `MemoryLogRow`
   citation pointed at `DataSourcesStep.tsx:264-341` (actually `325-439` — the old range mostly covered
   the *previous* row, `LocalFilesRow`); `extractPasteMemories` and `extractMemories` were cited 7 and 3
   lines early respectively; and on the Mac side, `startBackgroundInsightsIfNeeded` was cited at
   `OnboardingPagedIntroCoordinator.swift:694-901` when the function actually starts at `939`, and
   `analyzeEnrichment` was cited at `981-1092` when it actually starts at `1269` — both off by 200+
   lines, confirmed via a plain `grep -n` for the function signatures. These were citation-accuracy bugs
   in the old audit text itself, not code that moved; all are corrected in the detail sections below.

Net: **3 summary-table rows change status** (Data Sources, Memory-log import, Auto-created Tasks), the
step-by-step mapping table needed a structural rewrite, and 5 stale line-number citations (2 Windows, 3
Mac) were corrected in place. The single most significant correction is #1/#2 together: the previous
audit's single biggest claimed gap — "no Windows equivalent of Mac's Gmail/Calendar/memory-log
onboarding intelligence at all" — was overstated by an entire shipped step that had been live for five
weeks.

## Summary table

| Onboarding step/capability | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Name step | `OnboardingWelcomeStepView` | Present-equivalent (`NameStep.tsx`) | — |
| Language step (multi-select, primary) | `OnboardingLanguageStepView` | Partial (`LanguageStep.tsx` — single language, no multi-select) | M |
| How did you hear | `OnboardingHowDidYouHearStepView` | Present-equivalent (`HowDidYouHearStep.tsx`) | — |
| Trust / permissions preview | `OnboardingTrustStepView` | Present-equivalent (`TrustStep.tsx`) | — |
| Background/privacy consent (always-on listening, launch-at-login) | *(no dedicated Mac step; handled ambiently)* | Windows-only, extra step (`BackgroundPrivacyStep.tsx`) | — |
| Screen Recording permission | `OnboardingPermissionStepView` | Present-equivalent — Windows has no OS consent prompt to round-trip (there is none on this platform), and now correctly reads/writes real Rewind capture state instead of a fake toggle (`ScreenPermissionStep.tsx`, fixed pre-audit in `85c6ea0474`) | L |
| Full Disk Access permission (standalone) | `OnboardingPermissionStepView` (step 5) | **Absent as a distinct step** — folded into the automatic file scan, confirmed still true (no standalone consent UI anywhere in `components/onboarding/`) | L |
| Accessibility permission (active-app awareness) | `OnboardingPermissionStepView` (step 8) | **Absent** — no equivalent step or preference, confirmed still true | M |
| Automation permission | `OnboardingPermissionStepView` | Present-equivalent, but local pref flag (`automationConsentedAt`) not an OS grant (`AutomationPermissionStep.tsx`) | — |
| Microphone permission | `OnboardingPermissionStepView` | Present-equivalent (`MicPermissionStep.tsx`) | — |
| File scan / local discovery | `OnboardingFileScanStepView` + `OnboardingPagedIntroCoordinator.refreshSnapshotIfAvailable` | Partial, confirmed unchanged (`BuildProfileStep.tsx` — app names only via `indexFilesApps`/`rankApps`, no projects/tech/folders) | H |
| Web research (search the user by name/email/org) | `OnboardingWebResearchService` | **Absent**, confirmed unchanged (no DuckDuckGo/search call anywhere in the Windows renderer or main process) | H |
| Data Sources step (Gmail, Calendar, [Apple Notes — N/A on Windows] reading) | `OnboardingDataSourcesStepView` + `OnboardingPagedIntroCoordinator.startBackgroundInsightsIfNeeded` | **Was "Absent," is actually Partial** — `DataSourcesStep.tsx` connects Calendar + Gmail (OAuth) and surfaces the file-index count; missing live per-source scan progress, per-source profile-summary synthesis, and KG integration nodes | H |
| Memory-log import (ChatGPT/Claude paste-in) | `OnboardingMemoryLogImportService` + `OnboardingDataSourcesStepView` | **Was "Absent," is actually Present** — same step's `MemoryLogRow`, explicitly a port of the Mac service; gap is the discarded profile-summary field, not the import itself | L (was M) |
| Enrichment synthesis (LLM merges scan+email+calendar+web into profile summary + KG entities + goal ideas) | `OnboardingPagedIntroCoordinator.analyzeEnrichment` | **Absent**, confirmed unchanged — per-source LLM extraction exists (Gmail sync, memory-log paste), but no call that merges everything into one profile summary + KG entity list + goal suggestions | H |
| Exports step (Notion/Obsidian/ChatGPT/Claude/Gemini/agent MCP setup) | `OnboardingExportsStepView` | **Absent from onboarding**, confirmed unchanged — the underlying export capability exists elsewhere in the app (`lib/memoryExport.ts`, used by Settings → Advanced and Hub → Connections), it's just never surfaced as an onboarding step | M |
| Floating-bar shortcut setup | `OnboardingFloatingBarShortcutStepView` | Present-equivalent (`ShortcutSetupStep.tsx`) | — |
| Floating-bar demo (real AI round trip) | `OnboardingFloatingBarDemoView` | Partial, confirmed unchanged (`AskDemoStep.tsx` — scripted/static image, Continue available immediately regardless of interaction) | M |
| Voice shortcut test | `OnboardingVoiceShortcutStepView` | Folded into `VoiceIntroStep.tsx`, confirmed unchanged (no separate shortcut-only test) | L |
| Voice demo (waits for real AI response) | `OnboardingVoiceDemoView` | Partial, confirmed unchanged (`VoiceIntroStep.tsx` unlocks Continue on a completed *capture*, not a completed AI response) | M |
| Goal step | `OnboardingGoalStepView` | Present, shallower suggestions, confirmed unchanged (`GoalStep.tsx`) — now the terminal onboarding step (see Auto-created Tasks row) | M |
| AI goal generation | `GoalsAIService` fed by full enrichment context | Partial, confirmed unchanged (`generateGoal` in `lib/goals.ts` — single LLM call, app names only, no email/calendar/web context even though Data Sources now collects some of it) | M |
| Auto-created Tasks closing screen | `OnboardingTasksStepView` | **Was "Present-equivalent," is now Absent from the live flow** — `AutoCreatedTasksStep.tsx` still exists and unit-tests green, but has not been reachable from `Onboarding.tsx` since `93dbeec0d4` (2026-07-23); Goal is now terminal | L (new gap) |
| Post-onboarding prompt suggestions | `OnboardingPromptSuggestionBuilder` / `PostOnboardingPromptSuggestions` | **Absent**, confirmed unchanged | L |
| Onboarding-completion side effects (welcome task, `GoalGenerationService.generateNow()`, agent VM pipeline, launch-at-login) | `OnboardingView.handleOnboardingComplete` | Partial, confirmed unchanged (`completeOnboarding()` only stamps a timestamp and clears the saved step; launch-at-login is handled earlier, in `BackgroundPrivacyStep`/`persistBackgroundConsent`) | L |
| Versioned step-migration for in-flight upgrades | `OnboardingFlow.migratedStep` (11-flag migration ladder) | Partial, confirmed unchanged (`clampOnboardingStep` — clamps a saved index into `[0, totalSteps-1]` only, no reordering/insertion logic; note `totalSteps` itself has moved twice in the last two months — 15→14 — with no migration logic to re-home a user paused mid-flow across that shift) | L |
| Knowledge-graph richness during onboarding | Nodes for user, languages, projects, technologies, apps, folders, goals, integrations (Gmail/Calendar/Apple Notes/ChatGPT/Claude), web-research entities | Partial, confirmed unchanged **even with Data Sources now live** — connecting Calendar/Gmail or importing a memory log in `DataSourcesStep` never touches the onboarding graph; `onboardingGraph.ts` only ever calls `buildUserNode`/`buildLanguage`/`buildApps` (`onboardingGraphModel.ts`) | H |

## Step-by-step mapping

Rebuilt from the current `renderStep()` switch in `Onboarding.tsx` (`TOTAL_STEPS = 14`, indices 0–13).
The old table's Windows-index column was wrong from step 9 onward — it predates the Data Sources step
landing and postdates nothing (it was simply never updated after `7eb002b750`/`93dbeec0d4`).

| Mac step (index) | Windows step (index) | Notes |
|---|---|---|
| Name (0) | Name (0) | 1:1 |
| Language (1) | Language (1) | Mac is multi-select with a primary; Windows is single-choice |
| HowDidYouHear (2) | HowDidYouHear (2) | 1:1 |
| Trust (3) | Trust (3) | 1:1 |
| — | BackgroundPrivacy (4) | Windows-only step, no Mac equivalent (ambient on Mac) |
| ScreenRecording (4) | ScreenPermission (5) | Windows has no OS prompt to round-trip; reads/writes real local capture state |
| FullDiskAccess (5) | — | none — no distinct step |
| FileScan (6) | BuildProfile (6) | Windows scan is app-only, no project/tech/folder inference |
| Microphone (7) | MicPermission (7) | 1:1, plus Windows also flips `continuousRecording` here |
| Accessibility (8) | — | none |
| Automation (9) | AutomationPermission (8) | Windows: local pref flag, not an OS grant |
| FloatingBarShortcut (10) | ShortcutSetup (9) | 1:1 |
| VoiceShortcut (12) | VoiceIntro (10) | Windows merges shortcut-test + voice-demo into one step |
| VoiceDemo (13) | (folded into VoiceIntro) | Windows doesn't wait for a completed AI response |
| FloatingBar demo (11) | AskDemo (11) | Windows demo is scripted/static, not a live round trip |
| DataSources (14) | **DataSources (12)** | **Corrected**: exists on Windows now, at index 12 — Calendar/Gmail OAuth + file-index status + memory-log paste-in, no live per-source progress or synthesis |
| Exports (15) | — | none |
| Goal (16) | **Goal (13, terminal)** | **Corrected**: Windows goal suggestions/generation are far shallower, and Goal is now the LAST step — completing or skipping it routes straight to Chat |
| Tasks (17) | **— (removed 2026-07-23)** | **Corrected**: `AutoCreatedTasksStep.tsx` is unreachable dead code; Windows no longer has a step here at all |

Windows has 14 steps total vs Mac's 18 — the same count as the old audit reported, but for a different
reason: the old table arrived at 14 by (wrongly) including a live Tasks step and omitting Data Sources;
the actual 14 today includes Data Sources and excludes Tasks. The undercount vs Mac is still explained by
Windows never introducing Exports and merging several Mac steps (shortcut-test+voice-demo,
FullDiskAccess+FileScan), not by simply being "shorter" everywhere.

## Per-step / per-capability detail

### File scan / local discovery
**What it is:** A step that indexes the user's local files and turns that index into onboarding
signal (indexed-file count, inferred projects, tech stack, key folders, recent files, installed apps).

**Where (Mac):** `OnboardingFileScanStepView` (UI) + `OnboardingPagedIntroCoordinator.startFileScanIfNeeded`
(`desktop/macos/Desktop/Sources/Onboarding/OnboardingPagedIntroCoordinator.swift:633-655`) /
`refreshSnapshotIfAvailable` (same file, `658-855`; file confirmed present, 1930 lines total — the old
audit's cited range for this pair, `493-692`, was itself off by ~140 lines, caught while re-verifying).

**How it works:** Calls the `scan_files` tool, then queries the local Rewind SQLite DB
(`indexed_files` table) directly with several SQL queries: project-indicator files, installed `.app`
bundles, most-recently-modified files, a file-extension histogram mapped to a technology name table, and
a folder-name histogram. Builds a `ScanSnapshot`, writes knowledge-graph nodes for each category, and
separately batches "the user works on project X" / "active work in technology Y" facts into durable
memories via `OnboardingImportEvidenceService`.

**Windows status:** Partial, re-confirmed by reading the current file. `BuildProfileStep.tsx`
(`desktop/windows/src/renderer/src/components/onboarding/BuildProfileStep.tsx:77-96`) calls
`window.omi.indexFilesScan()` for a raw file count and `window.omi.indexFilesApps(200)` for installed
apps, which become graph app nodes via `rankApps` (`lib/appSelection.ts`) → `addAppNodes` →
`buildApps` (`lib/onboardingGraphModel.ts:29-45`). There is still no project inference, no technology
inference, no folder histogram, no recent-files list, and no memory-batch write from the scan — the
scan's only durable output is app nodes in the local graph. `lib/appMemories.ts:5-9` still carries the
comment that "app→memory synthesis was removed to match the macOS app" — the same stated-but-slightly-
misleading rationale the last audit flagged (Mac's real behavior graphs *and* memory-imports project/tech
signal; it just never memory-imports individual app names the way the old Windows pipeline did).

**Value / notes:** High, unchanged. This is still the seed data for the goal step and the graph — but see
the Data Sources correction below, which does close part of the "emptier 2nd brain" gap the old audit
described, just not through the file-scan step itself.

### Data Sources step — corrected from "Absent" to "Partial"
**What it is:** A dedicated onboarding screen that lets the user connect more context sources before
finishing, so the app has more than a name/language/app-list to work with.

**Where (Mac):** `OnboardingDataSourcesStepView.swift` (UI) +
`OnboardingPagedIntroCoordinator.startBackgroundInsightsIfNeeded` (background orchestration,
`OnboardingPagedIntroCoordinator.swift:939-1196` — the old audit's `694-901` was off by ~245 lines,
caught while re-verifying) — three parallel auto-running readers (Gmail, Calendar,
Apple Notes), each batch-saved as raw memories AND LLM-synthesized into one profile-summary sentence per
source, each producing its own KG integration node (`integration_gmail`, `integration_calendar`,
`integration_apple_notes`), with live per-source scan progress in the UI. Apple Notes requires an
`NSOpenPanel` folder pick.

**Windows status — this is the corrected finding.** `DataSourcesStep.tsx`
(`desktop/windows/src/renderer/src/components/onboarding/DataSourcesStep.tsx`, 439 lines) landed
2026-07-15 (`7eb002b750`) and sits at step index 12 in the live flow. It is a fixed-order list, not the
general connectors marketplace:
- **Calendar** (`CalendarRow`) — backend-mediated Google Calendar OAuth (`lib/calendarConnect.ts`): gets
  an auth URL, opens it in the system browser, polls `/v1/integrations/google_calendar` for
  `{connected:true}`. Needs no client-side Google credentials, so it works in every build.
- **Email** (`EmailRow`) — client-side Gmail loopback OAuth via `useGoogleConnection()`. **Gated behind
  `GOOGLE_ENABLED`** (`lib/googleFeatureFlag.ts:9-11`), which is `import.meta.env.VITE_ENABLE_GOOGLE_INTEGRATION
  === '1'` — unset in a normal packaged build. In that default case the row renders "Requires setup" and
  is inert; the Mac-parity behavior only exists when that build flag is set. When it IS connected, the
  hook's module-scope singleton fires an immediate sync (`runAutoSync` → `runGoogleSync` in
  `lib/googleSync.ts:12-30`) that calls `extractGmailMemories` (an LLM extraction step, not just an OAuth
  handshake) and writes tagged memories (`gmail/import/note`) — genuinely close in spirit to Mac's
  per-source read-and-synthesize, just gated and app-wide rather than onboarding-specific.
- **Local files** (`LocalFilesRow`) — read-only status readout of the count from the earlier
  `BuildProfileStep` scan (`window.omi.indexFilesStatus()`); it does not re-scan and adds nothing new.
- **Memory-log paste-in** (`MemoryLogRow`, ×2 for ChatGPT/Claude) — see the dedicated section below.
- **No Apple Notes row** — a genuine platform gap (no Windows equivalent app exists), not a bug.

What's still missing relative to Mac, confirmed by reading the file: no live "scanning… N emails found"
progress UI (Windows shows a static Connect/Connected pill, no counts, no per-row scanning state); no
per-source LLM synthesis into a single profile-summary sentence that surfaces anywhere in the UI; and,
confirmed via `lib/onboardingGraph.ts`, connecting anything on this screen never writes a KG node —
`integration_gmail`/`integration_calendar` equivalents do not exist on Windows at all.

**Value / notes:** High, but the shape of the gap changed. The old audit's framing — "a Windows user's
onboarding graph never grows from anything but their name, one language, and installed apps" — is still
literally true of the *graph*, but no longer true of the user's *memories*: Gmail (when enabled) and
pasted memory logs both feed real, LLM-extracted memories today. The remaining gap is specifically the
graph/profile-summary layer, not "nothing happens at all."

### Memory-log import (ChatGPT / Claude paste-in) — corrected from "Absent" to "Present"
**What it is:** Lets the user paste an exported ChatGPT or Claude memory log so Omi can extract durable
facts from it.

**Where (Mac):** `OnboardingMemoryLogImportService.swift` (141 lines, confirmed present), wired into
`OnboardingDataSourcesStepView` via `OnboardingPagedIntroCoordinator.importMemoryLog`.

**Windows status — corrected.** `MemoryLogRow` inside `DataSourcesStep.tsx`
(`desktop/windows/src/renderer/src/components/onboarding/DataSourcesStep.tsx:325-439`) copies the same
canned prompt to the clipboard AND opens the prefilled `chatgpt.com`/`claude.ai` URL (`?q=`), lets the
user paste the response into a `textarea`, and calls `extractPasteMemories` (`lib/pasteImport.ts:40-66`),
which tries an AI extraction path first (`extractMemories` in `lib/memoryExtract.ts:31-67`, POSTing to
backend `/v1/memories/extract`) and falls back to a local heuristic line-split
(`window.omi.memoryImportParse`, capped at `MAX_HEURISTIC_IMPORT_ITEMS = 500`) if the AI call fails —
a fallback path the source comments attribute to *this* file, not confirmed either way on the Mac side.
Results are written via the shared batched-import path (`memoriesBulk.ts`) and the per-account imported
count is cached (`lib/onboardingImportCounts.ts`) with an explicit cross-account guard.

**The one real gap:** the backend's `/v1/memories/extract` response includes a `profile` field
(`memoryExtract.ts:8`, `ExtractedMemories = { memories: string[]; profile: string }`) — a synthesized
summary sentence, exactly analogous to what Mac's service produces — but `DataSourcesStep.tsx` never
reads `r.profile` from the result; it is computed by the backend and discarded on the client. There is
also no `integration_chatgpt`/`integration_claude` graph node written (same finding as the Data Sources
section above).

**Value / notes:** Low now, was Medium. The core "let a user hand over a memory-log dump and get durable
facts out of it" capability is present and functioning; what's left missing (a shown profile summary, a
graph node) is cosmetic relative to the actual memory extraction, which is done.

### Enrichment synthesis / goal intelligence
**What it is:** The LLM call that turns everything gathered so far into a single coherent profile
summary, a compact list of extra knowledge-graph entities, and concrete goal suggestions.

**Where (Mac):** `OnboardingPagedIntroCoordinator.analyzeEnrichment`
(`OnboardingPagedIntroCoordinator.swift:1269-1383`) and `buildSuggestedGoals` (`1609-1636`) — the old
audit's `981-1092` for `analyzeEnrichment` was off by ~290 lines, caught while re-verifying.

**Windows status:** Still absent, re-confirmed. There is real per-source LLM extraction now (Gmail sync's
`extractGmailMemories`, the memory-log paste path's `extractMemories`), but nothing merges scan + email +
calendar + memory-log context into one profile summary, entity list, and goal-suggestion set the way
`analyzeEnrichment` does. `lib/goals.ts` (`generateGoal`) is still the only goal-facing LLM call, and it
still only takes an app-name list (see below) — it was not extended to consume anything Data Sources now
collects.

**Value / notes:** High, unchanged. This remains the largest genuine capability gap in the area — even
with Data Sources landed, there is no "connective tissue" step that turns the newly-collected Gmail/
Calendar/memory-log signal into a felt sense of personalization the way Mac's enrichment call does.

### Language step: multi-select vs single-select
**Where (Mac):** `OnboardingLanguageStepView.swift` + `OnboardingPagedIntroCoordinator.confirmLanguages`
— multi-select chip grid, selection order sets a primary, full list saved for per-turn language ID.

**Windows status:** Unchanged, re-confirmed by reading the current file. `LanguageStep.tsx`
(`desktop/windows/src/renderer/src/components/onboarding/LanguageStep.tsx`) is still a binary
English/Other choice with a single free-text field, resolved via `resolveLanguageCode` — no multi-select,
no primary/secondary distinction, no chip grid.

**Value / notes:** Medium, unchanged.

### Floating-bar demo: scripted vs live round trip
**Where (Mac):** `OnboardingFloatingBarDemoView.swift` — waits for a real keypress, then polls up to 60s
for a real AI response before revealing Continue.

**Windows status:** Unchanged, re-confirmed. `AskDemoStep.tsx`
(`desktop/windows/src/renderer/src/components/onboarding/AskDemoStep.tsx`) enables the overlay but never
waits for a keypress or a response — a static `macs.png` image fades in on a timer and Continue is
available immediately.

**Value / notes:** Medium, unchanged.

### Voice demo: capture vs response confirmation
**Where (Mac):** `OnboardingVoiceShortcutStepView.swift` (separate shortcut-only test) +
`OnboardingVoiceDemoView.swift` (waits for a completed AI response, with mute/zero-volume detection).

**Windows status:** Unchanged, re-confirmed. `VoiceIntroStep.tsx`
(`desktop/windows/src/renderer/src/components/onboarding/VoiceIntroStep.tsx`) merges both into one step,
unlocks Continue on `onVoiceCaptured()` — a completed *capture*, not a completed AI response — and adds
its own escape hatches (a 20s fallback timer, a "hold, don't tap" nudge, mic-blocked detection via the
real Capability Access Manager state) that have no direct Mac equivalent but serve a similar
"don't strand the user" purpose. Still no output-volume/mute detection and no separate shortcut-only
pre-test step.

**Value / notes:** Medium, unchanged.

### Accessibility / active-app-awareness permission
**Where (Mac):** `OnboardingPermissionStepView` instantiated with `permissionType: "accessibility"`.

**Windows status:** Absent, re-confirmed — no onboarding step, no corresponding preference anywhere in
`components/onboarding/`.

**Value / notes:** Medium, unchanged — may reflect a genuine platform difference (Windows UI Automation
vs. macOS Accessibility), but there's still no equivalent messaging or consent step at all.

### AI goal generation
**Where (Mac):** `GoalsAIService`, fed the full enrichment context (scan + email + calendar + notes +
web).

**Windows status:** Unchanged, re-confirmed by reading `lib/goals.ts` and `GoalStep.tsx`.
`generateGoal(apps)` (`lib/goals.ts:40-47`) builds a single prompt from just the app-name list via
`buildGoalPrompt` and calls `callAgentLLM` for one sentence — no email, calendar, or memory-log context,
even though the Data Sources step (which runs immediately before Goal in the flow, at index 12) now
collects some of that. The two starter cards in `GoalStep.tsx` (`SUGGESTED`) remain hardcoded strings,
not generated.

**Value / notes:** Medium, unchanged.

### Auto-created Tasks closing screen — corrected from "Present-equivalent" to "Absent (dead code)"
**What it is:** A closing screen previewing the tasks Omi auto-creates, meant to be the last thing a new
user sees before landing in the app.

**Where (Mac):** `OnboardingTasksStepView` (assumed still live; not independently re-verified this
pass — the Windows-side finding below stands on its own regardless).

**Windows status — corrected.** `AutoCreatedTasksStep.tsx`
(`desktop/windows/src/renderer/src/components/onboarding/AutoCreatedTasksStep.tsx`) still exists, still
compiles, and its own unit test (`AutoCreatedTasksStep.test.tsx`) still passes — but a grep of
`Onboarding.tsx` shows it is not imported. Commit `93dbeec0d4` ("fix(windows): simplify post-onboarding
controls", 2026-07-23 — three and a half weeks before the 2026-08-20 audit) removed the import, dropped
`TOTAL_STEPS` from 15 to 14, and made `GoalStep`'s `onContinue`/`onSkip` both call `finishToChat()`
directly (`setPendingRoute('/chat')` + `completeOnboarding()`). The commit message describes this as an
intentional product simplification, not a regression — but it means the row the old audit marked
"Present-equivalent" describes code that had already stopped being reachable for weeks by the time that
claim was written.

**Value / notes:** Low, but now correctly recorded as a gap rather than parity — this is a step Mac has
(assumed) and Windows no longer reaches, the mirror image of the dead-code finding the old audit itself
raised about Mac's `OnboardingChatView.swift`.

### Post-onboarding prompt suggestions
**Where (Mac):** `OnboardingPromptSuggestionBuilder.build` + `PostOnboardingPromptSuggestions`, invoked in
`OnboardingView.handleOnboardingComplete`.

**Windows status:** Absent, re-confirmed — no file, symbol, or call found anywhere in the renderer.

**Value / notes:** Low, unchanged — downstream of the still-missing enrichment synthesis, so there is
little personalized content to build a suggestion from even if this were added.

## Spotted outside my scope
- `OnboardingChatView.swift` (2157 lines, confirmed still present on Mac) — the previous audit's note
  that this large AI-chat-driven onboarding flow exists but is not instantiated in the current
  `OnboardingView.swift` paged flow was spot-checked (file exists, still not found via a direct
  instantiation grep) and appears to still hold. Not independently re-verified in full this pass; treat
  as carried forward with light confirmation, not a fresh finding.
- `OnboardingNotificationStepView.swift` (222 lines, confirmed still present) — same treatment: exists on
  disk, previously reported as deliberately unwired. Not re-verified beyond existence.
- Windows-only `BackgroundPrivacyStep` (always-on listening + launch-at-login consent) still has no Mac
  onboarding equivalent. Flagged again for the orchestrator in case this is worth recommending back to
  Mac rather than only closing gaps in the Windows→Mac direction.
- **New this pass:** `AutoCreatedTasksStep.tsx` is now itself an instance of the exact "built but
  unreachable" pattern the old audit flagged on the Mac side — worth the orchestrator's attention as
  Windows-side dead code / cleanup debt, independent of anything Mac-parity related. A repo-wide grep
  confirms the only references are the component's own file and its test.
- The Gmail sync-on-connect path (`lib/googleSync.ts`) that Data Sources now triggers is a general,
  always-on-when-connected background sync shared with Settings/Hub — it happens to also run during
  onboarding because that's one of the places a user can connect Gmail, not because anyone built it as
  onboarding-specific intelligence. Worth the orchestrator knowing this when scoping future onboarding
  work: enriching onboarding's *graph* (the confirmed remaining gap) may be able to piggyback on this
  existing extraction rather than needing a new pipeline.
