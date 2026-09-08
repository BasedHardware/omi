# Mac→Windows Parity Audit — UI Components & Visual Layer

> **Re-audit stamp: 2026-08-22.** This file replaces the 2026-08-20 version in place.
> The original pass is materially stale: several "Absent, High value" findings were
> already-shipped features by the time the audit was written (some for over a month),
> and its headline finding (a raw purple `--accent` leak) had already been fixed.
> Every claim below was re-verified against current source — file reads, symbol
> greps, and `git log` dates — not carried over from the old file. See the callout
> section immediately below for what changed and why.
>
> Scope: reusable visual components, design tokens, animations/effects, iconography,
> and interaction micro-patterns — not the features behind them (those are audited by
> other agents). Windows baseline checked: `src/renderer/src/components/**`,
> `src/renderer/src/styles/globals.css`, `tailwind.config.ts`, `src/renderer/src/lib/macPalette.ts`,
> `src/main/bar/window.ts`, `src/main/glow/**`, `resources/`, `src/renderer/src/assets/`,
> plus `docs/mac-parity-audit/TRACK4-PLAN.md` (the binding UI ruling that governs the
> purple exception). Every Mac file cited in the original pass is treated as a
> hypothesis, not ground truth, per this re-audit's brief — the Mac side was not
> re-read from scratch, but nothing here depends on a Mac citation that looked
> inconsistent with how wrong the Windows side turned out to be.

## Changed since the 2026-08-20 audit

The single biggest problem with the old file is that it audited a Windows codebase
that no longer exists: a large "Track 4 / Hub / fonts+primitives" wave landed
**2026-07-10 → 2026-07-25** — three to six weeks *before* the audit was written on
2026-08-20 — and rebuilt or added most of the components this file covers. The old
audit called several of these "Absent" or "much weaker" when they had already
shipped, faithfully, weeks earlier. That is exactly the "described code that had
existed for weeks already" failure mode this re-audit was commissioned to find, and
it recurred far more than once in this file specifically.

| # | Item | Old finding | Corrected finding |
|---|---|---|---|
| 1 | `--accent` raw-purple leak | "single most concrete, actionable finding" — live INV-UI-1 violation | **Already fixed.** `globals.css:62` — `--accent: #ffffff`, with an explicit "never purple" comment. Confirmed pre-existing per this re-audit's brief. |
| 2 | Purple tokens generally | Framed as an unauthorized/accidental leak risk | Purple is now a **deliberately governed, documented exception** — "Track 4 ruling" (Chris, 2026-07-14, `TRACK4-PLAN.md`) — contained to `lib/macPalette.ts` and a handful of cited call sites, explicitly exempt from the (Windows-blind) `check_brand_ui.py` ratchet. Not a compliance risk; a scoped design decision. |
| 3 | Glow border/edge/overlay | "Absent... zero Windows presence, not even a stub" (H) | **Present.** A full click-through focus-halo window subsystem (`main/glow/*`, `components/glow/GlowWindow.tsx`, route `/glow`) shipped 2026-07-14 → 2026-07-19, with the same green(focused)/red(distracted) hue mapping as Mac. |
| 4 | Goal celebration | "Present-but-much-weaker (plain success toast)" (H) | **Present, faithful.** `GoalCelebration.tsx` (shipped 2026-07-15) is a real 4-phase dim→confetti→gradient-text→fade-out port, wired into `Goals.tsx` in place of the old toast. |
| 5 | Agent provider pill system | "Absent" (H) | **Present** for the status/tint half (`bar/agentPills.ts`, `AgentPillView.tsx`, shipped 2026-07-19) — queued/starting/running/done/stopped/failed, matching Mac's vocabulary. The provider-*logo* half (Hermes/OpenClaw mark tinted per pill) is still absent from the pill itself, though the logo assets now exist elsewhere in the app. |
| 6 | Chat sessions sidebar | "Absent — single-thread architecture, no session concept" (H) | **Present** (as a popover, not a sidebar). `ChatHistoryPopover.tsx` + `HistorySessionRow.tsx` + `useChatSessions` (shipped 2026-07-15/16): date-grouped list, starred filter, search, new-chat, inline rename, delete-with-confirm. |
| 7 | Agent spawn/completion cards (part of "Chat bubble system") | "Absent" (H, bundled into the largest gap in the audit) | **Present.** `AgentThreadCard.tsx` (shipped 2026-07-19) renders spawn/completion cards in the shared thread. |
| 8 | User-adjustable font scale | "Absent... no fontScale-equivalent setting found" (M) | **Present.** `lib/fontScale.ts` + Settings "Font Size" card (shipped 2026-07-14): `Ctrl+=`/`Ctrl+-`/`Ctrl+0`, a 0.5–2.0 slider, persisted preference, applied as a root rem multiplier — the same mechanism Mac uses. |
| 9 | Speaker color-coded transcript bubbles | "Absent" (M) | **Partial**, not absent. `TranscriptDrawer.tsx` + `lib/conversations/speakers.ts` (shipped 2026-07-14) fully port Mac's per-speaker color, avatar, and 50%-opacity translation sub-bubble logic for **saved conversations**. The **live** recording popup/page still renders plain text — old finding stands there only. |
| 10 | Search results filmstrip (Rewind) | "Absent as a filmstrip... starkest visual downgrade... Mac shows screenshots, Windows shows text" (H) | **No longer text-only.** `SearchResultsFilmstrip.tsx` was rewritten 2026-07-14 into a grouped results list with real lazy-loaded thumbnails, a semantic-match badge, and highlighted snippets. Still a vertical list (not a horizontally-scrolling hover-lift filmstrip), but the "shows you text, not screenshots" framing is no longer true. |
| 11 | Rewind search bar | Cited `RewindSearchBar.tsx` (28 lines, bare input) as the live search UI | That file is now **dead code** — nothing imports it. The live search bar is inline in `pages/Rewind.tsx`: debounced (300ms, matches Mac), `Ctrl/Cmd+F` focus + `Escape` back-out, a clear button, and a real graphical month-grid date picker (`RewindDatePicker.tsx`). Still no app-filter menu or quick-date chips. |
| 12 | Full-screen timeline player transport | "Absent — no play/pause, no step, no speed" (H) | **Partial**, not absent. `pages/Rewind.tsx` now has a page-level Play/Pause toggle driving frame-by-frame auto-advance. Step/skip-to-start-end/speed-menu are still absent from `RewindPlayer.tsx` itself. |
| 13 | PTT voice waveform bars | Cited `components/overlay/Waveform.tsx` (24-bar DOM component) | That component **no longer exists**. A 2026-07-11 design pivot moved the voice-level visualization into the WebGL orb (`orb/waveform.ts`) as a shader-rendered amplitude-history row. The citation is stale, not the capability — see the updated section below. |
| 14 | Typing indicator | "Absent (literal `…` text)" (M) | **Partial**, not literally absent. The floating-bar overlay now shows an animated 8-dot ring (`OmiThinkingSpinner.tsx`, shipped 2026-07-16) explicitly modeled on Mac's `OmiThinkingMark`. The **default** main-window surface (Home Hub) still falls through to the literal `'…'` string in the same shared component; an optional legacy Home page has its own separate 3-dot bounce. |
| 15 | Citation cards | "depends on whether Windows chat currently surfaces citations... functional question for the chat-agent owner" | **Resolved, partially.** `useChat.ts`/`messagesSse.ts` do carry a `citations` array (id/title/emoji) end to end — the data plumbing exists. No rendering component consumes it; the gap is now confirmed pure-rendering, not data-availability. |
| 16 | Window vibrancy / material | "Absent" for the app generally | Narrowed: still true for the **floating bar** (unchanged, see below), but the **main window** now paints a real Mica tint (`App.tsx` `useMicaChrome`, `data-mica` in `globals.css`) — a genuine, if different, Windows-native vibrancy answer the old audit didn't have. |

