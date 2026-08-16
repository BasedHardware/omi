# Track 3 Ground Truth — Memories / Tasks / Goals pages + Home widgets

Scope: layout, IA, content/copy, and brand-token usage only. Track 3 renders these with
native Fluent/Windows components — do NOT clone SwiftUI chrome. Every Mac citation below
was read from source (not grep-inferred). Mac reference frozen at v0.12.72,
`C:/Users/chris/projects/omi/.worktrees/mac-ref/desktop/macos/`. Windows baseline read from
`C:/Users/chris/projects/omi/.worktrees/track3-proactive/desktop/windows/`.

---

## 1. Memories Page

**Mac source:** `Desktop/Sources/MainWindow/Pages/MemoriesPage.swift` (3171 lines).
**Windows source (current):** `src/renderer/src/pages/Memories.tsx` (479 lines).

### 1.1 Header (lines 1649-1826)

Single row, left to right:
1. **Search field** — magnifying-glass icon (spinner while searching/filtering), `TextField("Search memories...")`, clear (x-circle) button when non-empty.
2. **Layer filter dropdown** (`viewModel.canonicalLifecycleExposed` gated — a feature flag, may not always be present) — menu of `MemoryLayerFilter.allCases`:
   - `Default` — desc "Short-term + Long-term" (the baseline/no-filter state)
   - `Short-term` — desc "Fresh source-backed memories"
   - `Long-term` — desc "Stable memories"
   - `Archive` — desc "Explicit archive search"
   Button label shows selected filter name + chevron; icon swaps to `archivebox` for Archive, else `clock.badge.checkmark`. Non-default selections get a raised/stroked background to stand out from the default pill.
3. **"This device" toggle button** — `desktopcomputer` icon + "This device" label; toggles `filterThisDeviceOnly`; raised background + border when active. Tooltip: "Show memories captured on this Mac."
4. **Category filter dropdown** (button → popover, `MemoryTag` enum, `MemoriesPage.swift:9-51`):
   - `Manual` (icon `square.and.pencil`)
   - `About You` (raw case `system`, icon `person`)
   - `Insights` (raw case `interesting`, icon `lightbulb`)
   - `Workflow` (icon `arrow.triangle.branch`)
   Popover = search box + "All" row (count = total) + category rows (icon, name, count pill, checkmark if selected — multi-select), sorted by count descending, footer Clear / Apply buttons. Button label: "All" / single tag name / "N selected".
5. **Add Memory button** — icon-only `+`, black glyph on solid white/`textPrimary` rounded-16 square (42×42). Opens `AddMemorySheet` (textarea, ⌘/Ctrl+Enter save).
6. **Management menu button** — icon-only chevron-down, same black-on-white 42×42 style. Popover: "Visibility" section (Make Default Memories Private / Public — both disabled unless `areBulkServerMutationsAvailable`, with a tooltip explaining bulk mutation is backend-gated), divider, destructive "Delete Default Memories" (opens a confirm alert; message differs by whether canonical lifecycle is exposed).

**Windows today:** no layer filter, no category filter, no "This device" filter, and no default-view search box at all — search/filter only exists inside a separate "manage" (bulk-select) mode as one free-text field. This is the primary IA gap Track 3 must close.

### 1.2 Content states (in priority order, `MemoriesPage.swift:1536-1547`)
`isLoading && memories.isEmpty` → loading spinner + "Loading memories..." → else `errorMessage` → error view → else `memories.isEmpty` → empty state → else `filteredMemories.isEmpty` → no-results view → else → memory list.

- **Empty state** (`brain.head.profile` icon, "No Memories Yet", "Your memories and tips will appear here.\nMemories are extracted from your conversations.", **purple-filled** "Add Your First Memory" button).
- **No-results state** (filtered-empty; magnifyingglass icon, "No Results", "Try a different search or filter", "Clear Filters" text button if tags selected).
- **Error state** ("Failed to Load Memories", "Check your connection and try again.", **purple-filled** "Retry" button).

### 1.3 Memory list (lines 2104-2185)

