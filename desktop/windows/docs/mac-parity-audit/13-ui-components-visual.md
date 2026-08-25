# Mac→Windows Parity Audit — UI Components & Visual Layer

> Scope: reusable visual components, design tokens, animations/effects, iconography, and interaction micro-patterns — not the features behind them (those are audited by other agents). Windows baseline checked: `src/renderer/src/components/**`, `src/renderer/src/styles/globals.css`, `tailwind.config.ts`, `src/main/bar/window.ts`, `resources/`, `src/renderer/src/assets/`. Every Mac file cited below was read in full (not grep-inferred).

## Summary table

| Component / effect | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Semantic color palette (`OmiColors`) | `Theme/OmiColors.swift` | Partial — tokens exist but purple family is a live compliance risk (see deltas) | H |
| Chrome/panel system (`OmiChrome`, `omiPanel`/`omiControlSurface`) | `Theme/OmiChrome.swift` | Partial — `.glass`/`.glass-subtle`/`.glass-strong` cover it, no named radius scale | M |
| User-adjustable font scale | `Theme/OmiFont.swift` | Absent | M |
| Window vibrancy/material (`NSVisualEffectView`) | `FloatingControlBar/FloatingBackgroundModifier.swift` | Absent (flat solid fill, explicitly "no DWM material") | M |
| Glow border/edge ambient focus effect | `ProactiveAssistants/UI/Glow{Border,Edge,Overlay}*.swift` | Absent | H |
| Goal celebration (confetti + dim + gradient text) | `MainWindow/Components/GoalCelebrationView.swift` | Present-but-much-weaker (plain success toast) | H |
| Floating-bar notch morph | `FloatingControlBar/FloatingBarNotchTransition.swift` | Present, different technique, comparable fidelity | M |
| PTT voice waveform bars | `FloatingControlBar/VoiceWaveformBars.swift` | Present, comparable/more sophisticated | M |
| Agent provider logo mark + status-tinted pill system | `FloatingControlBar/AgentProviderLogoMark.swift`, `AgentPill.swift` | Absent | H |
| Chat bubble system (tool cards, thinking block, discovery/agent cards, rating/copy) | `MainWindow/Components/ChatBubble.swift` | Partial — bubbles exist, all card types absent | H |
| Chat sessions sidebar (multi-thread: date-grouped, starred, searchable, rename) | `MainWindow/Components/ChatSessionsSidebar.swift` | Absent — single-thread architecture, no session concept | H |
| Typing indicator (rotating dot ring) | `Chat/TypingIndicator.swift` | Absent (literal `…` text) | M |
| Speaker color-coded bubbles | `MainWindow/Components/SpeakerBubbleView.swift` | Absent | M |
| Audio level waveform (12-bar meter) | `MainWindow/Components/AudioLevelWaveformView.swift` | Present via a different component, comparable | L |
| Selectable markdown (cross-paragraph selection, GFM tables) | `MainWindow/Components/SelectableMarkdown.swift` | Partial — no tables, no distinct heading styling | M |
| Citation cards | `MainWindow/Components/CitationCardView.swift` | Absent | M |
| Screenshot thumbnail (hover delete, OCR/search badges) | `Rewind/UI/ScreenshotThumbnailView.swift` | Partial — filmstrip only, no delete/OCR badge | M |
| Per-app icon rendering | `Rewind/UI/AppIconView.swift` | Absent (text label only) | L |
| Interactive timeline bar (Canvas playhead glow, gap dashes, tooltip) | `Rewind/UI/InteractiveTimelineBar.swift` | Partial — DOM equivalent, no glow/tooltip/gap-dash | M |
| Full-screen timeline player (transport: play/pause/step/speed/seek) | `Rewind/UI/RewindTimelinePlayerView.swift` | Absent — image pane + lightbox only, no transport | H |
| Rewind search bar (app filter, date picker, quick-date chips, focus anim) | `Rewind/UI/RewindSearchBar.swift` | Absent — bare `<input>` + button, no filters/polish | M |
| Search results filmstrip (hover scale/lift/glow, spring) | `Rewind/UI/SearchResultsFilmstrip.swift` | Absent (plain text list, not a filmstrip) | H |
| Onboarding orbital loading animation | `FileIndexing/OnboardingLoadingAnimation.swift` | Present, comparable-to-better | — (parity) |
| Onboarding step transition | `Onboarding/OnboardingView.swift` (hard cut) | **Windows ahead** — `animate-fade-in` on each step mount | — (Windows ahead) |
| Onboarding demo-step choreography (bar/voice multi-phase gating, volume warning) | `Onboarding/OnboardingFloatingBarDemoView.swift`, `OnboardingVoiceDemoView.swift` | Partial — reveal anim present, gating intentionally simplified | L |
| Drag-anywhere + resize-handle floating bar | `FloatingControlBar/{DraggableAreaView,ResizeHandleView}.swift` | Absent (architectural: bar is fixed to top edge) | M |
| Click-through window behavior | `MainWindow/ClickThroughView.swift` | Present, comparable | — (parity) |
| Sound-cue feedback (focus lost/regained) | `Resources/focus-{lost,regained}.aiff` | Absent | L |
| Provider/branding logo assets | `Resources/{hermes,openclaw}_logo*.png`, `herologo.png`, onboarding lineup | Mostly absent (2 generic logo PNGs only) | L |
| State-driven tray icon | `Resources/tray_icon.png` (static) | **Windows wins**: idle/listening/paused `.ico` set | — (Windows ahead) |

## Design system tokens

**What it is (Mac):** `OmiColors` (`Theme/OmiColors.swift`) is a single enum of ~25 named `Color` constants: 5-step background scale (`backgroundPrimary` 0x0F0F0F → `backgroundQuaternary`/`backgroundRaised`), one `border` color, a 4-color purple accent family (`purplePrimary` 0x8B5CF6, `purpleSecondary`, `purpleAccent`, `purpleLight`), a 4-step text hierarchy, status colors (success/warning/error/info/amber), macOS traffic-light button colors, a 6-color dark-tone `speakerColors` array, a dedicated `userBubble` color, and two purple `LinearGradient`s. `OmiChrome.swift` defines a named corner-radius scale (`windowRadius` 26 → `chipRadius` 14) plus two view modifiers, `omiPanel`/`omiControlSurface`, that bundle fill + radius + optional stroke + shadow (opacity/radius/y-offset) into one call. `OmiFont.swift` adds a **user-adjustable global font scale** (`FontScaleSettings`, persisted to `UserDefaults`, injected via `\.fontScale` environment key) that every `scaledFont(size:)` call in the app respects — an accessibility/readability feature that touches every text element.