Everything else in the table below was re-checked and, unless flagged above, is
substantially unchanged from 2026-08-20 — those sections keep the old finding but
with corrected/current citations.

## Summary table

| Component / effect | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Semantic color palette (`OmiColors`) | `Theme/OmiColors.swift` | Present, governed — neutral by default, purple ported only via a contained, documented exception (`lib/macPalette.ts`) | H |
| Chrome/panel system (`OmiChrome`, `omiPanel`/`omiControlSurface`) | `Theme/OmiChrome.swift` | Partial — named radius scale now exists (`--radius-*` / `tailwind.config.ts` `borderRadius`), `.glass*` utilities cover fill+blur+shadow bundling | M |
| User-adjustable font scale | `Theme/OmiFont.swift` | **Present** — `lib/fontScale.ts`, Settings → General → Font Size | M |
| Window vibrancy/material (bar) | `FloatingControlBar/FloatingBackgroundModifier.swift` | Absent for the bar (explicitly, by design); main window gets Mica instead | M |
| Glow border/edge/overlay focus effect | `ProactiveAssistants/UI/Glow{Border,Edge,Overlay}*.swift` | **Present** — `main/glow/*` + `components/glow/GlowWindow.tsx` | H |
| Goal celebration (confetti + dim + gradient text) | `MainWindow/Components/GoalCelebrationView.swift` | **Present**, faithful port | H → parity |
| Floating-bar notch morph | `FloatingControlBar/FloatingBarNotchTransition.swift` | Present, different technique, comparable fidelity (now asymmetric open/close timing) | M |
| PTT voice waveform bars | `FloatingControlBar/VoiceWaveformBars.swift` | Present — moved into the WebGL orb (`orb/waveform.ts`), not a standalone DOM component | M |
| Agent provider logo mark + status-tinted pill system | `FloatingControlBar/AgentProviderLogoMark.swift`, `AgentPill.swift` | Partial — status/tint pill system Present (`bar/agentPills.ts`, `AgentPillView.tsx`); per-provider logo mark on the pill itself Absent | M (was H) |
| Chat bubble system (tool cards, thinking block, discovery/agent cards, rating/copy) | `MainWindow/Components/ChatBubble.swift` | Partial — agent spawn/completion cards and a copy button now Present; tool-call cards, thinking block, discovery card, rating buttons, info popover still Absent | H |
| Chat sessions (multiple conversation threads) | `MainWindow/Components/ChatSessionsSidebar.swift` | **Present**, as a popover not a sidebar (`ChatHistoryPopover.tsx`) | — (parity, different chrome) |
| Typing indicator | `Chat/TypingIndicator.swift` | Partial — animated 8-dot ring on the bar overlay; literal `'…'` still on the default main-window surface | M |
| Speaker color-coded bubbles | `MainWindow/Components/SpeakerBubbleView.swift` | Partial — full port for saved-conversation transcripts (`TranscriptDrawer.tsx`); live transcript surfaces still plain text | M |
| Audio level waveform (general meter) | `MainWindow/Components/AudioLevelWaveformView.swift` | Present via the orb's shared waveform renderer | L |
| Selectable markdown (cross-paragraph selection, GFM tables) | `MainWindow/Components/SelectableMarkdown.swift` | Partial — still no GFM tables, no distinct heading sizing | M |
| Citation cards | `MainWindow/Components/CitationCardView.swift` | Absent (rendering only — the data now confirmed present) | M |
| Screenshot thumbnail (Rewind grid) | `Rewind/UI/ScreenshotThumbnailView.swift` | Partial — filmstrip only, no delete/OCR badge/grid-by-app, unchanged | M |
| Per-app icon rendering | `Rewind/UI/AppIconView.swift` | Absent (text label only), unchanged | L |
| Interactive timeline bar (glow, gap dashes, tooltip) | `Rewind/UI/InteractiveTimelineBar.swift` | Partial — DOM scrubber, no glow/tooltip/gap-dash, unchanged | M |
| Full-screen timeline player (transport controls) | `Rewind/UI/RewindTimelinePlayerView.swift` | Partial (was Absent) — page-level play/pause now exists; no step/skip/speed | H → M |
| Rewind search bar (filters + focus polish) | `Rewind/UI/RewindSearchBar.swift` | Partial (was Absent) — debounce, `⌘F`/Esc, clear button, real date picker now exist; no app filter, no quick-date chips | M |
| Search results filmstrip (Rewind search) | `Rewind/UI/SearchResultsFilmstrip.swift` | Partial (was Absent) — real thumbnails + semantic badge + highlighted snippets now render; still a list, not a hover-lift filmstrip | M (was H) |
| Onboarding orbital loading animation | `FileIndexing/OnboardingLoadingAnimation.swift` | Present, comparable-to-better, unchanged (still indeterminate, not progress-driven) | — (parity) |
| Onboarding step transition | `Onboarding/OnboardingView.swift` (hard cut) | **Windows ahead**, unchanged — `animate-fade-in` per step mount | — (Windows ahead) |
| Onboarding demo-step choreography | `Onboarding/OnboardingFloatingBarDemoView.swift`, `OnboardingVoiceDemoView.swift` | Partial, unchanged — reveal animation present, gating intentionally simplified, no volume-mute warning | L |
| Drag-anywhere + resize-handle floating bar | `FloatingControlBar/{DraggableAreaView,ResizeHandleView}.swift` | Absent, unchanged — bar `BrowserWindow` is still `resizable: false, movable: false` | M |
| Click-through window behavior | `MainWindow/ClickThroughView.swift` | Present, comparable, unchanged | — (parity) |
| Sound-cue feedback (focus lost/regained) | `Resources/focus-{lost,regained}.aiff` | Absent, unchanged — no audio-cue files anywhere under `desktop/windows` | L |
| Provider/branding logo assets | `Resources/{hermes,openclaw}_logo*.png`, onboarding lineup | Partial (was "mostly absent") — Hermes/OpenClaw/Gemini/Calendar/Gmail/Obsidian logos now exist for the Connections panel; still none feed the agent-pill identity mark | L |
| State-driven tray icon | `Resources/tray_icon.png` (static) | **Windows ahead**, unchanged — idle/listening/paused `.ico` set | — (Windows ahead) |

