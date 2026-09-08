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
| C1 | DMG shows a drag-to-install window with our wordmark | DONE — wordmark only. The painted logo was removed: Finder already draws the real app icon in the left-hand slot, so a second copy of the mark in the corner is the same object twice and reads as a decoy next to the one the user is meant to drag |
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
| F1 | An animation showing the app being dragged into the permissions list | DONE — on the real System Settings window, not as a preview inside our card. A floating "Context for Claude" row is carried along the arrow into `SettingsSpotlightScene.dropSlot`, a row-height strip at the list edge the row arrives from. Only the slot and the source row are dashed — never the whole list, which is what made the earlier version read as "everything here is wrong". The in-card `GhostRowReplica` rehearsal was deleted along with its "Show me the row" button; the guidance now appears on its own |
| F2 | It highlights exactly where the row needs to go | DONE — AX ring on the REAL System Settings row. 477/477 exact rects live, cross-checked against an independent AX dump; 112 refusals all correct. `PermissionGuidance` is `.pointing` or `.instruction` only, so a mispositioned ring is unrepresentable |
| F3 | Same treatment for Screen Recording | DONE — overlay in `openScreenSettingsOnce`, relaunch nudge preserved |
| F4 | "Very accurate" to the reference | NOT BUILT — this row previously described the replica-then-ring-the-real-row design as though it existed. It does not; there is no such code. The CONSTRAINT is real and still governs the design: on macOS 26 the dashed "Drag this row up into the list" affordance is System Settings' OWN UI, no app can draw inside that window, and the reference app did not build it either. `MenuBarSpotlight` rings *this app's own status item*, not a System Settings row. |
| F5 | Permissions requested one at a time, paced | DONE — preserve |
| F6 | Screen Recording relaunch nudge | DONE — preserve |

## G. Tutorial (the long sequence)