**Where (Mac):** `desktop/macos/Desktop/Sources/Theme/{OmiColors,OmiChrome,OmiFont}.swift`.

**Windows status:**
- Color palette: Partial. `tailwind.config.ts` defines `text.{primary,secondary,tertiary,quaternary}` at fixed white-opacity steps and a `purple.{primary,secondary,accent,light}` family — but every value in that family has been redefined to **white** opacity (e.g. `purple.primary: 'rgba(255,255,255,0.9)'`), i.e. the token names survive but the color has already been neutralized, presumably for `INV-UI-1` compliance. However, `globals.css:48` separately defines `--accent: #5b02e0` (a literal violet hex, RGB 91/2/224) as a raw CSS custom property, **decoupled from the Tailwind purple tokens**, and it is actively consumed via `bg-[color:var(--accent)]` / `text-[color:var(--accent)]` / `border-[color:var(--accent)]` in at least 10 files: `Toggle.tsx`, `Home.tsx` (user chat bubble), `GenerateGoalsButton.tsx`, `SettingsTabRail.tsx`, `SettingRow.tsx`, `RewindTimelineBar.tsx` (playhead), `RewindThumbnailStrip.tsx` (active thumbnail border+ring), `RewindSearchBar.tsx`, `Sidebar.tsx` (active icon/dot/text), and `ShortcutSetupStep.tsx` — which additionally applies a literal purple glow: `shadow-[0_0_24px_4px_rgba(91,2,224,0.55)]`. **This is a live INV-UI-1 violation risk, not just a missing feature** — worth flagging to whoever owns the no-purple ratchet check.
- Radius/shadow system: Partial. `.glass`/`.glass-subtle`/`.glass-strong` in `globals.css` bundle background+border+blur+shadow similarly to `omiPanel`, but there's no named radius scale equivalent to `OmiChrome` — call sites use ad hoc `rounded-xl`/`rounded-2xl`/`rounded-3xl`.
- Font scale: Absent. No `fontScale`-equivalent setting found anywhere in `src/renderer/src` (grepped for `fontscale`/`font-scale`/text-scale settings — no hits). Text sizes are fixed Tailwind classes (`text-sm`, `text-xs`, etc.) with no user-adjustable multiplier.

**Value/notes:** The purple-token neutralization shows someone already did the right thing for the *named* palette — but the raw `--accent` hex bypasses that safeguard entirely and is the single most concrete, actionable finding in this audit (10+ call sites, one of them an explicit purple-tinted glow shadow).

## Window vibrancy / material

**What it is (Mac):** `FloatingBackgroundModifier` (`FloatingControlBar/FloatingBackgroundModifier.swift`) wraps `NSVisualEffectView` (material `.hudWindow`, `.behindWindow` blending, 0.95 alpha) plus an 18%-opacity black overlay, giving the floating bar genuine OS-level background blur/vibrancy that reacts to what's behind the window. A `solidBackground` user setting swaps it for flat `NSColor(white:0.12)` when vibrancy is disabled.

**Where (Mac):** `FloatingControlBar/FloatingBackgroundModifier.swift`.

**How it works:** `NSViewRepresentable` wrapping `NSVisualEffectView`; `.clipShape(.rect(cornerRadius:))` + 1px black stroke overlay.

**Windows status:** Absent. `bar.css` states outright: *"The top-edge bar window is TRANSPARENT (no DWM material) — the page paints everything."* The bar surface (`bar-surface`) is a flat `rgba(12,12,12,0.96)` fill with a 7%-white border and a drop shadow — no OS compositor blur. Windows' `.glass`/`.glass-strong` utility classes elsewhere in the app use CSS `backdrop-filter: blur()` (24–36px) which blurs the web content behind them, not the desktop behind the window — a materially different effect from `NSVisualEffectView`'s true behind-window vibrancy, and DWM acrylic/Mica APIs are not used for the bar itself (the insight-toast window comment does mention "thin wash over the DWM acrylic backdrop," so DWM material is used there, just not for the main bar).

**Value/notes:** Medium — cosmetic but contributes meaningfully to the "glass" feel Mac is going for; CSS `backdrop-filter` is a reasonable analog for panels floating over app content, just not for a window sitting over the whole desktop.

## Glow border / edge / overlay (ambient focus-state effect)

**What it is:** A full-screen ambient glow that appears around the user's active window to signal focus state — green/cyan animated mesh gradient when focused, red/orange when distracted. Rendered as a soft blurred border (`GlowBorderView`, 8pt blur outer + 2pt blur inner ring) or, in a newer variant, four independent edge windows (`GlowEdgeWindow`, one per side) so hover events on the target window's interior aren't blocked. Both use `MeshGradient` (macOS 15+) or an `AngularGradient` fallback, animated through an `.easeInOut(1.5s).repeatCount(3, autoreverses: true)` phase cycle, fading in over 0.3s and out over 0.5s after ~2.5s total.

**Where (Mac):** `ProactiveAssistants/UI/GlowBorderView.swift`, `GlowEdgeWindow.swift`, `GlowOverlayWindow.swift` (the `NSWindow` host: `.borderless`, `.popUpMenu` level, `ignoresMouseEvents = true`, `.canJoinAllSpaces`).

**How it works:** SwiftUI `MeshGradient`/`AngularGradient` + `.blur()` + `.mask()` compositing (`.blendMode(.destinationOut)` to hollow out the window interior), hosted in transparent always-on-top click-through `NSWindow`s positioned around (not over) the target window.