## Design system tokens

**What it is (Mac):** `OmiColors` (`Theme/OmiColors.swift`) is a single enum of ~25
named `Color` constants: 5-step background scale, a 4-color purple accent family, a
4-step text hierarchy, status colors, a 6-color speaker palette, a `userBubble`
color, and two purple gradients. `OmiChrome.swift` defines a named radius scale
(`windowRadius`…`chipRadius`) plus `omiPanel`/`omiControlSurface` view modifiers.
`OmiFont.swift` adds a user-adjustable global font-scale setting.

**Where (Mac):** `desktop/macos/Desktop/Sources/Theme/{OmiColors,OmiChrome,OmiFont}.swift`.

**Windows status — re-verified 2026-08-22, and substantially rebuilt since the last audit:**

- **Neutral palette, present.** `globals.css:38–76` ports the background ramp, text
  hierarchy, hairlines, status colors, and radius scale as CSS custom properties;
  `tailwind.config.ts:8–34` mirrors them as Tailwind tokens (`bg.*`, `text.*`,
  `line.*`, `success`/`warning`/`error`/`info`). `--accent: #ffffff` /
  `--accent-contrast: #0f0f0f` at `globals.css:62–63`, with an explicit "never
  purple (INV-UI-1)" comment. **This is the item the previous audit flagged as its
  headline finding (a raw `#5b02e0` leak) — already fixed at the time this re-audit
  started; confirmed still fixed.**
- **Purple, present but governed — not a leak.** `tailwind.config.ts:36–41` still
  defines a `purple.{primary,secondary,accent,light}` family (`#8b5cf6` etc.) and
  `globals.css:124–138` defines matching `--purple-*`/`--user-bubble`/`--speaker-*`
  custom properties, but per `lib/macPalette.ts:1–24` these are **not exposed as a
  general-purpose design token** — the module's own header explains that Track 5
  removed the app-wide `purple.*` *usage* and set `--accent` to white, and that the
  hex values that remain are "the one sanctioned exception": a binding ruling
  (`docs/mac-parity-audit/TRACK4-PLAN.md`, "Chris's binding Track 4 ruling," dated
  2026-07-14) that Mac's palette "ports as-is" specifically where Mac itself renders
  purple (the Rewind search-highlight box, the selected chat-history row, the
  transcript speaker/user-bubble colors, and one documented AI-accent icon color in
  `LiveNotesPanel.tsx:14–19`). Each consumer imports the color from `macPalette.ts`
  rather than re-declaring a hex or promoting one to a global var, and the module
  explicitly notes it is outside the (Mac/`app/lib`/`web`-only) `check_brand_ui.py`
  ratchet. This reframes the entire "live INV-UI-1 violation risk" angle of the old
  audit: purple on Windows is now a scoped, cited, intentional design decision, not
  an accidental leak.
- **Radius/shadow system: Partial**, improved from the last audit. `globals.css:63–68`
  now names a `--radius-{window,card,section,control,chip}` scale mirroring
  `OmiChrome` exactly (`tailwind.config.ts:44–50` exposes it as `rounded-window`
  etc.), though most call sites in older components still use ad hoc `rounded-xl`/
  `2xl`/`3xl` rather than the named scale — a partial, not full, adoption.
- **Font scale: Present.** `lib/fontScale.ts` (added 2026-07-14) is a real port of
  `FontScaleSettings`: a `[0.5, 2.0]` clamp, `Ctrl+=`/`Ctrl+-`/`Ctrl+0` global
  shortcuts, a persisted `fontScale` preference (`lib/preferences.ts:18–26,119–123`),
  applied as a root `rem` multiplier on startup (`main.tsx:40,67`) and live-reapplied
  on change. A Settings → General "Font Size" slider (`FontSizeCard.tsx`) drives the
  same preference. This directly reverses the old audit's "Absent" finding.

**Value/notes:** The previous audit's framing — "a raw hex bypasses the neutralization
safeguard" — was already wrong when written (the raw hex was gone) and is doubly
wrong now that the remaining purple is a cited, contained, product-approved
exception rather than an oversight. The two genuine remaining gaps here are cosmetic
and small: partial (not full) adoption of the named radius scale, and the fact that
several purple call sites (e.g. `RewindDatePicker.tsx`, `LiveNotesPanel.tsx`) are
each individually commented as sanctioned rather than drawing from one shared
"purple-allowed" registry — acceptable per the module's own design, not a defect.

## Window vibrancy / material

**What it is (Mac):** `FloatingBackgroundModifier` wraps `NSVisualEffectView`
(`.hudWindow` material, `.behindWindow` blending) for genuine OS-level
behind-window blur on the floating bar, with a `solidBackground` fallback setting.

**Where (Mac):** `FloatingControlBar/FloatingBackgroundModifier.swift`.

**Windows status:** Unchanged for the bar — `components/bar/bar.css:1–3` still
states outright that "the top-edge bar window is TRANSPARENT (no DWM material) —
the page paints everything," and `main/bar/window.ts:9,15,106,221,658` confirms the
bar is transparent with no DWM material, using CSS `backdrop-filter` blur on the
bar's own painted surface instead of true behind-window vibrancy. **New since the
last audit:** the *main* application window now applies a genuine Windows-native
material — `App.tsx:172–203` (`useMicaChrome`) stamps `data-mica="true"` on the root
when the OS grants a Mica backdrop, and `globals.css`'s `html[data-mica='true']`
rule swaps the canvas to a translucent `rgba(15,15,15,0.82)` fill so the desktop
tint reads through. This doesn't change the bar finding (which is deliberate and
explicitly documented as such) but it does mean "Windows has no vibrancy story" is
no longer an accurate summary of the app as a whole.