| # | Requirement | Status |
|---|---|---|
| G1 | "Learn how to use it" card with Start / Skip | DONE — `Tutorial/TutorialCardView.swift`, now spoken by the mark ("Let me show you what I do."); walked live |
| G2 | Opens a page in the browser as the first step. **NOT Wikipedia** — direct user instruction | **DONE, on the third instruction, and the chain is the reasoning.** (1) Open a page — Wikipedia. (2) "I dont like Ling's website": a third-party commercial page in somebody's browser thirty seconds after asking to watch their screen is wrong on taste and on trust, so the page was cut outright and the beat ran on whatever the user already had open. (3) "Open Anthropic's website and say scroll for a bit." Instruction 2 objected to a **stranger's** page, and (2) was worse than it looked on the machine that matters: a first run is a fresh Mac with an empty desktop, so a beat that said "go and find something to look at" waited for frames the user had nothing to produce. `TutorialModel.readingMaterial` is `https://www.anthropic.com/research` — Anthropic's own site, the one this app can open without choosing a third party's content for somebody, and the page on it there is enough of to scroll: the home page is short and largely static, capture dedupes perceptually, and a user who scrolled it end to end produced very little for the gate. Reported as "open anthropic's research page, maybe, because there's just more content to read and people can scroll through" — opened through `TutorialEnvironment.openPage`, which answers whether it **really** opened, so the card claims a page only when `NSWorkspace` said yes. Not opened at all for a user who declined the screen grant, where nothing they scroll could be captured. `testTheCaptureBeatOpensAnthropicsSiteAndAsksForAScroll`, `testAPageThatWouldNotOpenIsNeverClaimedAsOpened`, `testNoOtherBeatOpensAnything` |
| G3 | Asks the screen-recording permission at the right moment | DONE — `screenAccess` step, dropped from the plan when the grant already exists, advances on the real TCC answer. The ungranted path is unit-tested, not walked: this machine is granted |
| G4 | Coach mark: "collect your first frames" | DONE, reworded three times and re-placed — "I opened Anthropic's research page." / "Scroll through it for a bit, and I will tell you when I have it." Direct user instruction: do not say *see anything*. The ask is now a **gesture** rather than an act of attention, which is also the honest ask — scrolling is what produces distinct screens for the store to hold, and attention is not something this app can observe. The card takes `TutorialPlacement.outOfTheWay` (bottom trailing, the only step that does) so it is not sitting on the page it just opened. `testNoCardAsksTheUserToLookAtSomething` walks every state of the beat, including the one where the page would not open |
| G5 | A LIVE frame counter reading our own store — never a timer pretending | **GATE DONE, READOUT DECIDED OUT.** Direct user instruction: the card must not say it is collecting frames. The *gate* is untouched and is now the only thing holding the line — `framesCollected` is still assigned from `RewindQueries.frameCount` every tick and the model still contains no increment. What the user sees instead is the mark saying "Scroll through it for a bit" and then "Got it.", which is the same fact in a human's words. Mutating the gate into a timer still fails `testTheCaptureBeatReflectsTheStoreAndNeverElapsedTime`, and `testTheCaptureBeatSaysGotItOnlyOnceItReallyHasIt` proves the *sentence* is a consequence of the store too. `testNoCardEverSpeaksAProgressCountOrAFrameCount` walks the whole flow and fails on any digit |
| G6 | "It's time to open the timeline", showing the chord | **DONE, and it is now the beat that teaches the chord.** Direct user instruction: "this rewind window should open after asking me to press the command keys and from that action". The window used to open *itself* the moment the step began, which taught nothing — the tutorial announced a shortcut and then did the shortcut's job. `openTimeline` now asks and waits: its gate is `TutorialGate.realHotkey`, satisfied only by `GlobalShortcuts` genuinely delivering `.openTimeline`, and the window that appears is opened by the **app's own handler** in `ContextApp.swift`, not by the tutorial. `GlobalShortcuts.addObserver` exists for exactly this — an additive listener, so the tutorial never takes ownership of the shortcut. `testTheChordBeatWaitsForTheRealShortcutAndOpensNothingItself` asserts `timelinePresentations == 0` through five minutes of ticking. **The keys type themselves** (direct user instruction: "show the keyboard and the key getting pressed"): `TutorialChordDemo` loops a press over `TutorialChordCycle`, which draws `⌘⌘` as **one cap struck twice** and a rebound `⌘⇧K` as modifiers held while the last key falls. Two caps was the first drawing and it was reported — "expressing both the command keys one by one. It's supposed to be both the command keys together" — because a Mac has two Command keys and two ⌘ caps lighting in turn draws pressing both of them. Neither reading of that report is the fix: `ModifierDoubleTap` watches one modifier mask go down, up and down, so both Command keys held together cannot fire it at all. `testTheDemonstratedTapIsOneCapAndIsTheGestureTheDetectorFires` replays the drawing through that real detector, and replays the "together" reading through it too. The loop stops because the card stops rendering it, which is when the real chord fires |
| G7 | The timeline/rewind window opens | DONE — by the user's keypress (G6), through the shell's own `RewindWindow.present` wiring; the step only claims the window is up when `isVisible` agrees. The honest fallback for a machine whose chord cannot fire (Accessibility ungranted) is a labelled waiver that opens it *and says so*: `testAChordThatCannotFireOffersTheWayOutAtOnceAndSaysWhoOpenedIt` asserts the card reads "I opened it for you." rather than congratulating a keypress that never happened. The tutorial no longer keeps its own copy of the window's `onSearch` wiring — `Tutorial.searchPillWasPressed()` answers the shell, so there is one window with one set of buttons behind it |
| G8 | Coach mark with a left-scrolling animation: "scroll left to see the past" | **DONE, and now actually detected.** Direct user report: "The two finger dragging didnt work." Two independent causes, both real: (1) **nothing listened** — the hint was decorative and the step's gate was `.userAction`, so a perfect gesture changed nothing; (2) **the gesture moved nothing** — the track's scroll called `RewindModel.panTrack`, which pans the *visible window* and is clamped to the loaded day, and `resetTrackWindow` opens with `trackSpan` = the whole day, so `bounds.end - trackSpan == bounds.start` and `trackStart` could not move by any number of seconds. Every scroll on a freshly opened timeline was arithmetically a no-op. Fixes: `TutorialDrag` (a pure recogniser over scroll deltas, 12 tests in `TutorialDragTests`) behind a **local** `NSEvent` monitor gates the step as `TutorialGate.realGesture`; and `RewindModel.travel(by:)` replaces `panTrack`, moving the **playhead** so the picture changes and the window follows via `keepPlayheadVisible()`. The recogniser has no phase filter (momentum counts), no direction rule (which way is "back" is the user's own natural-scrolling setting, which this app does not get to read) and no trackpad requirement (a notched wheel scales by `pointsPerLine`). The card's arrow is `arrow.left.and.right` for the same reason. **The gesture is now drawn being made** (direct user instruction: show an animation for the left/right scroll): `TutorialScrollDemo` sweeps a hand across a strip of the timeline with the panels travelling under it, both driven by one phase through `TutorialScrollCycle`, so "the content moved because your fingers did" is true by construction — `testTheDemonstratedPanelsFollowTheHandExactly` fails if they ever disagree, which is how an inverted drag would be taught. It sweeps both ways for the same natural-scrolling reason, it collapses to a still under Reduce Motion, and it stops when the real gesture lands |
| G9 | Coach mark: "Find specific moments — click Search All" | DONE — anchored under the pill's real accessibility frame (pill (182,171) 118×25 → card x=31, y=211, arrow up), and the step advances because the real pill was pressed |
| G10 | A popup appears after clicking Search All | PARTIAL — the popup is the tutorial's own query card, not `SearchBarWindow`. Deliberate: that bar routes the question to Claude, which is the later proof beat, while G12 needs a memory row and a timestamp this app can show. Moving G10/G11 onto the real bar would move G12's gate to `QueryStamp` |
| G11 | Coach mark: type a query and press Enter | DONE — real field, submits on Return, runs `Queries.recall` against the real store; an empty result keeps the step and says so |
| G12 | Result appears, then "Found it! Tap the memory to jump back to that exact moment" | DONE, merged into G11's card — typing and finding are one continuous idea, and the mark's line changes from "Type something you just looked at." to "There it is." *because* there was a real hit. `search` no longer advances the step itself: the gate is `!results.isEmpty` and the Continue button is the only thing that reads it, so the check that says "something was really found" is the one the button runs. A second search that finds nothing takes the line back off the card (`testAFailedSecondSearchWithdrawsTheFoundItLine`) |
| G13 | "You are all set" completion card | DONE — the sentence comes from `TutorialOutcome`, an enum with exactly one route to `.caught` (the gate's own condition). A waived frame beat closes on an admission, and a *waived screen grant* now closes on `.cannotSee` — the flag the old code set and never read. `testTheSuccessSentenceIsReachableOnlyFromARealFrameCount` drives every other route and asserts none of them reaches the success sentence |
| G14 | "One more thing — you can always find it up here in the menu bar" | DONE — the `menuBar` step calls `MenuBarSpotlight.show()`, and teardown hides it |
| G15 | Shortcut-conflict notification with a one-click remedy | PARTIAL — `ShortcutConflicts.scan` reads other tools' real config files and the row renders only on evidence. On THIS machine the reference's "Codex also uses ⌘⌘" is FALSE (those Codex commands ship with no default binding and no keymap file exists), so no row appears — correct, but unexercised against a real conflict. The one-click write is deliberately NOT implemented: Codex rewrites keybindings.json wholesale from an in-memory keymap, so writing it under a running Codex leaves the old chord live and the button would report success while the conflict persisted |
| G16 | Progress dots through the tutorial | **DECIDED OUT** — direct user instruction: the tutorial must not show how many steps it has. Knowing it is fourteen long is a reason to leave it. `TutorialProgressDots` and `TutorialModel.progress` are deleted; `plan` survives because dropping an already-satisfied step still has to work. The flow is also eleven beats now rather than fourteen (G2 and G12 cut or merged; G6 came back as the beat that *waits* for the chord rather than announcing it), which is the other half of the same instruction |
| G17 | Music throughout, click sounds on every step | DONE, with a **last beat** — `Sound.music.start()` at `begin()`, faded out at the first step that hands the user to another application (`TutorialStep.handsOverToAnotherApp`, i.e. the browser) and idempotently again by teardown. It used to run until the tutorial ended, and the tutorial does not end on a schedule: `claudeProof` waits on Claude and cannot be waived, so a run left there looped a 24-second bed indefinitely. Reported from that beat as "you should really stop the noise after a while"; a click on every advance, a swoosh on the page and on the timeline, a chime on each earned gate |
| G18 | The mark does the talking | DONE — every card goes through `TalkingMark(lead:leadStyle:aside:)`, the same component and the same call-site shape onboarding uses, so the character that introduced itself is the one running the tutorial. The words come from `TutorialModel.speech`, not from the view, which is what lets `TutorialTests` assert them. Card width went 420 → 470: the mark takes a fixed 56 pt out of every line, and every card was re-rendered in Light and Dark at the new width to confirm nothing clips |

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

## I. Settings — five panes

Sidebar: General, Agents, Capture, Storage, Exclusions. Every row is an icon tile, a title, a grey
subtitle, and a right-hand control.

**Seven settings rows are deliberately not shipped**, each removed on a report on 2026-08-16, and
they account for **twelve** requirement IDs marked DROPPED below: the Appearance pane entire (I14 and
I17–I22 — one pane, seven IDs), the second shortcut recorder (I2), Airgap Mode's switch (I5), the
agent survey (I13) and Capture Quality with its footnote (I25, I26).
`docs/rewind-and-settings.md` § Part 2 carries the same list as one table. The pattern in all of them
is the same and is worth stating once: a control that only makes the product worse, or that
duplicates another control, is removed rather than narrowed or hidden — a setting nobody can find
still fires.

### I-General
| # | Requirement | Status |
|---|---|---|
| I1 | Open Timeline Shortcut — recorder, default double-Command, "Clear it to use ⌘⌘" | PARTIAL — recorder, copy, cleared-state and rejection are real, but bound to `SettingsShortcutChord`, a stub. `GlobalShortcuts` now exists and must be adapted onto `ShortcutBindingProvider` |
| I2 | Open Search Shortcut — recorder, default ⌘⌘⇧ | DROPPED (2026-08-16 report) — it bound a second chord onto the *same* window I1's opens. `ContextApp.shortcutFired` answered `.openActivity` and `.openSearch` with one `window.press()`, because the Spotlight panel became the Activity window; so the pane drew two recorders, two defaults and two conflict rows for one behaviour, and a user who rebound one could not tell which had won. Removed from `GlobalShortcuts.Action` as well as from the pane — hiding the row would have left the chord firing — and `ModifierDoubleTap` went with it |
| I3 | Conflict row, shown ONLY on a real conflict, with a one-click switch | PARTIAL — UI live-queries and never persists; the real `ShortcutConflicts` scanner exists but the pane still reads the stub |
| I4 | Launch on Login toggle | MISSING (LoginItem exists) |
| I5 | Airgap Mode toggle — suppresses telemetry, update checks, remote favicon requests; takes effect after relaunch | DROPPED (2026-08-16 report) — the switch, not the promise. `ExclusionEngine` still carries the flag, `NetworkEgress` still refuses every client while it is set, and anyone whose `exclusions.json` already says `airgapMode` keeps exactly the behaviour they chose. Ripping out the enforcement instead would silently start uploading for those users. Guard: `SettingsTests.testAirgapEnforcementSurvivesTheRemovalOfItsSwitch` |
| I6 | Updates row showing the real version | DONE — `UpdatesSettingsRow` reads the bundle version through `ContextUpdater`. |
| I7 | Automatic Updates toggle | DECIDED — Sparkle now ships (`Sources/ContextApp/Update/`, the shared micro-app feed, `docs/releasing.md`). The Updates row has a real `Check Now`; checks and verified downloads run automatically, while installation always asks before relaunch. A toggle is intentionally omitted because the shipping policy is fixed and locally signed copies are refused by `UpdatePolicy`. |

### I-Agents
| # | Requirement | Status |
|---|---|---|
| I8 | Route to Agent dropdown | DROPPED (J7) — it shipped and did nothing. `context.settings.agentRoute` had zero readers: no code anywhere branched on it. Its subtitle advertised "With ⌘↵ you can send your query directly to your agents", and there is no ⌘↵ — `SearchBarView` handles `insertNewline:` and `cancelOperation:` only — routing to the path divergence 3 below deliberately removed. Row, `AgentRoute`, the key, the default and the published property are all gone; a stored value decodes to nothing and is ignored. The real routing decision is I9 |
| I9 | Claude target dropdown: Claude app (prompt pre-filled) or the `claude` CLI in Terminal | DONE — `ClaudeRouter`, chosen in `SettingsStore.claudeTarget` and read by `ClaudeHandoff`. **This is no longer the search bar's setting**: the bar answers in-app from this app's own indexes and never routes to Claude. What the dropdown steers is the tutorial's guided hand-off — `Claude App` opens `claude://claude.ai/new?q=` (a *new chat*, prompt pre-filled and not sent; the `code/new` variant was verified by watching text land in the Code composer unsent), `Terminal` runs the `claude` CLI with the question in whichever app owns `.command` files. Pre-fill is genuinely supported, not a fallback; the clipboard branch happens only when nothing claims the scheme. The preference has exactly one home and one consumer — no `ClaudeRouter.preferredTarget` — and the row's subtitle is `ClaudeRouter.targetSubtitle`, so it describes what *this* Mac would really do for each option. `ClaudeHandoffTests.testTheHandoffRoutesToTheTargetChosenInSettings` pins both values of the dropdown |
| I10 | Tip line about mentioning the app inside Claude Code/Codex/Cursor | DONE, narrowed — it now names **Claude Code and Claude Desktop only**. `ClaudeRegistrar` writes those two configs (`~/.claude.json`, `claude_desktop_config.json`) and nothing in this package writes a Codex or Cursor MCP entry, nor do we ship a CLI (I12), so naming them made two thirds of the sentence work the user would have had to do by hand without being told. Codex and Cursor remain in the I13 survey, which reports what is *installed* and claims nothing about integration |
| I11 | An illustrative mock of an agent prompt box | MISSING |
| I12 | CLI toggle installing a command to `~/.local/bin` | MISSING — decide whether we ship a CLI at all; our equivalent is the MCP registration |
| I13 | Detected agent list (Claude, Codex, Cursor) with a green "Installed" pill | DROPPED (2026-08-16 report) — it was built, with real detection and a real not-installed state, and it was read-only: nothing on the pane or anywhere else acted on the survey, and the two surfaces this app registers with are named by I10's tip line either way. A list the user cannot do anything with, in the pane where the two controls that do something live. `AgentSurface`/`AgentPresence` and the probe are gone; `AgentPaths` keeps the `~`-abbreviation the Storage pane needs |

### I-Appearance

**The pane does not exist.** Reported as *"remove appearance options altogether … in fact remove
appearance section from settings altogether"*, and the three things on it came apart cleanly: the
theme tiles let a user disagree with their own machine's Appearance setting inside one app, the four
timeline toggles were four ways to make the timeline worse, and the Dock row was never an appearance
choice. Guard: `SettingsTests.testThereIsNoAppearancePane`.

| # | Requirement | Status |
|---|---|---|
| I14 | Appearance: System / Light / Dark preview tiles, selected one ringed | DROPPED (2026-08-16 report) — `System` (the default, and what every install was on) installed no appearance at all, so the control existed only to pin this app against the machine around it. Phase 0 of `docs/first-run-experience.md` had already deleted a forced `NSApp.appearance = .aqua` for rendering a light popover inside a dark system menu; the tiles were that defect with a switch on it |
| I15 | Accent Colour dropdown with a colour dot | DROPPED (J7, INV-UI-1) — **the requirement itself was wrong**, and it took shipping it to see why. Its only consumer was `.tint(store.accentColor)` on the Settings window, so picking a colour recoloured that window's switches and nothing else: every structural accent in the app reads `Ink.accent`, a fixed `systemBlue` chosen precisely so no machine can make it purple. And the requirement's own instruction — "default must mean `controlAccentColor`" — is the violation: on a Mac whose system accent is Purple, the *default* value of a control nobody touched painted the Settings window purple, which is exactly what `Ink.accent` refuses to do. A control that cannot do what it says and can only break the brand rule is deleted, not narrowed. `AccentChoice`, `Key.accent`, the published property and `accentColor` are gone; `Ink.accent` is the one accent, guarded by `InkAccentTests` over `BrandColourGuard` |
| I16 | Show Dock Icon toggle | DONE, **moved to General** — it decides whether the app has a second home besides the menu bar, which is the same question Launch on Login answers. `DockPresence` still owns the key, the default and the mapping |
| I17 | Timeline section with a LIVE preview reflecting the toggles below it | DROPPED (2026-08-16 report) with I18–I22 |
| I18 | Open externally toggle + `↵` hint | DROPPED (2026-08-16 report) — the timeline draws it always |
| I19 | Live Text toggle | DROPPED (2026-08-16 report) — the timeline draws it always |
| I20 | Zoom controls toggle + `⌘⇧+/−` hint | DROPPED (2026-08-16 report) — the timeline draws them always |
| I21 | Segment navigation toggle + `⌥←/→` hint | DROPPED (2026-08-16 report) — the timeline draws them always |
| I22 | Hidden controls keep their keyboard shortcuts working | DROPPED (2026-08-16 report) — vacuous once no control can be hidden. `RewindTests.TimelineControlVisibilityWiringTests` now checks the opposite direction: that no preference gate grows back over a control |

### I-Capture
| # | Requirement | Status |
|---|---|---|
| I23 | Screen Capture toggle | MISSING |
| I24 | Pause on Inactivity toggle | MISSING |
| I25 | Capture Quality: four tiles (Best / Default / Compact / Smallest), subtitle describes the selection | DROPPED (2026-08-16 report) — it was built and it genuinely worked (`FrameImage` resized and re-encoded to the selected tile), and the choice it offered was between one good answer and three worse ones: three of the four bought disk back by making the user's own screenshots harder to read, and — since `look` began handing frames to Claude as images — harder for a model to read too. The shipped Default is now the only answer, in `FrameImage.Quality`. `FrameLoader.maxPixelSize` stays at 2400 because frames written on Best Quality are still on disk |
| I26 | Footnote about quality vs disk space | DROPPED (2026-08-16 report) with I25 — there is no selection left to footnote |

### I-Storage
| # | Requirement | Status |
|---|---|---|
| I27 | Large header with REAL measured usage and "no storage limits set" | MISSING |
| I28 | Storage management radio group: Off / Compress / Limit | PARTIAL by decision (J7) — **Off / Limit only. `Compress` is dropped.** It shipped with a red destructive confirmation warning that "the original detail cannot be recovered", and then did nothing whatsoever: the retention sweep tests `strategy == .limit`, and no re-encoder exists anywhere in this package. A destructive-role warning in front of a no-op is worse than a missing feature — it teaches the user that this app's warnings are noise, and the next one really does delete. Building the re-encoder is a capture-pipeline change, not a Settings one; if it is ever built the case comes back with it. A persisted `"compress"` decodes to nil in both readers and falls back to `off`, so no migration was needed |
| I29 | Off is the default: "Keep all your data. Forever." | DONE — and it is the only strategy that destroys nothing |
| I30 | Limit deletes oldest recordings — needs a threshold control AND an explicit confirmation; never reachable by one stray click | DONE, with two corrections the requirement did not anticipate. **(a) Limit is two bounds, not one.** `ContextStore.enforceRetention` prunes by age *and* by bytes, and `Engine.ensureStorage` starts the sweep with 30 days, so turning Limit on deletes everything older than a month even at a 200 GB threshold on an 8 GB disk. For a release, no string the user could read said so — undisclosed permanent deletion of their data. The radio row, the header caption, the threshold row and the confirmation now all state it, from one constant (`StorageLimit.retentionDays`), pinned by `testEveryStringDescribingLimitDisclosesTheAgePrune`. **(b) The confirmation was ordering-dependent.** Its `isPresented` setter called `cancelStorageChange()` on every dismissal, and SwiftUI may write that binding before running the tapped button's action — which nulled the `pending` that `confirmStorage()` promotes, so the deliberate second click silently did nothing. Cancelling is now only the explicit Cancel button; `testConfirmingSurvivesEitherOrderOfBindingWriteAndButtonAction` drives both orderings through the pane's real binding |

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
| I39 | Websites: Exclude Private Tabs toggle | PARTIAL — Chrome/Edge/Brave/Firefox detected from title; **Safari and Arc cannot be detected at all**, so the copy must not overclaim. Arc was listed as covered and never was: measured across 925 Arc frames in the real database, all 13 distinct window titles are the bare page title (`Anthropic`, `LinkedIn`, `(9) Home / X`) with no browser chrome, so no `PrivateBrowsing.titleMarkers` entry can ever match. The one row matching "Arc" matched inside "Archit". `OpenExternally` documents the same titles from the other direction. The sentence is now built from two named lists so a browser cannot be moved between them in prose alone |
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
3. **The search bar answers in-app; only the tutorial hands off to Claude** — this reverses an
   earlier decision. The bar used to route what was typed into Claude and show nothing itself, which
   made every recall a round trip through another app. It now searches this app's own indexes and
   renders the hits. `ClaudeRouter` survives for the one act that is genuinely about Claude — the
   first-run hand-off (I9) — and for the Settings row that steers it.
4. **No second email capture** (E7); the Omi account already identifies the user.
5. **Update controls exist exactly as far as the updater does** (I7). They were omitted while there
   was no updater; there is one now, so `Check Now` is real — and it disappears again on any build
   `UpdatePolicy` refuses, which is every locally signed one. The rule was never "no update
   controls", it was "no control that cannot do what it says".
6. **Safari *and Arc* private windows are not excludable** from the window title alone (I39); the
   seam exists for AX to fill. Arc's titles carry no browser chrome at all — measured, not assumed.
7. **Three reference controls are deleted rather than implemented** (I8 Route to Agent, I15 Accent
   Colour, the Compress case of I28). Each had shipped as a control the user could operate that
   changed nothing, and Compress said so behind a red destructive warning. J7 rules out controls that
   cannot work, and it applies to controls that already exist as much as to ones not yet written: a
   dropdown nobody reads is the same fabrication as a fake screenshot, just harder to notice.
8. **Exclusions cover screen capture only.** `ScreenWatcher` is the sole caller of
   `ExclusionEngine.admit`/`revalidate`; no audio source consults the engine. Excluding an app
   suppresses its screenshots, OCR, window title and accessibility text and leaves microphone and
   system-audio transcription running. The pane says so above the list — on a privacy surface, an
   unstated boundary is the failure — and names Pause, which is what does stop audio.