**Windows status:** Absent. No glow/focus-halo window or CSS equivalent found anywhere in `src/renderer` or `src/main`. Corroborating evidence: the backend API client (`omiApi.generated.ts`) has a `glow_overlay_enabled` field in its generated types (mirroring a setting that presumably exists for Mac), but it is never referenced anywhere else in the Windows renderer — the setting exists in the shared API schema with no Windows UI to read, write, or render it.

**Value/notes:** High — this is Mac's most distinctive proactive-focus visual and has zero Windows presence, not even a stub. Any color choice here should stay green/red/neutral per the existing Mac hue mapping — not purple.

## Goal celebration (confetti burst)

**What it is:** A fullscreen celebration overlay triggered on `.goalCompleted`: a black dim scrim ramps to 40–50% opacity, a 40-particle confetti burst (mixed circles/rects, 9-color palette including gold/green/blue/pink/cyan/mint and `OmiColors.purplePrimary`) fires outward from center with per-particle random angle/distance/rotation, then "Goal Completed!" text fades in with a yellow→orange→yellow gradient fill and a shadow glow, followed by the goal title and a summary line, all via a 4-phase timed sequence (dim 0.3s → confetti 0.3s → text via spring(response:0.5, dampingFraction:0.7) → fade-out at 3.0s).

**Where (Mac):** `MainWindow/Components/GoalCelebrationView.swift` (`GoalConfettiView` for the particle system).

**How it works:** Pure SwiftUI: `ForEach` over 40 randomized particle configs, `.offset`/`.rotationEffect`/`.scaleEffect` animated via `withAnimation`, sequenced with `DispatchQueue.main.asyncAfter`.

**Windows status:** Present-but-much-weaker. `pages/Goals.tsx` fires `toast('Goal complete 🎉', { tone: 'success', body: g.title })` on reaching a target — this renders through the generic `ToastHost` (a small bottom-right glass card that fades in, no dim/scrim, no particles, no gradient text, no phased sequence). Confirmed by grepping the whole renderer tree for `confetti`/`celebrat`/`glow`: no celebration-specific component exists.

**Value/notes:** High-value gap for a moment product wants to be delightful; the Windows version is functionally present (user is notified) but visually a completely different tier of experience.

## Floating-bar notch morph