**Value/notes:** Medium, unchanged for the bar specifically — the bar gap is real
and by design, not an oversight; `backdrop-filter` remains a reasonable analog for
panels but not for a window sitting over the whole desktop.

## Glow border / edge / overlay (ambient focus-state effect)

**What it is (Mac):** A full-screen ambient glow around the user's active window
signaling focus state — green/cyan when focused, red/orange when distracted —
rendered via blurred mesh/angular gradients in transparent, click-through, always-
on-top `NSWindow`s positioned around (not over) the target window.

**Where (Mac):** `ProactiveAssistants/UI/GlowBorderView.swift`, `GlowEdgeWindow.swift`,
`GlowOverlayWindow.swift`.

**Windows status: Present.** This is the single largest correction in this file. The
old audit called this "Absent... zero Windows presence, not even a stub" — but a
complete, working halo subsystem shipped **2026-07-14 through 2026-07-19**, a full
month before that audit was written:

- `src/main/glow/glowWindow.ts` creates a dedicated `BrowserWindow` (`frame: false`,
  `transparent: true`, `resizable: false`, `movable: false`, `skipTaskbar: true`,
  `focusable: false`, `hasShadow: false`), sets `setAlwaysOnTop(true, 'screen-saver')`,
  and calls `setIgnoreMouseEvents(true)` with **no** `{ forward: true }` — fully
  click-through, by design, since (unlike the bar) the halo has no interactive
  regions (`glowWindow.ts:80–111`).
- `src/main/glow/glowPresets.ts:21–32` defines exactly the Mac hue mapping: `distracted`
  is red (`'239 68 68' / '248 113 113' / '220 38 38'`), `focused` is green
  (`'34 197 94' / '74 222 128' / '16 185 129'`), both at the same 0.85 intensity —
  with an explicit comment that this faintness is an approved, deliberately-fixed
  value that should not be tuned back up.
