# Requirements Checklist — derived from the reference screenshots

**This file is the acceptance criteria.** It was transcribed from 38 reference screenshots that no
implementer can see. If something is not written here, it is not verifiable — so treat every line as
a requirement and, when auditing, mark each DONE / PARTIAL / MISSING against the actual code.

The Status column is the author's belief at time of writing, and is exactly what an audit should
distrust.

## A. Teardown and cold onboarding (first request)

| # | Requirement | Status |
|---|---|---|
| A1 | Delete every old local build of the app | DONE |
| A2 | Revoke every previously granted permission so they must be re-granted | DONE |
| A3 | Walk the user through onboarding on a freshly built app | DONE |

## B. Menu bar / topbar

| # | Requirement | Status |
|---|---|---|
| B1 | Topbar colours must read as Apple-native, not off-brand | DONE — forced `.aqua` removed |
| B2 | Restore the ORIGINAL logo in the topbar, not the Anthropic-style one | DONE — template mark restored |
| B3 | Menu panel chrome must match a real system menu (rows, separators, metrics) | DONE |
| B4 | Nothing anywhere may use the Anthropic palette or serif display face | DONE — audit for stragglers |

## C. Installer

| # | Requirement | Status |
|---|---|---|
| C1 | DMG shows a drag-to-install window with our logo and wordmark | DONE |
| C2 | Instruction line "Drag Context for Claude into Applications to install" | DONE |
| C3 | Dashed drop-target outlines around BOTH icons | DONE |
| C4 | Arrow between the app icon and the Applications folder | DONE |
| C5 | Neutral palette, no warm/clay cast | DONE |

## D. First-run cinematic