**What it is:** The floating control bar smoothly grows from a small "notch" sliver (2×1pt at the target's bottom-center) into its full pill/panel shape using an eased (`1 - (1-progress)²`) width/height interpolation anchored to `midX`/`maxY`, so it reads as the bar "growing out of" the screen edge.

**Where (Mac):** `FloatingControlBar/FloatingBarNotchTransition.swift` — pure geometry math (`revealProgress`, `growFrame`, `growFrames`) consumed by the `NSWindow` frame-animation driver elsewhere in `FloatingControlBar/`.

**How it works:** Native `NSWindow.setFrame` sequence driven by the eased progress function — an actual window-frame animation, not a view transform.

**Windows status:** Present, different technique, comparable fidelity. `components/bar/bar.css`'s `.bar-surface` interpolates `width`/`height`/`border-radius` via CSS `transition` (260ms `cubic-bezier(0.3, 0.8, 0.3, 1)`) between a 148×36 pill and a 336×(measured) panel — "ONE element interpolating pill ⇄ panel," per the file's own comment, explicitly modeled as a single morphing surface rather than a crossfade, which is the same design intent as Mac's notch transition. The technical implementation differs (CSS layout transition on a fixed-size transparent window vs. actual `NSWindow` frame resizing) but the visual result — one shape growing/shrinking with eased timing — is a legitimate parity match, not a gap.

**Value/notes:** No action needed; this is one of the better-matched pairs in the audit.

## PTT voice waveform bars

**What it is (Mac):** 5 chunky bars in the floating bar that bounce to the user's voice in real time ("HeyClicky-style"), replacing an older pulsing-dot indicator. Driven by a per-bar underdamped spring model (stiffness 200, damping 10 → visible bounce/overshoot) with auto-gain (normalizes against a decaying recent-peak envelope so quiet/loud mics both fill the bar range) and an idle "breathing" wobble so the bars never look dead even at low signal. Rendered via `Canvas` + `TimelineView(.animation)` reading `AudioLevelMonitor.shared.microphoneLevel` at ~5Hz and springing at 60fps; filled with a purple gradient (`purpleAccent`→`purplePrimary`).

**Where (Mac):** `FloatingControlBar/VoiceWaveformBars.swift` (`WaveBarsModel` is the physics engine).

**Windows status:** Present, comparable/more sophisticated. `components/overlay/Waveform.tsx` renders 24 bars (vs Mac's 5) reading `analyser.getByteFrequencyData` directly on every `requestAnimationFrame`, with a genuinely more advanced **adaptive noise-gate**: it learns an ambient noise floor (rising slowly toward steady room noise, falling fast when the room quiets) and only treats level *above* that learned floor as speech — explicitly modeled as "like a videoconference mic meter," tuned to avoid fan/hum false-positives that a fixed threshold would catch. Bar heights are eased (`SMOOTH = 0.18`) via direct `style.transform` writes (no React re-render per frame), functionally the same "spring toward target" idea as Mac's underdamped spring, achieving 60fps without React state churn. Color is neutral (`bg-neutral-200`), correctly avoiding the purple Mac uses here.

**Value/notes:** No gap to close — if anything the Windows noise-gate logic is more thoughtful than Mac's raw-level auto-gain. Worth Mac picking up the ambient-floor idea, but that's out of this audit's direction.

## Agent provider logo mark + status-tinted pill system

**What it is:** A visible row of "pills" in the floating bar/chat surface, one per background/subagent run, each showing a status-tinted identity mark: `AgentProviderLogoMark` renders the Hermes/OpenClaw logo template-tinted to the pill's status color (queued=cyan, starting/running=amber, done=green, stopped=gray, failed=red — `AgentPill.Status.tintColor`), falling back to a flat robot-emoji-masked circle for providers without a dedicated logo, or a plain status-color circle with no provider at all.

**Where (Mac):** `FloatingControlBar/AgentProviderLogoMark.swift`, `FloatingControlBar/AgentPill.swift` (status/tint model), consumed throughout `ChatBubble.swift`'s `AgentSpawnCard`/`AgentCompletionCard`.

**Windows status:** Absent. No `AgentPill`/pill-row/provider-logo equivalent exists in `src/renderer/src/components` (grepped the whole tree). `SandboxBadge.tsx` is unrelated — a dev-only fixed-position debug label for distinguishing sandboxed windows, not a status system. No Hermes/OpenClaw logo assets exist anywhere under `src/renderer/src/assets` or `resources/` (only `omi-logo.png`, `omilogo.png`, `macs.png`, and boilerplate `electron.svg` are present).

**Value/notes:** High — this is a whole visual subsystem (identity + status color language for background agent work) with no Windows presence at all, consistent with background/floating-agent pills likely being out of scope for the current Windows feature set (flagged for the orchestrator to confirm whether this is a feature gap owned by another team or a genuine visual-parity gap).

## Chat bubble system (tool cards, thinking block, discovery/agent cards)

**What it is (Mac):** `ChatBubble.swift` is the single largest visual component in the app: circular AI/user avatars, sender-colored bubbles (`userBubble` purple-ish fill vs. `backgroundTertiary` for AI), a full **tool-call visualization system** — collapsible `ToolCallsGroup`/`ToolCallCard` rows with per-status icons (running spinner, slow=orange spinner, stalled=orange triangle, completed=green check, failed=red X), a "taking longer than usual" stalled banner with Cancel, an italicized collapsible `ThinkingBlock`, a `DiscoveryCard` for profile-summary results, `AgentSpawnCard`/`AgentCompletionCard` for background-agent handoffs (with open-agent deep links), rating buttons (thumbs up/down with a "Thank you!" confirmation), a copy button (icon swaps to checkmark on copy), an info popover for response metadata, and citation cards below AI replies. All chrome uses the shared `omiControlSurface`/`omiPanel` radius+shadow system.

**Where (Mac):** `MainWindow/Components/ChatBubble.swift` (1800+ lines).

**Windows status:** Partial. `components/chat/ChatMessages.tsx` covers the baseline: two bubble variants (`main`/`overlay`) with asymmetric rounded corners, a `bubble-in` CSS entrance animation, and a smooth character-by-character reveal for streaming replies (`RevealMarkdown`, 16ms/2-char-min ticks) — a nice touch Mac doesn't have in this exact form. But every structured-content type is absent: no avatars, no tool-call cards/status icons, no thinking block, no discovery card, no agent spawn/completion cards, no rating buttons, no copy button, no info popover, no citation cards. Windows' assistant/user distinction is plain markdown text in a bubble; there is no equivalent to Mac's `ContentBlockGroup` rendering pipeline at all in the reviewed components (worth double-checking with the chat-agent/tasks-goals owners in case agent-content-block rendering lives elsewhere).

**Value/notes:** High — largest single component gap in the audit by surface area, though much of it (tool-call cards, agent spawn cards) is downstream of the Absent agent-pill system above, so the two gaps likely close together.

## Chat sessions sidebar (multiple conversation threads)

**What it is (Mac):** A fixed-220pt left sidebar listing chat sessions grouped by date, with a "New Chat" button, a "Starred" filter toggle, a live search field, and per-session rows showing title/preview/star plus hover-revealed rename/star/delete actions (delete behind a confirmation alert). Titles are inline-editable (double-click or pencil → `TextField` → Enter/Esc).

**Where (Mac):** `MainWindow/Components/ChatSessionsSidebar.swift` (`ChatSessionsSidebar`, `SessionRow`), backed by `ChatProvider` (`groupedSessions`, `filteredSessions`, `createNewSession()`, `selectSession()`, `deleteSession()`, `toggleStarred()`, `updateSessionTitle()`).

**How it works:** SwiftUI `ScrollView` + `LazyVStack`, `@ObservedObject` provider driving all state, `.alert(...)` for delete confirmation, `@FocusState` for the rename field.

**Windows status:** Absent. Windows chat (`hooks/useChat.ts`) is architected around a **single ongoing thread** — the hook's own comments say "the MAIN window shows the ongoing thread" and "Start a fresh thread: drop the history…". There is no `ChatSession` type, no session list, no starring, no cross-chat search, no per-thread rename anywhere in the renderer. Both chat surfaces (`pages/Home.tsx` main window, `bar/AskPanel.tsx` overlay) render exactly one thread each, with an Esc "reset" that just clears the current thread rather than switching between saved ones.

**Value/notes:** High — this is a bigger architectural gap than a visual one. It's not skinning existing session data; Windows has no session concept in its data layer at all (per the files reviewed), so the whole sidebar + its `ChatProvider`-style multi-session store would be net-new. Cross-ref the chat-agent audit for whether multi-session chat is on the Windows roadmap.

## Typing indicator

**What it is (Mac):** `OmiThinkingMark` — 8 dots arranged in a ring, each dimmer than the last (opacity trail effect), continuously rotating at 360°/0.9s linear, rendered in a rounded pill (`TypingIndicator`). Uses `.drawingGroup(opaque: false, colorMode: .linear)` for GPU-composited smoothness.

**Where (Mac):** `Chat/TypingIndicator.swift`.

**Windows status:** Absent. `ChatMessages.tsx` shows a literal `'…'` string when `sending` is true and no content has streamed yet — no animated indicator, no dot ring, no pulsing.

**Value/notes:** Medium — small component, cheap to notice as "unfinished" since it's the very first thing a user sees after sending a message.

## Speaker color-coded transcript bubbles

**What it is (Mac):** Live/saved transcript segments render as chat-style bubbles color-coded per speaker from a fixed 6-color dark palette (`OmiColors.speakerColors`, indexed by `speakerId % 6`), each with a circular avatar (initial letter or "Y" for the user), a clickable speaker-name label (turns purple + shows a pencil icon once the speaker has been named), inline translation sub-bubbles at 50% color opacity, and a monospace timestamp.

**Where (Mac):** `MainWindow/Components/SpeakerBubbleView.swift`.

**Windows status:** Absent. `TranscriptPopup.tsx` (live recording popup) renders speaker labels as plain inline text (`{l.speaker}:` in `text-white/55`) with no color-coding and no avatar. `pages/LiveConversation.tsx` renders speaker as a neutral pill badge (`rounded-full border border-white/15 bg-white/5 ... text-white/75`) — same neutral treatment for every speaker, no per-speaker color, no avatar, no click-to-rename affordance visible in the reviewed markup.

**Value/notes:** Medium — meaningfully helps multi-speaker transcript scannability on Mac; Windows transcripts read as an undifferentiated list of "Speaker N:" lines.

## Audio level waveform (general-purpose meter)

**What it is (Mac):** A second, distinct waveform component from the PTT bars above — 12 vertical bars whose height responds to a single `level: Float` (square-root-boosted for low-level visibility, center bars up to 40% taller, deterministic per-bar variation via `sin()` instead of `random()` to avoid layout churn) with 4-step color intensity (purple at >0.6, white at >0.2, secondary-gray at >0.02, dim tertiary at rest). Explicitly has no `.animation()` modifier — relies on the 5Hz update cadence being visually smooth enough on its own, to avoid layout-traversal cost.

**Where (Mac):** `MainWindow/Components/AudioLevelWaveformView.swift`.

**Windows status:** Present via the same `overlay/Waveform.tsx` documented above (24-bar, ambient-noise-gated version) — Windows did not build a second, separate "simple level meter" component; one `Waveform` component covers both roles Mac splits across two files.

**Value/notes:** Low — functional coverage exists, just consolidated into one component rather than two. Not a real gap.

## Selectable markdown

**What it is (Mac):** Splits message text into text/code segments, renders text as a single `Text(AttributedString)` per segment (not per-inline-element) specifically so **text selection works across paragraph breaks** — a `.textSelection(.enabled)` gotcha SwiftUI doesn't handle well by default with block-based markdown renderers. Falls back to full `MarkdownUI.Markdown` rendering only when GFM table syntax is detected. Custom preprocessing converts `# headers` to bold and `* list` markers to `•` so they render correctly under `.inlineOnlyPreservingWhitespace` parsing. Caches `AttributedString`s keyed by content + font scale to avoid recomputation on every layout pass.

**Where (Mac):** `MainWindow/Components/SelectableMarkdown.swift`.

**Windows status:** Partial. `components/Markdown.tsx` is a dependency-free regex-based renderer (bold/italic/inline-code/fenced-code/headings/lists/links, deliberately restricting links to `http(s):`/`mailto:` schemes as an XSS/NTLM-leak mitigation — a security-conscious detail Mac's version doesn't need to worry about). It has **no GFM table support** at all (Mac explicitly special-cases tables), and headings render as a generic bold paragraph rather than Mac's distinct sizing per level. Cross-paragraph text selection is not a special concern on Windows since it's rendered as ordinary DOM text — the browser's native selection already spans block elements, so this is arguably a non-issue on this platform rather than a gap (SwiftUI needed the workaround; the DOM doesn't).

**Value/notes:** Medium — table rendering is the one concrete missing capability; the text-selection engineering problem doesn't transfer across platforms.

## Citation cards

**What it is (Mac):** Tappable cards below an AI reply listing its sources — emoji/icon + title + one-line preview + chevron, hover state swaps background from `backgroundSecondary` to `backgroundTertiary`, grouped under a "Sources" header with a quote-icon.

**Where (Mac):** `MainWindow/Components/CitationCardView.swift` (`CitationCardsView` for the list).

**Windows status:** Absent. No citation-rendering component found anywhere in `src/renderer/src/components` (grepped for `citation` — no hits outside Mac).

**Value/notes:** Medium — depends on whether Windows chat currently surfaces citations/sources data at all; if the backend sends them, this is a pure rendering gap.

## Screenshot thumbnail (Rewind grid)

**What it is (Mac):** Grid thumbnail with a hover overlay revealing an app-icon badge (top-left), a delete button (top-right, red circle), and a time label (bottom-right) over a black 30%-scrim; a purple-ring selection state; a purple magnifying-glass badge when the screenshot matches an active search query; and an OCR-extracted-text indicator icon. Supports grouping by app with per-group headers.

**Where (Mac):** `Rewind/UI/ScreenshotThumbnailView.swift` (`ScreenshotGridView` for the grid/group layout).

**Windows status:** Partial. `components/rewind/RewindThumbnailStrip.tsx`'s `Thumb` is a horizontal-filmstrip button (128×64) with lazy-loading via `IntersectionObserver`, an accent-colored border+ring when active, app name + time label below the image — but no hover-delete affordance, no OCR indicator, no search-match badge, and no grid/group-by-app layout (it's a scrolling strip, not a grid). This is a genuinely different layout paradigm (filmstrip vs. grid), not just a missing hover state — worth confirming with the rewind-feature owner whether Windows Rewind has a grid view elsewhere that this audit didn't find.