Scroll container, `LazyVStack(spacing: 14)`:
1. **`MemoryGraphInlineCard`** (the Brain Map) is the FIRST item, always rendered above every memory card (not a separate section, not conditionally hidden except when the whole graph is empty — then it shows its own empty sub-state, see §1.6).
2. Nested `LazyVStack(spacing: 10)` of `MemoryCardView` rows, each `.onAppear` triggers pagination (`loadMoreIfNeeded`).
3. "Loading more..." spinner row, or a "Load more memories" button (works both in filtered and unfiltered pagination modes).

### 1.4 MemoryCardView (lines 2381-2485)

Tappable card (rounded-18, shadow, hover raises background to `backgroundRaised` + bigger shadow):
- **Headline/content**: `memory.content`, 2-line clamp, tail-truncated. If content starts with `[Protected` or `[Encrypted`, render italic "Protected memory" placeholder instead.
- **NewBadge** (top-right of content row) if `createdAt` is <60s old — purple text on 15%-purple background pill, "New".
- Footer row (all `textSecondary`/`textTertiary`, 11pt):
  - relative + absolute created date ("3h ago · Jan 4, 2:15 PM")
  - device provenance label (if resolvable)
  - **`MemoryLayerBadge`** (tier badge) — ONLY if `memory.tierIsExplicit` (untiered/legacy memories show no badge at all). Capsule: icon (layer-specific) + layer display name; Archive gets a stronger `backgroundRaised` fill, others a plain `backgroundTertiary` fill. Tapping opens a small info popover explaining the layer.
  - "From {sourceName}" if present
  - spacer
  - **`MemoryDetailButton`** — small `info.circle` icon; hover (250ms debounced dismiss) opens `MemoryDetailTooltip`, a compact metadata card showing (whichever apply): Layer + Expires-at (short-term only), Category/Subcategory (or Tips/Tip-subcategory), Tags (filtered to exclude category/tips/has-message pseudo-tags), App, Source, Window title, Context summary, Current activity, Confidence, Reasoning, Created (absolute).
  - on card hover only: trailing `arrow.up.right` affordance icon.
- Newly-created cards (and not currently hovered) get a `userBubble`-tinted background (24% opacity) instead of the plain `backgroundSecondary` — a soft highlight distinct from the NewBadge.

Tapping the card body (not the info button) opens **`MemoryDetailSheet`** (450×600 sheet):
- Header row: category/tips badge, spacer, **Public/Private toggle switch** (label "Public", live PATCH via `toggleVisibility`), delete icon (trash, `error` color — dismisses sheet then deletes), dismiss (X) button.
- Content: `memory.content` (click-to-edit → inline `TextEditor` + Cancel/Save, only for non-protected memories).
- "Why this tip?" block (reasoning, only if present).
- "Context" block (current activity + context summary, only if present).
- Metadata block (`backgroundTertiary` panel): Confidence, Source App, Device (icon + name), Microphone (desktop source only), Created (absolute), Tags (FlowLayout of colored tag chips).
- Action: "View Source Conversation" row (only if `conversationId` present) — navigates + dismisses.

### 1.5 Undo-delete toast (lines 1592-1645)

Bottom-overlay capsule/pill (not a corner toast): trash icon, "Memory deleted" text, a live countdown in seconds (`%.0fs`, monospaced), "Undo" text button, and an immediate-dismiss "x" button (confirms the delete right away instead of waiting out the countdown). Spring-animated slide-up-from-bottom + fade, 24pt margins.

### 1.6 Brain Map (`MemoryGraphInlineCard`, `Pages/MemoryGraph/MemoryGraphPage.swift:73-140`)

**Mount point:** inline card at the very top of the Memories list (see §1.3), NOT a separate route/page in this context (there is also a standalone full-screen `MemoryGraphPage`, not used here). Card chrome: "Brain Map" title + rebuild (`arrow.clockwise`) button (or spinner while rebuilding) in the header row, then a 350pt-tall rounded-20 panel containing the 3D scene (or a loading spinner, or an empty sub-state: `brain` icon + "Brain map will appear once enough linked memories are available.").

**Rendering engine (Mac only, informational — Windows already uses react-three-fiber, not SceneKit):** SceneKit force-directed 3D graph. Node types and colors (`KnowledgeGraphNodeType`, lines 973-1006):
| Node type | Mac color |
|---|---|
| person | cyan |
| place | mint green (`RGB 0, 255, 158`) |
| organization | orange |
| **thing** | **`.purple` (systemPurple)** |
| concept | blue (`systemBlue`) |
| fixed/center ("you") node | white, largest radius (35 vs. 14 + up to 25 for others) |