| # | Requirement | Status |
|---|---|---|
| D1 | Big centred logo on a dimmed desktop at first launch | DONE — `Cinematic.swift` beat 1, scrim 0.96 |
| D2 | The logo BUILDS ITSELF with animation (not a fade-in of a finished image) | DONE — head, eyes, legs stroke on in sequence, then the wordmark. `CinematicMarkGeometry` scales stroke weight back with size, because `ContextMark`'s 9.5% menu-bar weight renders a torus at 132pt |
| D3 | Background music plays through the sequence | DONE — `Sound.music.start()` on beat 1, faded out over 2.0s at hand-off |
| D4 | Logo morphs into a horizontal BAR | DONE — beat 3, matched geometry, screenshot caught mid-morph |
| D5 | The bar STRETCHES into a search-bar shape | DONE — beat 4, swoosh on the stretch |
| D6 | A question types itself into the bar | DONE — "what was I working on today?" with a caret, keystroke sound every 4th char |
| D7 | Populated by a large swarm of windows flying in | DONE — REAL captured frames, verified on screen (Xcode with the user's own projects, Chrome with their own bookmarks). Picks one frame per app before a second of any, because an even spread returned five of six identical Cursor frames |
| D8 | Swooshing sounds on the window fly-in, staggered | DONE — one swoosh per card, 0.13s stagger |
| D9 | Click sounds on interaction throughout | DONE — cinematic beats, card advance (`go(to:)`), chime on every grant |
| D10 | Interactive and immersive overall; skippable | PARTIAL — "Skip intro" and a music mute are on screen and abort is tested from all six beats, but Esc/Skip are NOT verified on hardware: synthetic Escape does not reach a borderless window of an inactive accessory app |

## E. Onboarding cards

| # | Requirement | Status |
|---|---|---|
| E1 | Welcome card: title, one-line value, "Get started" + "Skip intro" | PARTIAL — card and action DONE; there is no "Skip intro" on the CARD (the cinematic carries it). Skipping the cards would leave a non-functional app |
| E2 | Value card: heading, paragraph, three bulleted claims, "Continue" | DONE |
| E3 | "Enable permissions" card listing each permission with its own explanation | DONE — each row renders its own first-person sentence via `Capability.title` |
| E4 | Sign in with the Omi account | EXISTS — restyle only |
| E5 | Connectors card: which agent surfaces to register with, checkboxes | EXISTS — restyle only |
| E6 | Progress dots across the flow | DONE — 5 dots when sign-in is needed, 4 when the session restores |
| E7 | An optional "stay in touch" email step exists in the reference | DECIDED OUT — the Omi account already identifies the user; do not add a second email capture |

## F. Permission choreography

| # | Requirement | Status |
|---|---|---|
| F1 | An animation showing the app being dragged into the permissions list | DONE — `GhostRowReplica`, ours, captioned as a preview |
| F2 | It highlights exactly where the row needs to go | DONE — AX ring on the REAL System Settings row. 477/477 exact rects live, cross-checked against an independent AX dump; 112 refusals all correct. `PermissionGuidance` is `.pointing` or `.instruction` only, so a mispositioned ring is unrepresentable |
| F3 | Same treatment for Screen Recording | DONE — overlay in `openScreenSettingsOnce`, relaunch nudge preserved |
| F4 | "Very accurate" to the reference | NOT BUILT — this row previously described the replica-then-ring-the-real-row design as though it existed. It does not; there is no such code. The CONSTRAINT is real and still governs the design: on macOS 26 the dashed "Drag this row up into the list" affordance is System Settings' OWN UI, no app can draw inside that window, and the reference app did not build it either. `MenuBarSpotlight` rings *this app's own status item*, not a System Settings row. |
| F5 | Permissions requested one at a time, paced | DONE — preserve |
| F6 | Screen Recording relaunch nudge | DONE — preserve |

## G. Tutorial (the long sequence)

| # | Requirement | Status |
|---|---|---|
| G1 | "Learn how to use it" card with Start / Skip | DONE — `Tutorial/TutorialCardView.swift` `invitation`; walked live |
| G2 | Opens a page in the browser as the first step. **NOT Wikipedia, and not any Wikipedia URL** — direct user instruction. The chosen page is `https://www.lingscars.com/`: text-dense (good for the OCR beat), online for two decades, and absurd enough that Claude reporting it back is the joke. **It is Cloudflare-challenged: `curl` gets HTTP 403 and an interstitial, so never fetch or health-check it — open it with `NSWorkspace` and let the real browser pass the challenge.** Frame progress must key off frame *count*, never a specific captured word, because on a slow network the first frames may be the interstitial. | DONE — `TutorialModel.articleURL`, opened with `NSWorkspace.shared.open` and never fetched; no reachability probe exists in the tutorial. The frame gate counts frames only, and the search beat asks the user for a word they saw rather than testing for one this code guessed, so the interstitial case costs nothing. |
| G3 | Asks the screen-recording permission at the right moment | DONE — `screenAccess` step, dropped from the plan when the grant already exists, advances on the real TCC answer. The ungranted path is unit-tested, not walked: this machine is granted |
| G4 | Coach mark: "Scroll around on this page and collect your first frames" | DONE — anchored over the browser window's real frame from the window server; degrades to a centred card with no arrow when it cannot be found |
| G5 | A LIVE frame counter reading our own store — never a timer pretending | DONE — assigned from `RewindQueries.frameCount` every tick; the model contains no increment. Measured live: 0 for the first 70 s on a static screen, then 1…5 by t=300 s. Mutating the gate into a 10 s timer fails `testTheFrameCounterReflectsTheStoreAndNeverElapsedTime` |
| G6 | "It's time to open the timeline", showing the chord | DONE — chord read from `GlobalShortcuts.shared.display(for: .openTimeline)`, described as live only when `readiness == .armed` |
| G7 | The timeline/rewind window opens | DONE — `RewindWindow.present` with the shell's own wiring; the step only claims the window is up when `isVisible` agrees |
| G8 | Coach mark with a left-scrolling animation: "scroll left to see the past" | DONE — anchored above the real `RewindTrackView` frame (card bottom 803, track top ~817), arrow down; the animation collapses under Reduce Motion |
| G9 | Coach mark: "Find specific moments — click Search All" | DONE — anchored under the pill's real accessibility frame (pill (182,171) 118×25 → card x=31, y=211, arrow up), and the step advances because the real pill was pressed |
| G10 | A popup appears after clicking Search All | PARTIAL — the popup is the tutorial's own query card, not `SearchBarWindow`. Deliberate: that bar routes the question to Claude, which is the later proof beat, while G12 needs a memory row and a timestamp this app can show. Moving G10/G11 onto the real bar would move G12's gate to `QueryStamp` |
| G11 | Coach mark: type a query and press Enter | DONE — real field, submits on Return, runs `Queries.recall` against the real store; an empty result keeps the step and says so |
| G12 | Result appears, then "Found it! Tap the memory to jump back to that exact moment" | DONE — verified live on a real hit (a frame captured at 12:40:21 AM whose OCR carried the page title); tapping it loads that frame's real picture and labels it with the captured second. No button can satisfy the gate |
| G13 | "You are all set" completion card | DONE — and its sentence changes when the frame gate was waived, so a waived run is never told its screen is searchable |
| G14 | "One more thing — you can always find it up here in the menu bar" | DONE — the `menuBar` step calls `MenuBarSpotlight.show()`, and teardown hides it |
| G15 | Shortcut-conflict notification with a one-click remedy | PARTIAL — `ShortcutConflicts.scan` reads other tools' real config files and the row renders only on evidence. On THIS machine the reference's "Codex also uses ⌘⌘" is FALSE (those Codex commands ship with no default binding and no keymap file exists), so no row appears — correct, but unexercised against a real conflict. The one-click write is deliberately NOT implemented: Codex rewrites keybindings.json wholesale from an in-memory keymap, so writing it under a running Codex leaves the old chord live and the button would report success while the conflict persisted |
| G16 | Progress dots through the tutorial | DONE — `TutorialProgressDots`, counting this run's plan (13 beats when Screen Recording is already granted) |
| G17 | Music throughout, click sounds on every step | DONE — `Sound.music.start()` at `begin()`, stopped by the one teardown; a click on every advance, a swoosh on the page and on the timeline, a chime on each earned gate |

## H. Rewind window

| # | Requirement | Status |
|---|---|---|
| H1 | Ported from the Omi repo rather than reinvented | DONE |
| H2 | Functionally as close to the reference as possible | DONE — verify |
| H3 | Centred window title for the mode | DONE |
| H4 | "Search All" pill with its `/` hint, top-left | DONE |
| H5 | Gear button opening Settings | DONE (closure, not yet wired to Settings) |
| H6 | Frame centred with a segment-keyed border | DONE |
| H7 | Chevrons on the frame's left/right edges for segment nav | DONE |
| H8 | Date/time pill bottom-left with a picker | DONE |
| H9 | Four circular controls bottom-right: open externally, live text, zoom out, zoom in | PARTIAL — open-externally is HIDDEN because it cannot be resolved honestly (0.10% of frames); needs capture to record AXURL |
| H10 | Timeline track with per-app coloured segments | DONE |
| H11 | App icon badges pinned along the track | DONE |
| H12 | Two-finger scroll to move forward/backward in time | DONE — horizontal intent wins, pans in seconds. VERIFY it works over the frame area, not only the 32pt track |
| H13 | Live Text highlighting selectable text in the frame | DONE — recomputed on demand, since capture discards Vision boxes |
| H14 | Track zoom distinct from frame-image zoom | DONE |
| H15 | Beautiful | SUBJECTIVE — verify by screenshot |

## I. Settings — six panes

Sidebar: General, Agents, Appearance, Capture, Storage, Exclusions. Every row is an icon tile, a
title, a grey subtitle, and a right-hand control.

### I-General
| # | Requirement | Status |
|---|---|---|
| I1 | Open Timeline Shortcut — recorder, default double-Command, "Clear it to use ⌘⌘" | PARTIAL — recorder, copy, cleared-state and rejection are real, but bound to `SettingsShortcutChord`, a stub. `GlobalShortcuts` now exists and must be adapted onto `ShortcutBindingProvider` |
| I2 | Open Search Shortcut — recorder, default ⌘⌘⇧ | PARTIAL — same stub binding as I1 |
| I3 | Conflict row, shown ONLY on a real conflict, with a one-click switch | PARTIAL — UI live-queries and never persists; the real `ShortcutConflicts` scanner exists but the pane still reads the stub |
| I4 | Launch on Login toggle | MISSING (LoginItem exists) |
| I5 | Airgap Mode toggle — suppresses telemetry, update checks, remote favicon requests; takes effect after relaunch | MISSING (engine flag exists) |
| I6 | Updates row showing the real version | MISSING |
| I7 | Automatic Updates toggle | DECIDE — no updater exists. Show the real version and OMIT both update controls unless Sparkle ports cheaply. A button that cannot update is worse than none, and disabling it still implies the feature. |

### I-Agents
| # | Requirement | Status |
|---|---|---|
| I8 | Route to Agent dropdown | MISSING |
| I9 | Claude target dropdown: Claude app (prompt pre-filled) or the `claude` CLI in Terminal | DONE — `ClaudeRouter`. Pre-fill is genuinely supported, not a fallback: `claude://code/new?q=` read out of the installed Claude's own router and verified by watching text land in the Code composer unsent. Clipboard fallback only when nothing claims the scheme |
| I10 | Tip line about mentioning the app inside Claude Code/Codex/Cursor | MISSING |
| I11 | An illustrative mock of an agent prompt box | MISSING |
| I12 | CLI toggle installing a command to `~/.local/bin` | MISSING — decide whether we ship a CLI at all; our equivalent is the MCP registration |
| I13 | Detected agent list (Claude, Codex, Cursor) with a green "Installed" pill | MISSING — detection must be real, with a not-installed state |

### I-Appearance
| # | Requirement | Status |
|---|---|---|
| I14 | Appearance: System / Light / Dark preview tiles, selected one ringed | MISSING |
| I15 | Accent Colour dropdown with a colour dot | MISSING — default must mean `controlAccentColor`; NEVER offer purple (INV-UI-1) |
| I16 | Show Dock Icon toggle | MISSING |
| I17 | Timeline section with a LIVE preview reflecting the toggles below it | MISSING |
| I18 | Open externally toggle + `↵` hint | MISSING |
| I19 | Live Text toggle | MISSING |
| I20 | Zoom controls toggle + `⌘⇧+/−` hint | MISSING |
| I21 | Segment navigation toggle + `⌥←/→` hint | MISSING |
| I22 | Hidden controls keep their keyboard shortcuts working | MISSING |

### I-Capture
| # | Requirement | Status |
|---|---|---|
| I23 | Screen Capture toggle | MISSING |
| I24 | Pause on Inactivity toggle | MISSING |
| I25 | Capture Quality: four tiles (Best / Default / Compact / Smallest), subtitle describes the selection | MISSING |
| I26 | Footnote about quality vs disk space | MISSING |

### I-Storage
| # | Requirement | Status |
|---|---|---|
| I27 | Large header with REAL measured usage and "no storage limits set" | MISSING |
| I28 | Storage management radio group: Off / Compress / Limit | MISSING |
| I29 | Off is the default: "Keep all your data. Forever." | MISSING |
| I30 | Limit deletes oldest recordings — needs a threshold control AND an explicit confirmation; never reachable by one stray click | MISSING |

### I-Exclusions
| # | Requirement | Status |
|---|---|---|
| I31 | Search field; Apps / Websites segmented control | MISSING (engine DONE) |
| I32 | Apps: Categories → Password Managers, expandable | MISSING (engine DONE) |
| I33 | Apps: Excluded section, locked rows the user cannot remove | MISSING (engine DONE) |
| I34 | Apps: System section (Notifications, Control Center, Spotlight, Siri, Login Screen) | MISSING (engine DONE) |
| I35 | Apps: Recently Recorded, with real icons | MISSING |
| I36 | Apps: All Applications, alphabetical, with icons | MISSING |
| I37 | Websites: "Search or add domain" | MISSING (engine DONE) |
| I38 | Websites: Banks category | MISSING (engine DONE) |
| I39 | Websites: Exclude Private Tabs toggle | PARTIAL — Chromium/Edge/Firefox detected from title; **Safari cannot be detected at all**, so the copy must not overclaim |
| I40 | Websites: Recently Recorded domains with favicons | MISSING — favicons are network requests and must obey Airgap Mode |

## J. Cross-cutting

| # | Requirement | Status |
|---|---|---|
| J1 | Music playing throughout the experience | DONE — cinematic starts the bed and fades it at hand-off; the tutorial runs its own from `begin()` to teardown |
| J2 | Sounds on clicks | DONE — click on every card and tutorial advance, swoosh on page open and timeline, chime on each earned gate. Chrome cues honour the system UI-sound setting; the bed has its own mute |
| J3 | Interactive and immersive; better than the reference | JUDGEMENT — verify by screenshot |
| J4 | Everything verified by screenshots and screen observation | ONGOING |
| J5 | All edits land on the upstream PR | ONGOING |
| J6 | Never purple anywhere (INV-UI-1) | ENFORCE |
| J7 | Nothing fabricated: no fake screenshots, no staged payoffs, no controls that cannot work | ENFORCE |

## Known deliberate divergences from the reference

These are decisions, not omissions. An audit should confirm each is still the right call rather than
"fixing" them.

1. **The permission drag affordance is macOS 26's own UI** (F4). We guide and highlight; we never
   redraw it.
2. **Open-externally is hidden, not faked** (H9). Matching URLs in window titles resolves 2.7% of
   frames and every one is a link rendered inside a page rather than its address. Needs capture to
   record `AXURL`.
3. **The search bar routes to Claude rather than answering** — the retrieval surface is Claude, by
   design.
4. **No second email capture** (E7); the Omi account already identifies the user.
5. **Update controls omitted unless a real updater exists** (I7).
6. **Safari private windows are not excludable** from the window title alone (I39); the seam exists
   for AX to fill.