**Value/notes:** Medium — the delete-on-hover and search/OCR badges are the concrete missing pieces if the filmstrip layout itself is an intentional design choice.

## Per-app icon rendering

**What it is (Mac):** `AppIconView` resolves and caches (via `NSCache`, 100-item/50MB limits) the real macOS application icon for a given app name by searching `/Applications`, `/System/Applications`, running-app bundle URLs, and bundle-ID guesses, falling back to a generic `app.fill` SF Symbol.

**Where (Mac):** `Rewind/UI/AppIconView.swift` (`AppIconCache` actor).

**Windows status:** Absent as a rendered icon. `RewindThumbnailStrip.tsx` shows only `frame.app` as a text string (`{frame.app || 'Unknown app'}`) — no icon image lookup/cache/render found anywhere in the Rewind components reviewed.

**Value/notes:** Low-medium — real app icons make a Rewind filmstrip/grid much faster to visually scan than app-name text alone.

## Interactive timeline bar (Rewind scrubber)

**What it is (Mac):** A hand-drawn `NSView` (not SwiftUI) rendering: a track background, per-frame colored blocks (hue derived from `appName.hashValue`), dashed gap indicators with a formatted duration label when there's a capture gap, a glowing white playhead (2px inset blur halo + solid bar + downward triangle), a hover indicator line, yellow search-result tick marks, and a custom `NSWindow`-hosted tooltip (app icon + name + time) that follows the cursor — built as a raw `NSView` specifically to avoid SwiftUI layout-cycle crashes the code comments describe in detail (`OMI-COMPUTER-1G`/`1J`).