Edges are colored by blending their two endpoint node colors at 25% alpha. Every node has a glow halo (2.5× radius sphere, ~2.5-3% opacity, additive blend) plus a billboarded text label below it.

**Assemble-in animation (Chris's favorite — preserve this contract, don't flatten):**
- On a genuinely new/changed graph (signature = FNV-1a hash of node/edge ids+labels+types — stable across launches, unlike Swift's per-process `Hasher`): run the force-directed physics **800 ticks off-main** (detached task) before ever creating scene nodes, so the graph never visibly "jitters into place" on screen — nodes appear once already close to their final position. `isAnimating` is then held `true` for exactly **3 seconds** of live on-screen settle/damping, then auto-stops.
- On an **unchanged** graph (same signature as last time, incl. same session or a saved on-disk layout cache keyed by user), the settled layout is **restored instantly with zero physics run and zero animation** — this is the "revisiting the page doesn't reload the map" behavior. Track 3/4 must preserve this: don't replay the assemble animation on every mount, only on first-ever load or on a real graph diff.
- **Incremental add** (onboarding-style live growth, `addGraphFromStorage()`, lines 533-565): new nodes scale in from `0.01 → 1.0` over 0.5s, new edges fade `opacity 0 → 1` over 0.5s, camera re-fits (0.8s eased pull-back), then a fresh 3s settle window plays.
- Auto-fit camera: distance computed from `maxDist / tan(fov/2) * 1.3` (30% padding), never closer than a fixed minimum for tiny graphs.

**Windows `BrainGraph` prop interface** (read from `components/graph/BrainGraph.tsx:16-42` — Track 3 does not edit `components/graph/**`, only consumes via props):
```ts
export type BrainGraphProps = {
  graph: KnowledgeGraph
  centerNodeId?: string
  interactive?: boolean
  shuffleKey?: number | string        // changing it re-rolls/animates module positions
  pauseWhenHidden?: boolean           // unmounts the WebGL canvas while host is 0×0 (use for Memories)
  frameLoop?: 'always' | 'demand'     // 'demand' for idle-heavy surfaces like Memories
  onReady?: () => void                // fires once the WebGL context/scene is created
  onVisibleChange?: (visible: boolean) => void // fires on mount/unmount under pauseWhenHidden
}
```
Windows' existing `Memories.tsx` already wires this correctly: `interactive={false} pauseWhenHidden frameLoop="demand"`, plus its own `onReady`/`onVisibleChange` bounded-fallback loading placeholder (4s timeout) — this pattern should be kept as-is when Track 3 touches the surrounding page chrome.

**Purple decision already resolved:** `components/graph/nodeColor.ts` deliberately maps Mac's "thing" purple to **pink `#ff375f`** (comment: "purple is off-brand everywhere (INV-UI-1)"), keeping person=cyan `#22d3d3`, place=mint `#00ff9e`, organization=orange `#ff9f0a`, concept/default=blue `#0a84ff`, fixed=white. No action needed from Track 3 here — just don't regress it.

---

## 2. Tasks Page

**Mac source:** `Desktop/Sources/MainWindow/Pages/TasksPage.swift` (6026 lines — by far the richest page on Mac; most of its richness is explicitly out of scope, see §2.7), `TaskDetailViews.swift`, `MainWindow/Tasks/SuggestedTasksSection.swift`.
**Windows source (current):** `src/renderer/src/pages/Tasks.tsx` (613 lines).

### 2.1 Grouped-by-due layout — **IMPORTANT DIVERGENCE**

Mac's `TaskCategory` (lines 10-33) has exactly **4 groups, in this order**: `Today`, `Tomorrow`, `Later`, `No Deadline`. Critically, **overdue tasks fold into "Today"** (`categoryFor`, lines 1960-1973: `if dueAt < startOfTomorrow { return .today }`) — there is **no separate "Overdue" bucket** on Mac, matching the Flutter mobile app's grouping. Only non-empty groups render (`TasksPage.swift:3741`, `if !orderedTasks.isEmpty`).

**Windows today has 5 buckets**: `Overdue, Today, Tomorrow, Upcoming, No due date` (`pages/Tasks.tsx:129-148`) — a real IA divergence from Mac. Porting to Mac's IA means collapsing Overdue into Today and renaming Upcoming→Later (or keeping Upcoming as the Later-equivalent name — copy choice for Track 3, but the **grouping boundary** — overdue joins today, doesn't get its own section — is the thing to match).