- `src/renderer/src/components/glow/GlowWindow.tsx` renders three stacked rings
  whose only difference is hue, driven by a `runId`-keyed remount so a superseding
  glow always restarts its envelope from zero, with a double-`requestAnimationFrame`
  paint-ack handshake to main before it reveals (avoiding a flash of the previous
  run's frame at the new position).
- The route is wired in `App.tsx:23,49` (`import { GlowWindow }` / `<Route path="/glow" .../>`),
  ungated like the capture window since it "paints geometry main hands it and holds
  no user data."

**Value/notes:** No further gap-closing action needed for this to count as present;
remaining differences (Mac uses `MeshGradient`/`AngularGradient` + real window-frame
edge-following vs. Windows' CSS box-shadow ring) are implementation detail, not a
capability gap. One open question this re-audit did **not** resolve: the
`glow_overlay_enabled` field in `omiApi.generated.ts` is still never read by the
renderer even though the feature itself now works — either the Windows halo is
unconditionally on (gated some other way this audit didn't find) or that specific
settings field is Mac-only; worth a quick check with the settings/API owner, but it
no longer implies the feature is unbuilt.

## Goal celebration (confetti burst)

**What it is (Mac):** A fullscreen celebration on `.goalCompleted`: dim scrim → 40-
particle confetti burst (9-color palette incl. two purple shades) → gradient
"Goal Completed!" text → fade out, over ~3.5s.

**Where (Mac):** `MainWindow/Components/GoalCelebrationView.swift`.

**Windows status: Present, faithful port.** The old audit's "present-but-much-
weaker (plain success toast)" finding is superseded — `components/goals/GoalCelebration.tsx`
(added 2026-07-15) is now wired into `pages/Goals.tsx` in place of the old
`toast('Goal complete 🎉', …)` call. It matches Mac's choreography closely:
40-particle burst (`makeParticles`, `GoalCelebration.tsx:29–58`) with the same
random-angle/distance/rotation model, a black dim scrim (0.4 → 0.5 → 0 opacity),
a yellow→orange→yellow gradient-text "Goal Completed!" with a drop-shadow glow, and
a phased timer (`CELEBRATION_TIMINGS`: confetti at 300ms, text at 800ms, fade-out at
3000ms, done at 3500ms — `GoalCelebration.tsx:13–18`) that lines up with Mac's own
~3.5s sequence. Per INV-UI-1, the file's own header notes Mac's 9-color palette
included 2 purple particles, both swapped for white here — a correct, intentional
divergence, not a gap. A `motion-reduce:hidden` guard drops the confetti burst under
`prefers-reduced-motion` while keeping the dim + text.

**Value/notes:** No longer a gap. The only residual difference from Mac is the
implementation technique (CSS transitions/tweens vs. Mac's live physics springs),
which the component's own comment calls out as a deliberate "keep the choreography,
optimize the impl" tradeoff.

## Floating-bar notch morph

**What it is (Mac):** The floating bar grows from a small notch sliver into its
full shape via eased `NSWindow` frame animation.

**Where (Mac):** `FloatingControlBar/FloatingBarNotchTransition.swift`.

**Windows status:** Present, unchanged in design, refined in timing.
`components/bar/bar.css` still interpolates `width`/`height`/`border-radius` via CSS
transition on one morphing surface ("ONE element interpolating pill ⇄ panel," per
its own comment) — but the timing is no longer the single 260ms figure the old
audit cited. It is now asymmetric: opening transitions run 170ms and closing
transitions run 240ms (`bar.css:70–83`), landing from a 2026-07-19 "motion parity —
bar morph asymmetry" pass that deliberately makes open feel snappier than close.
Same design intent as Mac (one shape growing/shrinking, not a crossfade); the
specific numbers just moved.

**Value/notes:** No action needed — still one of the better-matched pairs.

## PTT voice waveform bars / general audio-level meter

**What it is (Mac):** Two related components — `VoiceWaveformBars.swift` (5 spring-
physics bars in the floating bar, purple-gradient fill, auto-gain) and
`AudioLevelWaveformView.swift` (a separate 12-bar general-purpose level meter).

**Where (Mac):** `FloatingControlBar/VoiceWaveformBars.swift`,
`MainWindow/Components/AudioLevelWaveformView.swift`.

**Windows status:** Present, but the old audit's citation (`components/overlay/Waveform.tsx`,
a standalone 24-bar DOM component with an adaptive noise gate) is stale — that file
no longer exists in the tree. A 2026-07-11 design pivot ("Chris 2026-07-11... the
live scrolling look was approved by the user 2026-07-11," per its own header)
replaced the standalone waveform with a shader-rendered amplitude-history row
integrated directly into the WebGL orb: `src/renderer/src/orb/waveform.ts` computes
a scrolling row of rounded-capsule bars (silence renders as a small dot; new samples
enter at the right and the history slides left) as a pure function consumed by the
orb's shader (`u_wave[]`), capped at `WAVE_MAX_SLOTS = 40`. Color is neutral
(matching the orb's overall palette), not purple. This still covers both of Mac's
roles (PTT bars + general level meter) in one place, same as the old audit noted for
the superseded component — the capability is unchanged, only the implementation
and file location moved.

**Value/notes:** No real gap — re-verify the specific noise-gate/auto-gain
sophistication claim if a future audit needs it, since that logic may have moved or
changed shape along with the file; this pass did not re-derive it from the new
shader code in comparable depth to the old audit's DOM-component read.

## Agent provider logo mark + status-tinted pill system

**What it is (Mac):** Floating-bar pills, one per background agent run, each
showing a status-tinted provider identity mark (Hermes/OpenClaw logo, tinted
queued=cyan/running=amber/done=green/stopped=gray/failed=red).

**Where (Mac):** `FloatingControlBar/AgentProviderLogoMark.swift`, `AgentPill.swift`.

**Windows status: Partial** (was "Absent"). The status/tint half of this system now
exists: `src/renderer/src/components/bar/agentPills.ts` defines the exact same two-
tier status vocabulary as Mac — a kernel wire status (`idle`/`queued`/`starting`/
`running`/`waiting_input`/`waiting_approval`/`cancelling`/`succeeded`/`completed`/
`failed`/`cancelled`/`timed_out`/`orphaned`) collapsed to a coarse display status
(`queued`/`starting`/`running`/`done`/`stopped`/`failed`) with a neutral tint token
per status — its own header cites this as "a faithful port of the macOS
AgentPillsManager mechanism." `AgentPillView.tsx` (shipped 2026-07-19, B2/B3) renders
the pill's own chip and a dedicated per-pill transcript view (a click on a spawned
pill lands on that run's own synthesized transcript, not the shared thread — the
same separation Mac's `AgentMainChatView` makes). What is still absent is the
*identity* half: `AgentPillView.tsx` shows a generic `Bot` icon, not a
Hermes/OpenClaw logo mark tinted per status — there is no
`AgentProviderLogoMark`-equivalent wired into the pill. Provider logo *assets*
(`assets/brands/{hermes,openclaw}_logo.png`) do now exist in the codebase, but they
feed `ConnectorBrandMark.tsx` in the Connections settings panel, not the bar pill.

**Value/notes:** Medium (down from High) — the harder, more architecturally
significant half (status modeling + per-run transcript UI) is done; what remains is
a smaller visual-polish gap (swap the generic bot icon for the tinted provider mark
the assets already support).

## Chat bubble system (tool cards, thinking block, discovery/agent cards)

**What it is (Mac):** `ChatBubble.swift` — avatars, sender-colored bubbles, a full
tool-call visualization system (`ToolCallsGroup`/`ToolCallCard` with per-status
icons and a stalled banner), a collapsible `ThinkingBlock`, a `DiscoveryCard`,
`AgentSpawnCard`/`AgentCompletionCard`, rating buttons, a copy button, an info
popover, and citation cards.

**Where (Mac):** `MainWindow/Components/ChatBubble.swift`.

**Windows status: Partial**, with one real addition since the last audit.
`components/chat/ChatMessages.tsx` still covers the baseline (asymmetric bubble
corners, `bubble-in` entrance, character-reveal streaming via `RevealMarkdown`) and
now also renders **agent spawn/completion cards**: `AgentThreadCard.tsx` (shipped
2026-07-19) renders a `Bot` icon + title + running/done/stopped/failed chip for
`agentSpawn`/`agentCompletion` message blocks, checked before the streaming/copy
logic so a card never shows a stray placeholder or copy button
(`ChatMessages.tsx:103–120`). A hover-revealed **copy button**
(`CopyMessageButton`, `ChatMessages.tsx:34–79`) is also present, with its own
per-bubble "copied" tick — something the old audit didn't credit Windows with at
all. Still genuinely absent: tool-call cards/status icons, the collapsible thinking
block, the discovery card, rating buttons (thumbs up/down), the info popover for
response metadata, and citation cards (confirmed absent as a *rendering* component
— see the dedicated Citation cards section below for the data-plumbing nuance).
Avatars remain absent from the shared `ChatMessages` component that the default
Home experience (`HubChatPanel.tsx`) uses; the optional legacy Home page
(`pages/LegacyHome.tsx`, reachable via a `useLegacyHomeDesign` preference, off by
default) renders its own Omi-mark avatar circle for assistant turns, so avatar
coverage is inconsistent across Windows' two Home implementations rather than
uniformly absent.

**Value/notes:** Still the largest single component gap in the audit by remaining
surface area, but smaller than the old audit stated — the agent-card slice (which
the old audit explicitly said was "downstream of the Absent agent-pill system") is
now built, alongside a copy button neither version of the old audit's summary table
credited.

## Chat sessions (multiple conversation threads)

**What it is (Mac):** A fixed sidebar listing chat sessions grouped by date, with
new-chat, starred filter, live search, and per-session rename/star/delete.

**Where (Mac):** `MainWindow/Components/ChatSessionsSidebar.swift`.

**Windows status: Present** (was "Absent — no session concept in the data layer at
all"). This reverses the old audit's core claim. `hooks/useChatSessions.ts` (shipped
2026-07-15) is a full sessions data layer, and `components/chat/ChatHistoryPopover.tsx`
+ `HistorySessionRow.tsx` (shipped 2026-07-15/16, wired into the default Home
experience via `HubChatHeader.tsx`) render it: a header with a starred-filter toggle
and "new chat" button, a live search field, and a date-grouped list
(`ChatHistoryPopover.tsx:107–125`). Each row (`HistorySessionRow.tsx`) supports
double-click-to-rename with Enter/Escape, a star toggle, and a hover-revealed
delete that arms an inline check/cancel confirm rather than deleting immediately
(`HistorySessionRow.tsx:126–156`) — a reasonable Windows-native analog of Mac's
delete confirmation alert. The one real structural difference from Mac: this is a
**popover** anchored off the chat header, not a persistent 220pt sidebar — a
deliberate chrome choice, not a missing capability.

**Value/notes:** No longer an architectural gap. If product specifically wants an
always-visible sidebar rather than an on-demand popover, that's a chrome preference
to raise separately — the session data model, search, starring, rename, and delete
this audit previously called "net-new" all already exist.

## Typing indicator

**What it is (Mac):** `OmiThinkingMark` — 8 dots in a ring, opacity-trailed,
continuously rotating, rendered in a pill.

**Where (Mac):** `Chat/TypingIndicator.swift`.

**Windows status: Partial** (was "Absent... literal `…` string"). The floating-bar
overlay chat now shows a genuine animated indicator:
`components/chat/OmiThinkingSpinner.tsx` (shipped 2026-07-16) draws exactly an
8-dot ring on a radius-6.6 circle with opacity ramping 1.0→0.2 head-to-tail, spun at
0.4s/rev via the `.omi-thinking-spin` keyframe (`globals.css:627–633`) — explicitly
modeled on Mac's mark, per its own header comment, and shown standalone (not inside
a bubble) so the real reply pops in cleanly once it streams. However, this only
fires for the **overlay** variant (`ChatMessages.tsx:126–128`, gated on
`variant === 'overlay'`); the **default main-window** surface (`HubChatPanel.tsx`,
which renders `ChatMessages` with `variant="main"`) still falls through to the
literal `'…'` string (`ChatMessages.tsx:139–140`) for exactly the case the old audit
described. The optional legacy Home page has yet a third, different treatment — a
CSS 3-dot bounce (`.typing-dots`, `globals.css:583–605`), which is more polished
than plain text but not the same 8-dot ring.

**Value/notes:** Medium, unchanged from the old audit's rating — the component that
matters most for a first-time impression (the default Home chat surface) still
shows unstyled text; the ring exists but is scoped to the bar.

## Speaker color-coded transcript bubbles

**What it is (Mac):** Live/saved transcript segments render as color-coded bubbles
by speaker (6-color dark palette, indexed `speakerId % 6`), with avatars, a
clickable rename affordance, and inline translation sub-bubbles at 50% opacity.

**Where (Mac):** `MainWindow/Components/SpeakerBubbleView.swift`.

**Windows status: Partial** (was "Absent"). `lib/macPalette.ts` now defines the
exact Mac constants (`SPEAKER_COLORS` 6-tone array, `USER_BUBBLE`, `AVATAR_USER`,
`AVATAR_PERSON`, `AVATAR_UNNAMED`) in one contained module, and
`lib/conversations/speakers.ts` ports the presentation logic 1:1 (`bubbleColor`,
`avatarInitial`, `avatarFill`, `speakerLabel` — `speakers.ts:38–64`). This is fully
wired into `components/conversations/TranscriptDrawer.tsx` (shipped 2026-07-14),
which renders per-speaker colored bubble fills, 32px avatar circles, and a
translation sub-bubble at the speaker color's 50% opacity
(`TranscriptDrawer.tsx:41–65`) — for **saved conversations** viewed via
`ConversationDetail.tsx`. The **live** surfaces the old audit cited are unchanged:
`components/TranscriptPopup.tsx:51` still renders `{l.speaker}: ` as plain
`text-white/55`, and `pages/LiveConversation.tsx:105` still renders speaker as a
neutral, undifferentiated pill.

**Value/notes:** Medium, same value as before but the finding is now "half-shipped"
rather than "absent" — the exact color/avatar system Mac uses is built and correct,
just not yet applied to the two live-recording surfaces.

## Audio level waveform (general-purpose meter)

**What it is (Mac):** A second, distinct 12-bar level-meter component from the PTT
bars, used elsewhere in the app.

**Where (Mac):** `MainWindow/Components/AudioLevelWaveformView.swift`.

**Windows status:** Present via the same orb waveform renderer documented above —
Windows still consolidates both of Mac's roles into one component/module rather than
building two, per the prior audit's finding. The specific component name
(`overlay/Waveform.tsx`) the old audit cited for this coverage is gone, replaced by
`orb/waveform.ts`; the consolidation itself is unchanged.

**Value/notes:** Low, unchanged — functional coverage exists, just consolidated.

## Selectable markdown

**What it is (Mac):** Custom text-segment rendering so cross-paragraph text
selection works under SwiftUI, plus GFM table support.

**Where (Mac):** `MainWindow/Components/SelectableMarkdown.swift`.

**Windows status:** Unchanged. `components/Markdown.tsx` (173 lines) remains a
dependency-free regex renderer covering bold/italic/inline-code/fenced-code/
headings/lists/links with the same http(s)/mailto scheme restriction the old audit
noted. Still **no GFM table support** (no table-related code anywhere in the file)
and headings still render as a generic bold paragraph rather than per-level sizing.
Cross-paragraph selection remains a non-issue on Windows for the same reason the old
audit gave — it's ordinary DOM text, so the browser's native selection already spans
block elements.

**Value/notes:** Medium, unchanged — table rendering is the one concrete gap that
would transfer meaningfully across platforms.

## Citation cards

**What it is (Mac):** Tappable source cards below an AI reply — icon, title,
preview, chevron — grouped under a "Sources" header.

**Where (Mac):** `MainWindow/Components/CitationCardView.swift`.

**Windows status: Absent** as a rendering component, but the open question the old
audit raised ("depends on whether Windows chat currently surfaces citations... a
functional question for the chat-agent owner") is now answered: it does. `hooks/useChat.ts`
(`citations?: ChatCitation[]`, `useChat.ts:54,1284–1318`) and `lib/messagesSse.ts`
(`citations: { id, title, emoji? }[]`, `messagesSse.ts:31–34,69–85`) carry a full
citations array end-to-end from the SSE stream into the chat message object. Nothing
in `ChatMessages.tsx` or any other component reads `m.citations` to render it — the
gap is confirmed to be pure rendering, not data availability.

**Value/notes:** Medium, same value, but now a well-scoped rendering task rather than
an open data-availability question — a citation UI could be built directly against
`ChatMsg.citations` with no backend/plumbing work needed.

## Screenshot thumbnail (Rewind grid)

**What it is (Mac):** Grid thumbnails with hover delete, app-icon badge, OCR
indicator, search-match badge, and grouping by app.

**Where (Mac):** `Rewind/UI/ScreenshotThumbnailView.swift`.

**Windows status:** Unchanged. `components/rewind/RewindThumbnailStrip.tsx` is still
a horizontal filmstrip (`Thumb`, 128×64, `IntersectionObserver` lazy-load) with an
accent border+ring when active and app-name/time labels below the image — no
hover-delete, no OCR indicator, no search-match badge, no grid/group-by-app. The
component was touched 2026-07-20 for a memoization perf fix only; its layout and
feature set are the same ones the old audit described.

**Value/notes:** Medium, unchanged.

## Per-app icon rendering

**What it is (Mac):** `AppIconView` resolves and caches real macOS app icons.

**Where (Mac):** `Rewind/UI/AppIconView.swift`.

**Windows status:** Unchanged — Absent. `RewindThumbnailStrip.tsx:69` still shows
only `frame.app || 'Unknown app'` as plain text; no icon lookup/cache/render exists
anywhere in the Rewind components.

**Value/notes:** Low-medium, unchanged.

## Interactive timeline bar (Rewind scrubber)

**What it is (Mac):** A hand-drawn `NSView` scrubber with a glowing playhead, dashed
gap indicators, hover tooltip, and search-result tick marks.

**Where (Mac):** `Rewind/UI/InteractiveTimelineBar.swift`.

**Windows status:** Unchanged in capability. `components/rewind/RewindTimelineBar.tsx`
remains a DOM-based, fixed-hour-scale, pannable timeline with activity segments and
an accent playhead line, still with no playhead glow, no dashed/labeled gap segments,
and no hover tooltip (confirmed by grep — no `glow`/`tooltip` in the current file).
It gained a wheel-pan reliability fix (2026-07-16) and now feeds the drill-down
mini-timeline used by the rebuilt search-results flow (2026-07-14, see below), but
the visual polish gap the old audit identified is the same one that remains today.

**Value/notes:** Medium, unchanged.

## Full-screen timeline player (transport controls)

**What it is (Mac):** A dedicated video-style scrubber: transport buttons
(skip/step/play-pause), a 0.5×–8× speed menu, and keyboard shortcuts.

**Where (Mac):** `Rewind/UI/RewindTimelinePlayerView.swift`.

**Windows status: Partial** (was "Absent"). `components/rewind/RewindPlayer.tsx`
itself is unchanged — a single current frame with a click-to-expand lightbox
(`RewindPlayer.tsx:158–165`), still no step buttons, no speed control, no dedicated
transport slider inside the component. But the page around it, `pages/Rewind.tsx`,
now has a genuine **Play/Pause toggle** in its header (`Rewind.tsx:118–126`) driving
`useRewind`'s frame-by-frame auto-advance (`hooks/useRewind.ts:52,160–174`) — a
capability that simply did not exist at the time of the last audit. Still absent:
skip-to-start/end, step-frame, and a speed menu — Mac's transport remains
meaningfully richer.

**Value/notes:** High → Medium. Still the largest remaining Rewind gap, but no
longer a complete absence of any playback control.

## Rewind search bar (filters + focus polish)

**What it is (Mac):** A search field plus filter chrome: animated focus tint,
inline spinner, clear button, `⌘F` hint, app-filter menu, native date picker, and
Today/Yesterday/This-Week quick-date chips.

**Where (Mac):** `Rewind/UI/RewindSearchBar.swift`.

**Windows status: Partial** (was "Absent (all filter chrome)"). The old audit's
citation, `components/rewind/RewindSearchBar.tsx`, is now **dead code** — grepping
the renderer tree shows nothing imports it any more. The live search bar for Rewind
is inline in `pages/Rewind.tsx:96–124`: a 300ms-debounced search field explicitly
commented as macOS parity ("RewindViewModel 300ms," `Rewind.tsx:14`), a clear (✕)
button that appears once there's a query, `Ctrl/Cmd+F` to focus and `Escape` to back
out of drill-down → results → clear (`Rewind.tsx:63–75`), and a real graphical
month-grid date picker, `components/rewind/RewindDatePicker.tsx` — a button labeled
`MMM d, yyyy` that opens a calendar popover, explicitly ported from Mac's `.graphical
DatePicker` (`RewindDatePicker.tsx:1–15`), with the selected day rendered in Mac's
`purplePrimary` as the one sanctioned Track-4 exception in this file. Still absent:
an app-filter menu and Today/Yesterday/This-Week quick-date chips — no equivalent of
either exists in `Rewind.tsx` or `useRewind.ts`.

**Value/notes:** Medium, unchanged in severity but the surviving gap is narrower —
debounce, keyboard shortcuts, clear button, and a real date picker are done; app
filtering and quick-date chips are the concrete remainder.

## Search results filmstrip (Rewind search)

**What it is (Mac):** A horizontally-scrollable thumbnail filmstrip with hover
scale/lift/glow, a purple selection ring, a match-count badge, and a scroll-progress
capsule.

**Where (Mac):** `Rewind/UI/SearchResultsFilmstrip.swift`.

**Windows status: Partial** (was "Absent as a filmstrip... the starkest visual
downgrade in this audit"). `components/rewind/SearchResultsFilmstrip.tsx` was
rewritten on 2026-07-14 (two commits: "rich search-results list + drill-down
mini-timeline," "distinguish semantic search hits") into a real, image-bearing
component: each result group renders a lazy-loaded (`IntersectionObserver`) 120×80
thumbnail, the app name, a "Related" badge with a sparkle icon when the hit came
from semantic (not literal keyword) search (`SearchResultsFilmstrip.tsx:120–130`),
a time range, a highlighted context snippet (`Snippet`, `:66–81`), and an
"N screenshots" badge for multi-frame groups. Selecting a group drills into a
mini-timeline (handled by the parent `Rewind.tsx`). This directly reverses the old
audit's framing — Windows now shows screenshots in its search results, not just
text. It remains a **vertical list**, not a horizontally-scrolling filmstrip with
hover-scale/lift/spring/glow, no purple selection ring (correctly neutral per
INV-UI-1), and no scroll-progress capsule or `←`/`→` keyboard hints.

**Value/notes:** Medium (down from High) — the core "can I see what I'm looking for"
job this component exists to do is now met; the remaining gap is purely the
interaction-polish layer (hover choreography, progress indicator), not content.

## Onboarding orbital loading animation

**What it is (Mac):** A circular loading indicator with a breathing center pulse, a
progress-fill arc, and 4 orbiting glow particles.

**Where (Mac):** `FileIndexing/OnboardingLoadingAnimation.swift`.

**Windows status:** Unchanged — Present, comparable-to-better.
`components/onboarding/OrbitScanner.tsx` still renders 4 comet-trailed orbiting dots
around a center glow, respects the reduce-motion kill-switch, and is still
indeterminate/decorative rather than tied to real indexing progress (no
`progress`/`indeterminate`-driven arc logic found in the current file).

**Value/notes:** Genuine parity win, unchanged from the old audit; the
progress-wiring caveat still stands as an open question for the onboarding owner.

## Onboarding step transition (Windows ahead)

**What it is:** The transition style between full onboarding steps.

**Windows status:** Unchanged — still Windows-ahead. `components/onboarding/StepScaffold.tsx`
still wraps every step in `animate-fade-in` (a 0.4s fade + 6px slide,
`tailwind.config.ts` `fadeIn` keyframe) and animates its progress dots via
`transition-all`, while Mac's own step switch remains a hard, unanimated cut.

**Value/notes:** Still flagged so it isn't miscounted as a Windows gap.

## Onboarding demo-step choreography

**What it is (Mac):** Multi-phase demo steps gated on real app state (bar/voice),
including a volume-mute warning card.

**Windows status:** Unchanged — Partial, intentionally simplified.
`AskDemoStep.tsx` and `VoiceIntroStep.tsx` were both last touched 2026-07-14 for
unrelated fixes (a "can never dead-end" hold-to-talk fix on the voice step); neither
gained the multi-phase real-response gating or a volume-mute warning equivalent. The
documented reliability-over-fidelity tradeoff the old audit described still holds.

**Value/notes:** Low, unchanged.

## Drag-anywhere + resize-handle floating bar

**What it is (Mac):** The floating bar can be dragged anywhere and resized from its
corner.

**Windows status:** Unchanged — Absent, architecturally. `src/main/bar/window.ts:212–213`
still creates the bar with `resizable: false, movable: false` explicitly; the bar
remains a fixed top-edge dock that only morphs pill⇄panel size, not a
freely-positioned/resizable window.

**Value/notes:** Medium, unchanged — reads as an intentional divergence, not an
oversight.

## Click-through window behavior

**What it is (Mac):** `ClickThroughView` passes clicks through while replaying a
pending click once the window becomes key.

**Windows status:** Unchanged — Present, comparable. `main/bar/window.ts` still uses
`setIgnoreMouseEvents(true, { forward: true })` by default (`window.ts:235,349,362,372,735`),
flipping via the `applyClickThrough`/`setInteractive` pair when the renderer reports
the cursor over an interactive island.

**Value/notes:** No gap, unchanged.

## Sound-cue feedback

**What it is (Mac):** `focus-lost.aiff`/`focus-regained.aiff` audio cues, presumably
paired with the Glow Border effect's focus-state changes.

**Windows status:** Unchanged — Absent. No `.wav`/`.mp3`/`.aiff` file exists
anywhere under `desktop/windows` (excluding `node_modules`). Notably, the Glow
Border effect this was presumably paired with is **no longer absent on Windows**
(see above) — so if this audio cue gets scoped, its visual counterpart is already
built and shipped, not merely planned.

**Value/notes:** Low, unchanged, but now more clearly "the one missing half of a
feature that otherwise exists" rather than "paired with another absent feature."

## Design-system deltas

| Convention | Mac | Windows | Notes |
|---|---|---|---|
| Named color tokens | `OmiColors` enum | CSS custom properties + Tailwind tokens, neutral by default | `--accent` is white (fixed pre-audit); purple survives only as a cited, contained exception (`lib/macPalette.ts`), not a leak. |
| Named radius scale | `OmiChrome`, 5 steps | `--radius-*` / `tailwind.config.ts borderRadius`, 5 steps — now named, adoption still partial at call sites | Improved since the last audit (the scale itself now exists); most call sites still use ad hoc classes. |
| Panel/shadow bundling | `omiPanel`/`omiControlSurface` | `.glass`/`.glass-subtle`/`.glass-strong` | Comparable, unchanged. |
| Typography scale | `scaledFont`, user-adjustable | `lib/fontScale.ts`, user-adjustable (`Ctrl+=`/`-`/`0`, Settings slider) | **No longer a gap** — full parity mechanism now exists. |
| Window vibrancy | `NSVisualEffectView` (bar) | None for the bar (by design); Mica for the main window | Bar gap unchanged; main-window vibrancy is new since the last audit. |
| Focus-state ambient glow | `GlowBorderView`/`GlowEdgeWindow` | `main/glow/*` + `/glow` route, matching hue mapping | **No longer a gap** — full subsystem shipped 2026-07-14→19. |
| Motion/easing | SwiftUI springs; hand-rolled waveform physics | CSS `cubic-bezier`; orb-integrated waveform math | Comparable, unchanged in kind; waveform implementation relocated (see PTT section). |
| Iconography/branding assets | Rich `Resources/` set incl. provider logos | Provider logos now present (`assets/brands/*`) for the Connections panel; still none feed agent-pill identity | Partial improvement — assets exist, not yet wired to the pill UI. |
| Audio feedback | 2 `.aiff` cues | None found | Unchanged; now pairs with an already-shipped visual (glow), not an absent one. |
| State-driven iconography | Static `tray_icon.png` | 3 tray `.ico` states (idle/listening/paused) | Unchanged — Windows still ahead. |

## Spotted outside my scope

- `components/graph/`/`components/onboarding/BrainMap.tsx` (WebGL node-glow graph)
  remains a substantial Windows-only visual system with no direct Mac equivalent —
  unchanged from the last audit's note.
- The `orb/` subsystem (`orb/waveform.ts` and its shader/choreography siblings) has
  grown since the last audit: it now absorbs what used to be a standalone
  `overlay/Waveform.tsx` component. Any future audit of the bar's primary
  state-indicator should treat the orb, not a separate waveform component, as the
  place voice-level visualization logic lives.
- `glow_overlay_enabled` in `omiApi.generated.ts` is still unconsumed by the Windows
  renderer even though the feature it presumably names now works on Windows via a
  different, undiscovered gating path (or is unconditionally on) — worth a quick
  check with the settings/API-schema owner, reframed from "is this feature planned"
  to "why does a working feature not read this specific field."
- `docs/mac-parity-audit/TRACK4-PLAN.md` is a live, detailed orchestrator planning
  doc (Rewind/Conversations/Capture) with its own ground-truth corrections and a
  binding UI ruling on purple — any future UI-visual audit pass should read it
  directly rather than re-deriving the purple policy from source, since the ruling
  and its rationale are already written down there.
- The Hub/legacy-Home split (`pages/Home.tsx` switching between `HomeHub` and
  `pages/LegacyHome.tsx` on a `useLegacyHomeDesign` preference) means several visual
  findings in this file legitimately differ by which Home a given user sees. This
  audit describes the default (`HomeHub`) except where a legacy-only detail is
  explicitly called out (e.g. the legacy page's own avatar/typing treatment).