**Where (Mac):** `Rewind/UI/InteractiveTimelineBar.swift`.

**Windows status:** Partial. `components/rewind/RewindTimelineBar.tsx` is a DOM-based fixed-time-scale (140px/hour) scrollable timeline with activity segments (`bg-white/25` blocks), local-time-aligned axis ticks with date/time labels, an accent-colored playhead line, and click-to-seek + wheel-to-pan — solid functional coverage of the "scrub through time" job, and its local-timezone-aware tick alignment is a nice detail Mac's version doesn't obviously have. But it has **no playhead glow**, **no dashed/labeled gap segments** (gaps are implicit in the segment computation, not drawn as distinct dashed+labeled blocks the way Mac does), and **no hover tooltip** showing app/time/thumbnail on scrub.

**Value/notes:** Medium — the core scrubbing interaction is present and arguably better-organized (fixed hour-scale, pannable) on Windows; the missing polish is the glow/tooltip/gap-labeling layer.

## Full-screen timeline player (transport controls)

**What it is (Mac):** A dedicated full-screen frame viewer with video-style playback: a black `ZStack`, a large centered frame image with drop shadow, a bottom gradient scrim (`LinearGradient` → `.black.opacity(0.8)`), an app-colored activity strip above a native `Slider` (`.tint(OmiColors.purplePrimary)`), five SF-Symbol transport buttons (skip-to-start, prev-frame, a circular white play/pause, next-frame, skip-to-end) with disabled-state dimming, a 0.5×–8× playback-speed `Menu` driving a `Timer.scheduledTimer` frame-advance loop, and space/arrow/escape keyboard shortcuts.

**Where (Mac):** `Rewind/UI/RewindTimelinePlayerView.swift` (lines 6–507).

**How it works:** SwiftUI transport buttons + native `Slider` + a `Timer`-driven auto-advance loop; keyboard handling via `.onKeyPress`/key equivalents.

**Windows status:** Absent. `components/rewind/RewindPlayer.tsx` shows a single current frame with a click-to-expand lightbox (`fixed inset-0 z-50 bg-black/90`) — **no play/pause, no step buttons, no speed control, no dedicated transport slider** (seeking happens only via the separate `RewindTimelineBar`/`RewindThumbnailStrip`), and no transport keyboard shortcuts in this file. Windows' "player" is an image-with-metadata pane plus a zoom lightbox, not a scrubber.

**Value/notes:** High — the single largest rewind gap: Mac has an entire dedicated video-scrubber playback UI that Windows has no equivalent of. **Open question (flagged by the timeline sub-audit):** three separate Mac timeline implementations coexist (`InteractiveTimelineBar`, `RewindTimelineView`, and this player's inline slider); verifying which is actually wired into the live Rewind screen (parent container not in the audited set) is a prerequisite to scoping any timeline/player parity work — cross-ref the rewind audit owner.

## Rewind search bar (filters + focus polish)

**What it is (Mac):** A search input plus filter chrome: an animated magnifier tint on focus (`.easeInOut(0.15)`), an inline spinner while searching, a clear (`xmark.circle.fill`) button, a `⌘F` keyboard-shortcut hint chip when idle, an app-filter `Menu` showing the selected app's icon via `AppIconView`, a native `DatePicker`, and Today/Yesterday/This-Week quick-date pill chips with selected-state background swap.

**Where (Mac):** `Rewind/UI/RewindSearchBar.swift` (lines 5–197).

**How it works:** SwiftUI `TextField` + `Menu` + `DatePicker` + pill `Button`s; focus-state color via `.animation(.easeInOut(0.15), value: isSearchFocused)`.

**Windows status:** Absent (all filter chrome). `components/rewind/RewindSearchBar.tsx` (28 lines total) is a plain `<form>` with a single text `<input>` and a "Search" submit `<button>` — no app filter, no date picker, no quick-date chips, no focus-state color animation, no clear button, no `⌘F` hint, no loading spinner.

**Value/notes:** Medium — the filter controls themselves are feature-scope (owned by the rewind audit), but even the pure visual layer (focus transition, magnifier icon, clear button) is entirely absent on Windows.

## Search results filmstrip (Rewind search)

**What it is (Mac):** A horizontally-scrollable thumbnail filmstrip explicitly modeled on Screenpipe's interaction language: on hover, thumbnails scale to 1.15× and lift -16px with a spring (`response:0.3, dampingFraction:0.7`), gain a white glow shadow, and reveal the app name; selected items get a purple ring + glow; a yellow match-count badge with its own glow sits top-right per thumbnail; a capsule progress bar at the bottom shows scroll position within results; keyboard-shortcut hints (←/→) are shown inline.

**Where (Mac):** `Rewind/UI/SearchResultsFilmstrip.swift` (`FilmstripThumbnail`).

**Windows status:** Absent as a filmstrip. `components/rewind/SearchResultsFilmstrip.tsx` is a **plain vertical list** of text rows (`timestamp · app — window title` + match snippet), each a simple hover-background button — no thumbnail images, no hover scale/lift/glow, no match-count badge, no scroll-progress indicator, no keyboard hints. Despite sharing a filename with the Mac component, this is a completely different (and much lower-fidelity) UI pattern: a results list, not a filmstrip.

**Value/notes:** High — of everything in this audit, this is the starkest visual downgrade: same component name, same job (browse search hits), but Mac shows you the screenshots and Windows shows you text.

## Onboarding orbital loading animation

**What it is (Mac):** A circular loading indicator for the file-indexing onboarding step: a breathing center pulse (radial gradient, sine-driven scale), a background track ring, a white progress arc that fills as indexing completes, and 4 independently-speed orbiting glow particles (radial-gradient dots with soft halos) circling the ring.

**Where (Mac):** `FileIndexing/OnboardingLoadingAnimation.swift`. Built with `Canvas` + `TimelineView(.animation)`.

**Windows status:** Present, comparable-to-better. `components/onboarding/OrbitScanner.tsx` is a pure SVG+CSS equivalent: 4 dots at distinct speeds/directions orbiting a shared ring, each dragging a **gradient comet trail** (linear gradient from transparent tail to solid white head) that "paints" the ring as it spins, plus a center dot with a soft halo — same visual idea (multi-speed orbiting particles + center glow), arguably more polished due to the comet-trail rendering, and it explicitly respects the app's global reduce-motion kill-switch (`html[data-reduce-motion='true']`). It doesn't render a literal progress-fill arc the way Mac's does (Mac ties the arc length to real indexing `progress`; Windows' version appears to be indeterminate/decorative only) — worth confirming with the onboarding-feature owner whether Windows needs a progress-driven arc too.