Sort within each group: due date ascending (nulls last), then created-at descending as tiebreak (`sortTasks`, lines 1975-1986) — Windows already does this (`pages/Tasks.tsx:308-336`), consistent with Mac and the Python backend.

### 2.2 Header (lines 3056-3195)
Search field ("Search tasks..."), saved-filter-view chips (gated, §2.7), filter dropdown (gated, §2.7) OR multi-select controls when in multi-select mode (gated), chat-toggle button (if chat enabled), **Add task button** (`+` icon, tooltip "Add task (⌘N)" — opens the inline-creation row, not a modal), task-settings button.

### 2.3 Suggested Tasks quiet-capture strip (`SuggestedTasksSection.swift`)

Mounted **above** the inline-create-top row and **above all category groups**, inside the same scroll content (`TasksPage.swift:3721-3726`), suppressed when the view is filtered to only-done or only-deleted, or in multi-select mode.
- Loading (no candidates yet): spinner + "Checking Suggested".
- With candidates: header row — `tray` icon, "Suggested" title, count badge, trailing caption "Quietly captured for your review". Panel background: `backgroundSecondary` @72% + hairline border.
- Each `SuggestedCandidateCard`:
  - Title — editable inline `TextField` (multi-line, 1-3 lines) if `candidate.isEditableTask`, else static text (3-line clamp).
  - Optional detail line (2-line clamp, secondary color).
  - Provenance row: `link` icon + `provenanceLabel`, evidence count ("N source(s)").
  - Actions: **"Do now"** (prominent, white/black), **"Later"** (bordered), **"Dismiss"** (bordered → popover of optional reasons — "Already handled" / "Not mine" / "Not useful" — or dismiss-with-no-reason if the popover is closed without a selection).
- `AutoAcceptedTaskWhyButton` — a "Why" text button shown on any task row whose `source` is non-manual and has provenance, opening a popover: "Why Omi added this" + a one-line explanation derived from the source type (screen context / conversation / other authorized source) + linked-source count.

### 2.4 Inline task creation row (`InlineTaskCreationRow`, lines 5921-5969)

Circle placeholder styled like the row checkbox (purple-stroked, 50% opacity) + `TextField("New task...")`. **Distinctly purple-accented**: 5%-purple background fill, 30%-purple border, and a solid purple 3pt-wide left accent bar (`overlay(alignment: .leading)`). Enter commits, Escape cancels. Renders either at the very top of the list (`⌘N` / header `+`) or inline directly after a specific task row (context-dependent insert point).

### 2.5 Task row anatomy (`TaskRow`, lines 4444-4610 struct / 4763+ content)

Left to right:
1. Drag handle (gated, §2.7).
2. **Completion checkbox** — circle, empty-stroke → filled + animated checkmark on complete (or a square multi-select checkbox in multi-select mode — gated; or a "trash.slash" icon for soft-deleted tasks).
3. **Title** — plain text (click → inline edit, 1s debounce auto-save, Escape/blur commits), strikethrough when completed.
4. **Badge row** (`FlowLayout`, wraps): recurring icon (`repeat`), `NewBadge` (<60s old — purple text/bg, same component/style as Memories), `AutoAcceptedTaskWhyButton` (§2.3), chat-thread affordance ("Open thread" / "Work on this with Omi" — gated, N/A without the agent-chat system), `ChatSessionStatusIndicator` (gated), `TaskDetailButton` (info-circle → hover tooltip, click → `TaskDetailView` sheet).
5. **On-hover trailing overlay** (not a fixed layout slot — appears only on hover/active-picker, no layout shift): "Execute" pill (sparkles, spawn-agent — gated), "add due date" icon (only if no due date yet), **`PriorityBadgeInteractive`** (flag icon + High/Medium/Low label; grayscale by level — textPrimary/Secondary/Tertiary, NOT color-coded red/yellow/green; popover picker), outdent/indent buttons (gated).
6. **`DueDateBadgeInteractive`** — calendar icon + smart label: "Today" / "Tomorrow" / weekday name (within a week) / relative-past ("3d ago") / absolute date (`MMM d`), edit via popover date-picker.
7. **`TagBadgeInteractive`** — tag icon + up to 2 classification labels + "+N" overflow, popover multi-select capsule grid (colored per `TaskClassification`), "Done" button is **purple-filled**.