**Value/notes:** This is a genuine parity win worth calling out positively — no action needed beyond possibly wiring real progress into the existing animation if product wants it. One caveat: Mac's arc is progress-driven (communicates real scan %), while `OrbitScanner` is indeterminate and keeps spinning unchanged even after the scan completes (`BuildProfileStep.tsx:58-65` only swaps the text below it) — worth confirming intent with the fileindex-kg/onboarding owner.

## Onboarding step transition (Windows ahead)

**What it is:** The transition style when advancing between full onboarding steps.

**Where (Mac):** The step switch lives in `Onboarding/OnboardingView.swift` (an `if currentStep == N { … } else if …` chain); `OnboardingPagedIntroCoordinator.swift` is a pure state `ObservableObject`, not view code.

**How it works (Mac):** **No cross-fade, slide, page-curl, or parallax between steps at all** — grepping the switch for `.transition(`/`withAnimation`/`matchedGeometryEffect` found none; it's a hard instant cut (the `if/else` swaps the entire `Group` with no animation wrapper). Individual steps carry their own internal micro-transitions for sub-state changes, but the step-to-step swap is unanimated. The `OnboardingStepScaffold` progress capsules fill/highlight per step with no transition modifier either.

**Windows status:** Present / **better at this layer.** `pages/Onboarding.tsx` also instant-swaps `renderStep()`, **but** every step is wrapped by `StepScaffold.tsx`, whose root `<div>` always carries `animate-fade-in` (line 52) → a 0.4s fade + 6px upward slide (`opacity 0→1`, `translateY(6px)→0`, `cubic-bezier(0.22,1,0.36,1)`, per `tailwind.config.ts:65-83`) that replays on every step mount. Its progress dots (`StepScaffold.tsx:58-73`) additionally have `transition-all` on the width/color change — an animated dot transition Mac's scaffold lacks.

**Value/notes:** Flagged so it isn't miscounted as a Windows gap — Windows' per-step "settle-in" fade is a genuine transition Mac's top-level step switch entirely lacks. Neither side does slide/page-curl/parallax between two full pages.

## Onboarding demo-step choreography (floating-bar & voice demos)

**What it is:** The onboarding steps that have the user trigger the real "Ask Omi" bar / push-to-talk and see a canned exchange.

**Where (Mac):** `Onboarding/OnboardingFloatingBarDemoView.swift`, `Onboarding/OnboardingVoiceDemoView.swift`.

**How it works (Mac):** Multi-phase, gated on **real** app state. The floating-bar demo polls the production bar's `showingAIConversation` (`Timer.publish(every: 0.25)`), swaps a keyboard-shortcut keycap row → a static `onboarding_mac_lineup.png` via `.transition(.opacity.combined(with: .move(edge: .bottom)))`, and only reveals "Continue" after `waitForResponse` detects the AI response finished streaming. The voice demo adds a **volume-mute warning card** (with an "I turned it up" recheck button, driven by `SystemAudioMuteController` output-readiness polling) plus a PTT keycap row and "Listening…/Waiting for omi to respond…" status, all with `.transition(.opacity)`. The bar in both is the real production `FloatingControlBarManager`, not a mock.

**Windows status:** Partial — intentionally simplified. `components/onboarding/AskDemoStep.tsx` enables the real overlay, then **unconditionally** reveals a static `macs.png` after one `requestAnimationFrame` via CSS `transition-all duration-500` (translateY-4→0, opacity 0→100) — its own comment says this is deliberately **not** gated on the bar event firing ("so it can never be held hostage to the floating-bar event firing"), and "Continue" is always immediately available (no response-detection poll). `components/onboarding/VoiceIntroStep.tsx` shows a two-state keycap UI driven by real overlay/voice events but with **no transition animation** on the swap and **no volume-mute warning** equivalent.

**Value/notes:** Low — a documented robustness tradeoff (reliability over live-demo fidelity), not an oversight. The reveal animation is a close analog; the missing pieces are the multi-phase "wait for the real AI response" choreography and the volume-readiness warning (the latter is partly feature-scope). Windows' step never actually demonstrates the live floating-bar exchange the way Mac's does.

## Drag-anywhere + resize-handle floating bar

**What it is (Mac):** The floating control bar window can be dragged anywhere on screen (`DraggableAreaView`, an `NSView` capturing `mouseDown`/`mouseDragged` to reposition the `NSWindow`, gated by a `draggableBarEnabled` setting) and resized from its bottom-right corner (`ResizeHandleView`, min 430×250, crosshair cursor, a 3-dot diagonal `ResizeGripShape` visual affordance).

**Where (Mac):** `FloatingControlBar/{DraggableAreaView,ResizeHandleView}.swift`.

**Windows status:** Absent, and architecturally so. `src/main/bar/window.ts` creates the bar `BrowserWindow` with `resizable: false, movable: false` explicitly — the Windows bar is a fixed top-edge dock that only morphs between pill and panel sizes (see Notch morph section above), not a freely-positioned/resizable floating window at all.

**Value/notes:** Medium. This reads as an intentional design divergence (top-edge dock vs. free-floating bar) rather than an oversight, but it is a real capability gap if product wants users to reposition/resize the Windows bar the way Mac allows.

## Click-through window behavior