### 2.6 Detail sheet (`TaskDetailView`, `TaskDetailViews.swift:204-334`)

550×600 sheet. Header: "Task Details" + source pill (if present) + dismiss. Body sections (conditionally shown): Task description block, Core fields (always shown — description repeats plus structured fields), Context (activity/summary/reasoning — only if present), Agent (only if `agentStatus`/`agentPlan` present), then several **engineering/internal-bug-tracking-only** sections: Sentry, Reporter, Analysis (omi-analytics), App Info, Source (screenshot metadata), and a catch-all "remaining metadata" section. **These last six sections only populate for tasks sourced from `sentry_feedback`/screenshot/omi-analytics pipelines (internal bug tasks), not ordinary user action items** — Track 3 should treat them as N/A for the product Tasks page and only port Task/Core-fields/Context/Agent.

### 2.7 Explicitly gated — Windows will NOT build these (flag as **G-D**, do not port)

- Saved filter views (bookmark chips + save-current-filters flow).
- The rich multi-tag filter dropdown (`filterLabel`/`filterDropdownButton`, lines 3196+) beyond a simple open/done/all toggle.
- Drag-and-drop reordering, indent/outdent nesting (28pt-per-level), and the associated keyboard shortcuts.
- Multi-select mode + bulk delete.
- Per-task chat/agent threading ("Execute", "Work on this with Omi", "Open thread", `ChatSessionStatusIndicator`) — depends on the agent-chat system, separate track.
- Trackpad swipe-to-delete/indent gestures (`swipeableContent`) — not applicable on Windows anyway.
- The full context-sensitive `KeyboardHintBar` key set (multi-select/indent/outdent hints) — scope down to whatever subset of Navigate/New/Delete/Cancel actually applies once the above are gated out.

### 2.8 Empty view & undo toast

Empty (`emptyView`, lines 3680-3709): `tray.fill` icon (or `line.3.horizontal.decrease` if filtered-empty) + "All Caught Up!" ("No Matching Tasks" if filtered) + subtext + "Clear Filters" bordered button when filtered.

Undo toast (`UndoToastView`, lines 5871-5919): dark capsule, trash icon, "Task deleted" (+ "(N)" count if multiple queued), spacer, "Undo" pill button. Same shape/spirit as the Memories undo toast but as a capsule rather than a rounded-rect panel.

---

## 3. Goals Page

**Mac source:** Goals has **no dedicated routed "GoalsPage.swift"** — it's a Dashboard-embedded card (`MainWindow/Components/GoalsWidget.swift`, 952 lines: `GoalsWidget`, `GoalRowView`, `GoalEditSheet`, `GoalInsightSheet`), plus a separate full-screen sheet for history (`MainWindow/Pages/GoalsHistoryPage.swift`, 215 lines) and a fullscreen celebration overlay (`MainWindow/Components/GoalCelebrationView.swift`, 170 lines). **Windows already has a dedicated full `Goals.tsx` page** (662 lines) — that page-level choice is fine/Windows-appropriate; use the widget/history specs below as the content reference for what the page should show.

### 3.1 Goal card (`GoalRowView`, lines 145-534)

- **Emoji auto-icon** (36×36 rounded-12 tile) — derived from the goal title via a large keyword→emoji lookup (`goalEmoji`, ~28 categories: revenue/money→💰, users/growth→🚀, workout/gym→💪, run/steps→🏃, weight→⚖️, meditate/yoga→🧘, sleep→😴, water→💧, health→❤️, read/book→📚, learn/study→🎓, code/program→💻, language→🗣️, write/blog→✍️, video→🎬, music→🎵, art/draw→🎨, photo→📸, task/todo→✅, habit/streak→🔥, time→⏰, project/ship→🎯, travel→✈️, home→🏠, save/budget→🏦, friend/social→👥, family→👨‍👩‍👧, date/relationship→💕, win/best→🏆, grow/improve→🌱, star/success→⭐, **default 🎯**). Tapping the tile opens the edit sheet.
- Title (tap → edit sheet).
- Optional expand/collapse chevron — only shown if the goal has a `description` or has linked tasks.
- Advice/insight button (`lightbulb.fill`, yellow, **hover-only**) → opens `GoalInsightSheet`.
- Progress value text: "current/target" (or a live drag-preview value while dragging).
- **Progress bar** — a drag-to-set-progress bar/thumb, NOT a static display: background track (12% white), fill in a **5-stage discrete color threshold** (not a continuous gradient):
  | Progress | Color |
  |---|---|
  | ≥80% | `#22C55E` green |
  | ≥60% | `#84CC16` lime |
  | ≥40% | `#FBBF24` yellow |
  | ≥20% | `#F97316` orange |
  | <20% | neutral `textTertiary` |
  White circular drag-thumb always visible, height grows 6→8pt while dragging.
- Expanded section (if toggled open): description text (3-line clamp) + "LINKED TASKS" mini-checklist (fetched live via `getActionItems`, filtered by `goalId`, checkbox + strikethrough-when-complete rows).

### 3.2 Empty state (0 goals)

Centered **"Generate AI Goal"** button only (sparkles icon or spinner while generating, **purple text on 12%-purple background**) — no manual-entry composer shown by default in the empty state. The header's `+` button (shown only when `goals.count < 4`) is the separate manual-create entry point, opening `GoalEditSheet`.

### 3.3 Create/Edit sheet (`GoalEditSheet`, lines 539-712)

400-wide sheet (320h for create, 420h for edit). Fields: Goal Title text field, Current + Target number fields side-by-side. **No emoji picker is exposed in this sheet** despite an `availableEmojis` array existing in source (20 emoji) — the emoji is always auto-derived from the title text, never manually chosen. Footer: Delete (existing goals only, red text) / Cancel / **Save or "Add Goal" (purple-filled)**.

### 3.4 Insight/advice sheet (`GoalInsightSheet`, lines 716-887)

400×380 sheet. Header: lightbulb icon + "Goal Insight" + dismiss. Goal-info row: title + "current/target (pct%)" + a small circular progress ring (**purple stroke**). Body: loading spinner ("Getting personalized insight...") / error (orange triangle) / insight text under a "This week's action:" label (from `GoalsAIService.getGoalInsight`). Footer: "Refresh" (ghost) + "Done" (**purple-filled**).

### 3.5 Completion celebration (`GoalCelebrationView.swift`, full-screen overlay, not part of the widget itself)

Triggered by a `.goalCompleted` notification (fired elsewhere when progress reaches target) — **not** a dedicated done-checkbox in `GoalRowView` on Mac (completion is a side effect of progress reaching the target, same model Windows already uses). 4-phase sequence, ~3.3s total:
1. **Dim** (0.3s) — black scrim to ~40-50% opacity.
2. **Confetti** (0.3s) — 40-particle burst (mixed circles/rounded-rects) outward from screen center, 9-color palette: yellow, gold, green, blue, pink, orange, cyan, mint, **and 2 purple shades (`purplePrimary` + `purplePrimary` @70%)** — random angle/distance(80-300pt)/rotation(0-1080°) per particle.
3. **Text** (spring 0.5/0.7, appears ~0.8s in) — "Goal Completed!" in a yellow→orange→yellow gradient with a yellow glow/shadow, then the goal title, then "{target} {unit} reached".
4. **Fade-out** at 3.0s (0.5s), fully clears at 3.5s.

### 3.6 Goals History (`GoalsHistoryPage.swift`, separate full-screen sheet, opened from the widget)