**What it is (Mac):** `ClickThroughView` wraps an `NSHostingView` subclass that returns `nil` from `hitTest` (so clicks pass through to whatever's behind it) while still tracking "would-be" clicks and replaying them as synthetic mouse events once the window actually becomes key — solving the common macOS bug where the first click on an inactive click-through window just activates the app instead of registering as a real click.

**Where (Mac):** `MainWindow/ClickThroughView.swift`.

**Windows status:** Present, comparable. `src/main/bar/window.ts` uses `win.setIgnoreMouseEvents(true, { forward: true })` (Electron's click-through primitive) by default, flipping to `setIgnoreMouseEvents(false)` when the renderer reports the cursor is over an "interactive island" (`applyClickThrough`/`setInteractive` IPC pair) — the same reactivation-on-hover pattern as Mac's pending-click replay, just built on `mousemove` forwarding instead of a captured/replayed `NSEvent`.

**Value/notes:** No gap — both platforms solved the same "click-through except where it shouldn't be" problem with platform-appropriate primitives.

## Sound-cue feedback

**What it is (Mac):** Two audio files, `focus-lost.aiff`/`focus-regained.aiff`, presumably played as an audible cue when the proactive-focus system detects a state change (consistent with the Glow Border effect's focused/distracted color modes — these are very likely the audio counterpart to that visual).

**Where (Mac):** `Resources/focus-lost.aiff`, `Resources/focus-regained.aiff`.

**Windows status:** Absent. No `.aiff`/`.wav`/`.mp3` files found anywhere under `desktop/windows` (excluding `node_modules`).

**Value/notes:** Low — small feature, but it's paired with the also-Absent Glow Border effect, so if that visual gets built, the audio cue is a natural companion to scope in at the same time.

## Design-system deltas

| Convention | Mac | Windows | Notes |
|---|---|---|---|
| Named color tokens | `OmiColors` enum, ~25 semantic constants | Tailwind `text.*`/`purple.*` + CSS custom properties (`--glass-*`, `--accent`, `--nav-sel`, `--surface`) | Windows' `purple.*` tokens are neutralized to white (good), but `--accent: #5b02e0` is a live raw-purple leak used in 10+ files — see Glow/Color section above. |
| Named radius scale | `OmiChrome` (`windowRadius`…`chipRadius`, 5 steps) | None — ad hoc `rounded-xl`/`2xl`/`3xl` per call site | Minor consistency risk, not urgent. |
| Panel/shadow bundling | `omiPanel`/`omiControlSurface` modifiers (fill+radius+stroke+shadow in one call) | `.glass`/`.glass-subtle`/`.glass-strong` utility classes | Comparable in effect. |
| Typography scale | `scaledFont(size:weight:design:)`, global user-adjustable multiplier | Fixed Tailwind text-size classes, no user scale setting | Accessibility-relevant gap — Absent on Windows. |
| Window vibrancy | `NSVisualEffectView` (true behind-window blur) | CSS `backdrop-filter` (blurs in-page content only); bar window explicitly has none | See Window vibrancy section. |
| Motion/easing | SwiftUI native springs (`spring(response:dampingFraction:)`) throughout; hand-rolled physics for waveform bars | CSS `cubic-bezier` keyframes/transitions; hand-rolled physics for waveform bars only | Comparable expressiveness; Windows has no general spring primitive but doesn't obviously need one given CSS transitions cover the same UI moments. |
| Iconography/branding assets | Rich `Resources/` set: provider logos (flat + regular), hero logo, app icons (.icns), onboarding lineup image, install/permission GIFs, demo MP4s, notch SVG logo | Sparse: `omi-logo.png`, `omilogo.png`, `macs.png`, boilerplate `electron.svg`; no provider logos, no permission/install GIFs, no demo videos | Reflects the Absent agent-pill/provider system and likely a different (in-app, not asset-driven) onboarding walkthrough approach — worth confirming with the onboarding owner rather than assuming it's missing outright. |
| Audio feedback | 2 `.aiff` cues (focus lost/regained) | None found | See Sound-cue section. |
| State-driven iconography | Single static `tray_icon.png` (Resources listing shows no state variants) | **3 tray `.ico` states** (idle/listening/paused) generated by `scripts/gen-tray-icons.mjs` | Windows is ahead here — worth flagging as a pattern Mac could adopt, not a gap to close on Windows. |

## Spotted outside my scope

- The Windows onboarding `BrainGraph.tsx`/`BrainMap.tsx` (WebGL/canvas node-glow visualization, `components/graph/` and `components/onboarding/BrainMap.tsx`) is a substantial, good-looking visual system with pulsing glow halos on nodes — it has no direct Mac equivalent, so it isn't a "gap" in either direction, but it's a strong existing asset the onboarding/fileindex-kg audit owners should know about when comparing onboarding sophistication generally.
- Whether Mac's tray icon has state variants (matching Windows' idle/listening/paused set) wasn't in my file list (`Resources/tray_icon.png` and `omi_menu_bar_icon.png` were the only two listed) — flagging for whoever owns menu-bar/tray behavior on Mac, since Windows appears ahead here.
- The `glow_overlay_enabled` field's presence in `omiApi.generated.ts` with zero renderer consumption suggests either a planned-but-unbuilt Windows setting, or a field that's Mac-only and simply flows through the shared generated types unused — worth a quick check with whoever owns the settings/API-schema surface (likely `app-shell` or `focus-insight` audit owners) rather than treating it as confirmed dead code.
- Citation-card data availability (does Windows chat even receive citation data from the backend?) is a functional question for the chat-agent owner — I only confirmed the rendering component is absent, not whether the underlying data plumbing exists.
- The orb (`components/orb/Orb.tsx`, WebGL2 via `OrbAnimator`/`choreography` presets, self-throttled 30/60/0fps) is a substantial Windows-only visual system with no Mac equivalent at all — out of scope for a Mac→Windows gap list, but the app-shell/floating-bar audit owners should know it exists as Windows' primary state-indicator (idle/listening/speaking/thinking), roughly filling the role Mac splits across the pulsing dot / waveform bars / provider logo marks.