Back button + "Goals History" title (balanced header). States: loading / error / empty (`trophy` icon, "No goals history yet", "Completed and removed goals will appear here") / list of `CompletedGoalRow`:
- Emoji tile (smaller keyword table subset, same idea as §3.1, default 🎯).
- Title, type badge ("Yes/No" / "Scale" / "Numeric" — **purple text on 15%-purple background**) + final value/unit.
- Trailing status: green checkmark + relative completion date (if actually completed), or a dim x + "Removed" (if archived without completing).

### 3.7 Windows `Goals.tsx` today, for comparison (what already exists vs. the spec above)

- Flat **Active / Completed** sections (no due-date-style grouping needed on either platform — goals aren't date-grouped).
- Plain-text titles — **no emoji auto-icon at all**.
- Single-color progress bar (white/emerald fill) — **no 5-stage color-threshold ramp**.
- Completion driven by an explicit checkbox (`toggleComplete`) that PATCHes progress to the target value (there is no backend write path for `is_active`/status — verified 400/no route — so this mirrors Mac's "completion = progress reaches target" model correctly), with a plain success toast ("Goal complete 🎉") instead of the confetti/dim/gradient-text celebration.
- An inline AI-suggestion **preview card** flow (`GET /v1/goals/suggest` → dismissable "Suggested goal" card with Add/Another/Dismiss) — materially different UX from Mac's plain centered "Generate AI Goal" empty-state button (Mac's flow directly creates on click; Windows previews first). Not necessarily wrong, but a real UX divergence Track 3 should decide about deliberately rather than by accident.
- No insight/advice surface at all.
- No separate goals-history page — the existing "Completed" section already serves that role, so Track 3 likely does NOT need to port a separate history sheet, just make sure the Completed section shows the type-badge/status content `CompletedGoalRow` shows.

---

## 4. Home Hub widgets (for Track 5's Hub to mount)

**Mac source:** `Desktop/Sources/MainWindow/Dashboard/WhatMattersNowSection.swift` (506 lines — both widgets live in this one file), mounted from `MainWindow/Pages/DashboardPage.swift` (3 call sites: lines 760, 1797, 1976 — main dashboard placement plus at least one secondary/compact context).

### 4.1 `WhatMattersNowSection` (lines 4-45)

Renders nothing if `store.recommendations` is empty. Otherwise: rounded-14 panel (`backgroundSecondary` @72% + hairline border), header "What matters now", then a horizontal row of `WhatMattersNowCard`s (one per recommendation, min-height 152):
- Headline (2-line, semibold).
- `whyNow` explanation text (3-line, secondary color).
- Optional `contextLabel` (target icon + 1-line tertiary text).
- Optional `evidencePreview` (link icon + 1-line text).
- Actions: primary button labeled `recommendation.recommendedAction` (prominent white/black style), "Later" (bordered), "Dismiss" (bordered → popover: Already handled / Not mine / Not useful, or dismiss-with-no-reason on popover close).

**Data dependency:** a `DashboardIntelligenceStore`-equivalent exposing `recommendations: [DashboardRecommendation]` where each item has (at minimum) `interventionID`, `headline`, `whyNow`, `contextLabel?`, `evidencePreview`, `recommendedAction`. **Callbacks:** `onOpen(recommendation) async -> Bool` (primary action; on success calls `store.recordPrimaryAction`), `later(recommendation)`, `dismiss(recommendation, reason?)`.

### 4.2 `FocusedGoalsSection` (lines 145-189)

Single-line row:
- If `store.focusedGoals` is non-empty: "Focused goals" label + up to **5** goal-title chip buttons (capsule, `backgroundSecondary` @80%) each calling `onOpenGoal(goalId)`, trailing "All goals" text button (`onShowAll`).
- Else if `store.accountGeneration != nil` (i.e., data has actually loaded, this isn't just a cold-start blank): "No focused goals" text + a button labeled "Add goal" (if `store.goals` is entirely empty) or "Choose focus" (if there are goals but none focused) — both call `onShowAll`.
- Else (no `accountGeneration` yet): renders nothing (avoids a flash of "no focused goals" before the first load completes).

**Data dependency:** `focusedGoals: [{goalId, title}]` (only the first 5 rendered), `goals: [...]` (to decide the empty-state button label), `accountGeneration` (readiness gate — Track 3's Windows equivalent should gate on "has this store loaded at least once", not literally an `accountGeneration` field name).

### 4.3 Mounting guidance for Track 3 / Track 5

Both sections should be exposed as standalone, prop-driven components — a data-hook equivalent of `DashboardIntelligenceStore` plus `onOpen`/`onOpenGoal`/`onShowAll` callbacks — so Track 5's Hub can mount them without pulling in the rest of the Mac `DashboardPage`. Neither section owns navigation itself (they call back out via the props above); Track 5 decides what "open"/"show all" actually does in the Windows Hub.

### 4.4 DELETE — legacy Windows Home widgets these replace

- **`src/renderer/src/components/home/QuickTaskWidget.tsx`** — a preview of the next 2-3 open tasks sorted by due date, with a due-chip (Today/Tomorrow/Overdue/date), linking to `/tasks`. Predates the WhatMattersNow model; has no "why this matters now" reasoning, no dismiss/later actions, no evidence/provenance.
- **`src/renderer/src/components/home/QuickGoalsWidget.tsx`** — a preview of the first 2 active goals with mini progress bars, "Generate" button in the empty state, linking to `/goals`. Predates the FocusedGoals model; shows *any* active goals rather than a curated focus set, and has no "choose focus"/"all goals" concept.

Both should be deleted once `WhatMattersNowSection`- and `FocusedGoalsSection`-equivalents are mounted in the Windows Hub (Track 5's responsibility to wire; Track 3's responsibility to build the mountable components).

---

## 5. Purple-vs-neutral map (binding — port as-is; Mac beta still ships purple)

Per the brief: **do not introduce purple where Mac renders neutral**, but where Mac genuinely uses purple as its primary-CTA/"new"/"AI" accent, port it as specified — Track 3 is not responsible for de-purpling Mac's design language, only for not adding *new* purple beyond what's documented here. (Windows brand tokens: `purple.primary` etc. in `tailwind.config.ts` are already neutralized to white per `INV-UI-1` — see `docs/mac-parity-audit/13-ui-components-visual.md` §"Design system tokens" — so anywhere below marked purple should map to Windows' *own* neutral primary treatment, e.g. `btn-primary`'s existing white/glass style, not to the raw `--accent: #5b02e0` CSS variable, which is a separate, already-flagged live purple leak elsewhere in the app that Track 3 must not reuse.)

| Page | Element | Mac color |
|---|---|---|
| Memories | Empty-state "Add Your First Memory" button | `purplePrimary` fill |
| Memories | Error-state "Retry" button | `purplePrimary` fill |
| Memories | Newly-created card background tint | `userBubble` (#43389F family) @24% opacity |
| Memories | Brain Map "thing" node | SwiftUI `.purple` (systemPurple) — **already de-purpled to pink `#ff375f`** in Windows `nodeColor.ts`, settled, no action needed |
| Memories + Tasks | `NewBadge` ("New" pill, <60s old) | `purplePrimary` text on 15%-purple background |
| Tasks | `InlineTaskCreationRow` (checkbox stroke, background fill, border, left accent bar) | `purplePrimary` throughout (checkbox 50%, bg 5%, border 30%, accent bar solid) |
| Tasks | `TagBadgeInteractive` popover "Done" button | `purplePrimary` fill |
| Goals | Empty-state "Generate AI Goal" button | `purplePrimary` text on 12%-purple background |
| Goals | `GoalEditSheet` Save/Add Goal button | `purplePrimary` fill |
| Goals | `GoalInsightSheet` progress ring + Done button | `purplePrimary` stroke / fill |
| Goals | `GoalCelebrationView` confetti palette | 2 of 9 particle colors are `purplePrimary` shades (~20% of particles) |
| Goals | `GoalsHistoryPage` type badge (Yes/No · Scale · Numeric) | `purplePrimary` text on 15%-purple background |

**Net pattern:** on Mac, purple is the default "primary confirm" / "new-and-AI-generated" accent across all three pages — essentially every primary-action button and every "new/AI" badge. Windows' existing `.btn-primary` (white/glass, `globals.css:276-286`) is the correct neutral substitute already in use in the reviewed `Memories.tsx`/`Tasks.tsx`/`Goals.tsx` source — confirm this stays true for each specific element listed above when porting, rather than reaching for the separately-flagged `--accent` purple leak.
