# First-Run Experience — Plan

**Premise: the app has a front door, and Claude reads the same store through it.** First run has
four jobs, in order: look unmistakably good, take consent honestly, register with Claude, and then
prove the whole thing works — by walking the user through the app's own surfaces and finishing on a
real answer out of Claude.

The rule underneath all of it is unchanged and is the only one that matters: **first run may not
teach a surface or a gesture the app does not have.** What changed is which surfaces those are, and
this document had it backwards for a release — see below.

## What the app actually ships now, and what this document used to claim

This plan was written against a product with no retrieval UI of its own. Its original premise —
*"the search bar is Claude. This app ships no search panel, no scrubbable timeline, and no global
hotkey"* — is false in all three clauses, and it is recorded here rather than deleted because every
stale instruction further down descends from it.

- **The Activity spine is the main surface.** A chronological, day-grouped feed of conversations,
  memories, tasks and screen moments, with a filter chip row (`All · Conversations · Memories ·
  Tasks · Rewind`) and an hour rail. It answers inside the floating panel *before anything is typed*,
  so it is what the app opens on (`Activity/ActivitySurface.swift`, `Search/SearchBarView.swift`).
- **Conversations, memories and tasks come from the user's Omi account**; screen moments are local.
  An unreachable account is an ordinary state the surface distinguishes from an empty one, so the
  value card's consent line has to name the account as something the *user* reads back too, not only
  Claude (`OnboardingView.valueClaims`).
- **Two global chords, both rebindable.** `⌘ + ⌘` — both physical Command keys together, not a
  double tap — opens Activity; `⌘⌘⇧` toggles the same surface. The action is `GlobalShortcuts.Action
  .openActivity`, renamed from `openTimeline` when the window behind it changed, with the *persisted*
  identifier deliberately left as `openTimeline` so recorded bindings survive (`Action.storageKey`).
  Neither chord fires without Accessibility, which is the one permission this flow lists and never
  requires — so any copy naming a chord must ask `GlobalShortcuts.readiness` first.
- **The timeline is not the landing screen.** It is reached from the `Timeline ⌘T` pill in the
  panel's header, from the menu bar's "Open Timeline" row, or by activating a moment. Settings is the
  gear in the same header, and the menu bar.
- **The panel is a Spotlight panel**: borderless, non-activating, key without pulling the app
  forward, gone on Escape.

---

## Phase 0 — Un-Anthropic the brand, and make the menu bar native

The current look is Anthropic's, not ours, and the menu bar is the worst offender.

| # | Change | Where |
|---|---|---|
| 0.1 | Stop forcing `NSApp.appearance = .aqua`; follow system appearance | `ContextApp.swift:49` |
| 0.2 | Restore the original template mark | `MenuBar/ContextMark.swift` ← `git show 2920115b85:desktop/context-for-claude/Sources/ContextApp/MenuBar/ContextMark.swift` |
| 0.3 | Menu-bar panel to native metrics | `MenuBar/StatusView.swift`, `Ink.swift:638-643` |
| 0.4 | Replace the Anthropic palette + serif display | `Onboarding/Ink.swift:57-108`, `315-358`, `420-467` |

**0.1 is the root cause of "colors look so off."** Forcing `.aqua` app-wide renders the popover light
while the surrounding system menu is dark. Delete the override; the popover already uses native
semantic colors and will then match.

**0.2** The geometry never changed across the restyle — head, two oval eyes, two curved legs. The
original set `NSColor.black` + `image.isTemplate = true`, so macOS auto-inverted it per menu-bar
appearance and dimmed it when inactive. The current one hardcodes clay `#D97757` and
`isTemplate = false`. Restoring the template is the whole fix.

**0.3** A native menu has no filled row capsules, no custom letter-spacing, ~22pt rows, and no card
padding. Drop `InkPermissionRow(native:)`'s `quaternaryLabelColor.opacity(0.5)` fill, drop `.inkStyle`
tracking on this surface, use `Divider()`, and let the row heights be system-standard. Evaluate
replacing the `NSPopover` with a real `NSMenu` containing `NSHostingView` rows — an actual menu is
the only thing that reads exactly like a menu.

**0.4** The palette is literally Anthropic's — `paper #FAF9F5`, `ink #141413`, `bronze #D97757` (the
source comments call it "Anthropic clay") — plus system serif (New York) for every role ≥22pt.
Replacement direction:
- **Accent:** `NSColor.controlAccentColor` — the user's own chosen accent. Maximally native, and
  definitively not a borrowed brand. Never purple (`INV-UI-1`).
- **Neutrals:** system semantic colors (`labelColor`, `secondaryLabelColor`, `separatorColor`,
  materials) instead of hand-mixed paper/ink.
- **Display type:** Open Runde, already bundled at `Resources/Fonts/OpenRunde-*.otf` and currently
  orphaned by the serif switch. Geometric, distinctive, ours. Body stays SF Pro.
- The mark itself goes back to template black/white (0.2), so it inverts correctly everywhere.

`Resources/ContextForClaude.icns` was never touched by the restyle commits and still carries the old
palette — regenerate it from the restored mark.

---

## Phase 1 — Audio, synthesized so it is license-clean

No UI sound infrastructure exists today (zero `NSSound`/`AVAudioPlayer`/`AudioServices` hits). No
music will be downloaded; every asset is generated on this machine, so there is nothing to license.

**Generator** — `scripts/make-sounds.py`, numpy + stdlib `wave`, 48 kHz (matches Core Audio, no
resample), 16-bit PCM into `Resources/Sounds/`:

- **`pad.wav`** — ambient bed, 60–90 s, stereo. Four sine partials (C3 130.81, G3 196.00, C4 261.63,
  E4 329.63) each doubled by a quiet triangle octave, pairs detuned ±3–5 cents, panned ±15–20%.
  Envelope A3s/D1s/S0.7/R4s plus a 0.05–0.1 Hz amplitude LFO. Pseudo-reverb: feedback delay 350–450 ms
  with a 180 ms tap, feedback 0.35–0.45, wet 25–30%, low-pass the feedback path at 4–6 kHz.
  Crossfade the last 2 s into the head so `numberOfLoops = -1` loops seamlessly. Peak −6 dBFS.
- **`swoosh.wav`** — 250–400 ms. White noise through a band-pass (Q 2–4) swept 400 Hz → 3–4 kHz via
  overlap-add STFT magnitude shaping (20–50 ms windows), with a quiet 150→600 Hz chirp underneath.
  Attack 10–20 ms, skewed-Hann hump peaking ~40% in, exponential decay. Peak −8 to −10 dBFS.
- **`click.wav`** — 40–80 ms. 1 kHz tick + quieter 300–400 Hz body, pitch bending 1000→700 Hz.
  Attack 1–3 ms, fast exponential decay, no sustain. Mono, peak −12 dBFS (it repeats constantly).
- **`chime.wav`** — success cue for a granted permission and for the final "all set".

**Playback** — `Sources/ContextApp/Support/Sound.swift`:
- Music: one `AVAudioPlayer`, `numberOfLoops = -1`, `setVolume(_:fadeDuration:)` for fades — never a
  hard cut.
- SFX: `AVAudioEngine` + a pool of `AVAudioPlayerNode`s with preloaded `AVAudioPCMBuffer`s, so rapid
  clicks overlap without allocation latency.
- Chrome sounds (click, swoosh) honour the system setting, read via
  `CFPreferencesCopyAppValue("com.apple.sound.uiaudio.enabled", "com.apple.systemsound")`. Neither
  `AVAudioPlayer` nor `AVAudioEngine` respects it automatically. The cinematic bed is content, not
  chrome, and is gated by its own explicit mute control instead.

**Bug fix that ships with this phase.** `Capture/SystemAudioCapture.swift:131,411` builds its tap as
`CATapDescription(stereoGlobalTapButExcludeProcesses: [])` — an empty exclude list, i.e. a global tap
that records *every* process including this one. Onboarding music and swooshes would land in the
user's own transcripts. Fix: exclude our own pid unconditionally, for the whole process lifetime, not
just during onboarding — clicks can fire from Settings while a capture session runs.

**The obvious one-line fix is wrong and was corrected during implementation.** An earlier revision of
this document recommended:

```swift
// WRONG — does not compile, and would not have worked if it did.
CATapDescription(stereoGlobalTapButExcludeProcesses: [pid_t(ProcessInfo.processInfo.processIdentifier)])
```

`stereoGlobalTapButExcludeProcesses` takes `[AudioObjectID]` — CoreAudio process *object* IDs, which
are not pids. Passing a pid therefore reads as a fix while our own audio keeps landing in the tap
(measured on this machine: pid 77685 is object 164). The real fix translates first, via
`kAudioHardwarePropertyTranslatePIDToProcessObject`, and both tap sites go through one factory so
they cannot drift apart.

Two tests, not one:
- The exclude list is non-empty and contains our own process object. Prove it by reverting the fix and
  watching the test fail — an assertion that passes against both the broken and fixed code is not a
  regression test.
- `isExclusive == true` and `muteBehavior == .unmuted`. Flipping `exclusive` inverts the list's meaning
  into "record only us", which would be a far worse bug than the one being fixed and would otherwise
  pass the first test.

If the pid-to-object translation fails, the implementation logs and falls open (an empty exclude
list) rather than refusing to capture. That is a deliberate trade: the exposure is limited to this
app's own UI sounds, whereas failing closed would silently disable the product's core function.

---

## Phase 2 — A real drag-to-install DMG

`scripts/package-dmg.sh:79-91` currently emits a plain `UDZO` straight from a staged folder. The
`/Applications` symlink is already there; nothing else is styled.

- **`scripts/make-dmg-background.sh`** — ImageMagick (installed, 7.1.1-47) renders the background at
  1x and 2x: wordmark top-left, "Drag Context for Claude into Applications to install", and an arrow
  between the two icon positions. **No mark.** It shipped with the app's glyph lifted out of the
  `.icns` at the top left, which put the mark on screen twice — Finder draws the real app icon in the
  left-hand slot 130 pt below it, and that icon is the thing the window exists to have dragged. A
  second, smaller copy of it is a decoy, not branding.

  **The corridor stays an arrow, and that is a platform limit rather than a preference.** A dotted arc
  with a translucent tile in flight along it was built and then reverted, because what was actually
  wanted was *"a continuous animation of the app being dragged into Applications"* — and no disk image
  can deliver one. Finder takes the window background from a static image path recorded in `.DS_Store`
  and draws it once, so a GIF or a video renders as a single frame; macOS has not auto-run anything
  from a mounted volume in many years, so there is nothing on a DMG that could drive motion without
  the user launching it first. A still frame implying movement is a *worse* answer to that request
  than an arrow, because it invites the same ask again. Anything that genuinely animates has to run
  code the user started: an installer app on the image (a Gatekeeper prompt and a second signed
  binary), or the app moving itself out of `/Volumes` on first launch. Neither is in scope here, and
  both leave this window as it is.
- **`package-dmg.sh`** gains the standard styling dance, no new dependency (`create-dmg` is *not*
  installed and is not worth adding): `hdiutil create -format UDRW` → `hdiutil attach -readwrite
  -noverify -noautoopen` → drop `.background/background.png` + `.VolumeIcon.icns`, `SetFile -a C` the
  volume → Finder AppleScript → `hdiutil detach` → `hdiutil convert -format UDZO`.
- AppleScript must set: `open` the disk, icon view, toolbar/statusbar hidden, `bounds` of container
  window, `icon size 128`, `arrangement ... not arranged`, `background picture ... file
  ".background:background.png"`, explicit `position of item` for the app and for `Applications`,
  then `update without registering applications`, a `delay`, `close`.
- Gotchas: the volume must be **open in Finder**, not merely mounted, before positions can be set;
  `arrangement` must be `not arranged` or Finder re-snaps to a grid and discards positions; the
  background path must be a relative alias, not absolute; the image must be fully **detached** before
  `convert`; first run needs Automation permission for the shell to drive Finder, so detect and fail
  loudly rather than hang.

---

## Phase 3 — The first-run cinematic

One borderless transparent window over a dimmed desktop. `OnboardingWindow` is currently a fixed
720×640 floating card (`OnboardingWindow.swift`, `cardSize`); the cinematic needs a full-screen variant
on the display under the pointer, then it shrinks back to the card for Phase 4.

Beats, each with its own sound:

1. **Dim** — desktop darkens over ~0.6 s, music fades in.
2. **Build the mark** — the restored mark draws itself on (head, then eyes, then legs), wordmark
   resolves after it. This is the moment the app introduces itself, so it holds for a beat.
3. **Collapse to a bar** — mark and wordmark morph via matched geometry into a single horizontal bar.
4. **Stretch into a prompt** — the bar widens into a prompt field with the mark at the left and a
   caret; a question types itself ("what was I working on today?"). Swoosh on the stretch.
5. **Windows swoosh in** — a field of window cards flies in from off-screen on staggered swooshes,
   settles into a grid, and then floats: each window on its own long period, with a resting tilt and
   a parallax that follows its resting scale. The windows are **synthetic and identical on every
   run** — generic app windows drawn from `CinematicWindowArt.swift`, never the user's captured
   frames and never a fabricated screenshot. That file's types carry numbers only and no view in it
   can draw text, so a window cannot name an app, a person, or a message. See the header of
   `CinematicWindows.swift` for why the real-frames path was removed rather than kept as a fallback:
   first-run stores are empty by construction, so the fallback *was* the shipping path.
6. **Recede** into the welcome card.

Constraints: `Esc` and a visible "Skip intro" abort at any point; `InkReduceMotion` (already present)
collapses every motion beat to a cross-fade; the whole sequence must be idempotent and never run
again once `context.onboarded` is set.

---

## Phase 4 — Onboarding cards

`welcome → value → sign in to Omi → permissions → connector → tutorial intro → done`, with progress
dots and click sounds. The machine is `OnboardingStep` (`OnboardingView.swift`), and it is a value
with pure `itinerary` / `next` / `back` / `progressSteps` functions rather than a private enum inside
the view, because the ordering is the part with wrong answers available and a `View` cannot be
asserted against.

- **Sign-in comes before permissions, deliberately.** Everything recorded lands in an Omi account and
  the permissions are what start the recording, so the account has to be known before macOS is asked
  for a microphone. A restored session drops `.signIn` and nothing else.
- **Back is refused from `.permissions` onward.** TCC shows each prompt exactly once and will not
  un-ask, so a card reached backwards could not do anything.
- **Both exits from the last card seal the run.** `.done`'s `finish()` and the tutorial hand-off both
  call `sealTheRun()` — login item, `context.onboarded`, `OnboardingResume().clear()`, music stop.
  The hand-off used to skip all four, so taking the walkthrough left the install un-onboarded and put
  the card back up on the next launch.
- **A resume point is corrected to this run's itinerary** (`OnboardingStep.resumed`). The record holds
  a card; the itinerary is rebuilt at launch from whether a session was restored, so the two can
  disagree — a run that recorded `.signIn` and came back with an account already restored would open
  on the one card that run does not have, asking somebody signed in to sign in again.
- **The `done` card names both ways in**: the menu bar (rung by `MenuBarSpotlight` while the line is
  on screen) and the chord, printed from `GlobalShortcuts` and omitted when it is not armed.
- **The `done` card always watches for the screen grant, and only sometimes opens the pane**
  (`OnboardingFinale`). Those were one condition and it stranded a run: the ungranted card's only
  control was "Open Screen Recording", and the watch was armed only for a run that had *not*
  postponed the screen row — so a user who pressed "I'll do these later" reached a last card that
  could not notice a grant and had no button that could close it, in a borderless window with no Dock
  icon behind it. A deliberate "later" now closes the flow; the watch runs whenever the grant is
  missing, however it came to be missing.
- **The Accessibility row never says "Allow"** (`OnboardingView.statusWord`). macOS has no dialog for
  it at any point — `Permissions.request(.accessibility)` opens the pane — so the word is
  "Open Settings" from the first frame rather than after a click that spends a prompt which does not
  exist.

---

## Phase 5 — Permission choreography

**macOS 26 draws the drag affordance itself.** The dashed row and "Drag this row up into the list"
arrow are System Settings' own UI on 26.x — no app can draw inside that window. So we guide and
highlight the real thing; we never redraw or simulate it as though it were ours.

1. Nothing rehearses inside our card. The in-card ghost replica is gone: it made the user press
   "Show me the row" before anything happened, which is our UI standing in front of the actual task.
   The guidance now just appears, on the real window, when the capability needs it.
2. We open the exact pane (`Permissions.swift:32-45` already has the per-capability URLs), then locate
   the System Settings window and the drag-target row through the Accessibility API
   (`Capture/AXElement.swift` already wraps AX), and draw a floating overlay: a pulsing ring plus an
   animated hand pointing at the real row.
3. The row shows a live "waiting" state that flips to a checkmark the instant TCC reports the grant,
   with `chime.wav`. Screen Recording additionally needs the existing relaunch nudge, because the
   window server only honours the grant in a new process.

**The rows, in the order the card lists them: screen, Accessibility, microphone, system audio.** The
required subset is microphone, system audio and screen; Accessibility is listed and never required,
because macOS has no dialog for it and gating the card on a switch flipped by hand would strand
anyone unwilling to leave the flow. Screen goes first because the two row locators each need the
other's grant, and granting the screen is what makes every later pane's row findable — the full
argument is on `PermissionInvitations.listed`, which is the one owner of both lists. Nothing else may
restate the order; a copy of it in `OnboardingView` outlived the ordering it described by a rewrite.

Permissions stay one-at-a-time, and the lead-in/after-grant pacing inside an episode survives — that
pacing was a deliberate earlier fix and is not to be undone. What *is* undone is the **automatic
sequencing** around it: the card no longer asks for anything on its own. Each capability is a row the
user clicks, and only that click starts its episode (`PermissionInvitations.swift`). The pacing was
never the problem; spending it on prompts the user had not asked for was, because the dialog landed
before the sentence explaining it could be read.

---

## Phase 6 — The tutorial, which walks the app's own surfaces and ends inside Claude

**Eleven beats, and `TutorialStep.flow` is the list.** It was six when this section was written, all
of them either a card or Claude, because the app had no surfaces of its own to walk. Four of the
current eleven — `openActivity`, `timeline`, `findMoments`, `query` — are this app's own windows.
Onboarding's `.tutorial` card is what offers it, and its aside has to describe *this*, not the
one-minute hop to Claude the flow used to be.

1. **`invitation`** — "Let me show you what I do", Start / Skip.
2. **`screenAccess`** — Screen Recording, asked for here and only if it is genuinely missing.

   **A grant and a grant *in force* are different facts, and the flow reads both**
   (`TutorialEnvironment.screenNeedsRelaunch`). macOS decides what a program may capture when that
   program connects to the window server, so a grant taken while this app is running preflights as
   granted and captures nothing until the app starts again. That is the ordinary first run rather
   than an edge: onboarding's permissions card is where the grant is normally taken, and the tutorial
   hand-off leaves from the card *before* the one that offers the relaunch. Untested, the walkthrough
   thanked the user for sight it did not have and then sat the capture beat out its full 45 s patience
   waiting for frames that physically could not arrive, under a card telling them to keep scrolling a
   page it had opened for them. The beat now says why, opens no page, and offers the way past at once
   — the same treatment an unarmed chord and an unopened timeline already get — and `TutorialOutcome`
   carries the reason through to the closing card as `.cannotSeeYet`.
3. **`collectFrames`.** Open `anthropic.com/research` — Claude's own site, the one this app can put on
   somebody's screen without choosing a third party's content for them, and the page on it there is
   enough of to scroll — and ask them to scroll it. The home page is short and largely static, and
   capture dedupes perceptually, so scrolling it to the end produced very little for the gate.
   The gate **reads our own store** (`TutorialGate.realFrames`): real frames, not a timer pretending.
   The count is not narrated; the card says "Scroll through it for a bit" and then "Got it", and it
   claims the page was opened only when `NSWorkspace` says it really was.
4. **`openActivity`** — the chord, taught the only way a chord can be taught: the user presses `⌘ + ⌘`
   and the real Activity panel opens *because they did*, gated on the real shortcut really firing
   (`TutorialGate.realHotkey`). This beat was `openTimeline` and taught the chord as the way to the
   timeline. It is not, and the beat followed the behaviour rather than keeping the old lesson.
5. **`timeline`** — the drag through a captured day, which is the moment the product becomes obvious.
   The tutorial **opens that window itself** and says so, because the chord no longer does; the
   travelling still has to be the user's (`TutorialGate.realGesture`).
6. **`findMoments`** — the real "Search All" pill, gated on the real search panel being on screen.
7. **`query`** — type into the real search bar and click the real hit to travel to it. **Deliberately
   not Return**: in the panel that key hands the question to Claude and closes the surface the beat is
   being conducted in, so a card coaching it would coach the one keystroke that ends its own lesson.
   The results narrow as they are typed, so there is nothing to submit; the gate is a real answer to a
   real question (`TutorialGate.realSearchResult`), which is the one gate in the flow that cannot be
   waived.
8. **Hand off to Claude — by doing it.** Direct user instruction: "Open claude for me and type the
   first thing in." The tutorial routes the suggested question through `ClaudeRouter` as
   `claude://claude.ai/new?q=…`, which lands it in the composer of a **normal new chat**. The prompt
   is **pre-filled, not sent** — pressing Return stays the user's. Every branch that could not
   pre-fill says so instead: no `claude://` handler falls back to the clipboard, and no Claude Desktop
   at all is its own admission (`TutorialClaudeAsk`).

   **The surface is named at the call site** (`ClaudeHandoff.surface`), because Claude has two and
   they are not interchangeable: `claude://claude.ai/new` is an ordinary chat and `claude://code/new`
   is the Claude Code tab. This beat shipped on the second one, inherited from the search bar back
   when the bar was the thing that routed to Claude, and dropped the user into the Code tab
   mid-tutorial. Either surface can answer (`ClaudeRegistrar` writes the MCP entry into both
   configs); only one of them is where a person asks a question.

   **The *target* is the user's, not the call site's.** `Settings → Agents → Claude target` picks the
   Claude app or the `claude` CLI, and this handoff is what that dropdown steers — `ClaudeHandoff`
   reads `SettingsStore.claudeTarget` as it hands over, and the CLI branch answers
   `TutorialClaudeAsk.ranInTerminal` rather than pretending a composer was filled. On that target no
   restart is ever offered: a `claude` process is new every time and reads `~/.claude.json` as it
   starts, so quitting the Claude the user is reading would cost them a session and fix nothing.

   **The restart is conditional and consented.** Claude reads its MCP config at startup, so a Claude
   open from *before* we registered cannot call our tools — but that is a conditional justification
   and `ClaudeHandoff` tests the condition rather than assuming it: `launchDate <=
   ClaudeRegistrar.claudeDesktopRegisteredAt`, with either date missing answering "no restart". A
   Claude launched after we wrote already has us and is never touched. When a restart genuinely is
   needed the card *asks* ("Claude is open already… May I close and reopen it?") with a real second
   choice — declining still hands the question over and the copy says the reach may be stale, which
   beats quitting somebody's conversation to force a gate. What comes back reports what happened, so
   an app that refuses to quit is `restarted: false`.
   **The card gets out of Claude's way, without leaving.** Reported in one sentence — *when it opens
   the Claude window, the flow window blocks the view*. Both beats take `TutorialPlacement.clearOfClaude`,
   and `TutorialOverlay.parked` puts the card in whichever band around Claude's real window has room
   (beside it, then above, then below, then the top trailing corner when a full-screen Claude leaves
   nothing clear — never the bottom, where the composer is). Claude's frame comes from
   `ClaudeWindowProbe`, which reads `CGWindowListCopyWindowInfo` and so needs no grant, and it is
   re-read every tick because Claude opens *after* the card and the user can move it.
9. **Prove it** (`claudeProof`). The MCP server writes a last-query timestamp into the data directory;
   the app watches for it, so "Found it" appears only when Claude has genuinely called one of our
   tools. This is the payoff beat, and it is earned rather than staged. It is also the one card that
   **must not take the keyboard** (`TutorialStep.takesFocusOnEntry`): the tool call happens when the
   user presses Return in Claude's composer, and an accessory app activating over Claude eats exactly
   that keystroke.
10. **`allSet`** — "That's everything", and the one sentence that says what the capture beat really
    achieved. This absorbed the old standalone "Your screen is now searchable" card.
11. **`menuBar`** — "one more thing — I live up here", with `MenuBarSpotlight.show()`.

**The shortcut-conflict step is back in scope.** This section used to end "we register no hotkey, so
there is no conflict to warn about. Adding a fake one would be theatre." Two chords are registered
now (`⌘ + ⌘` and `⌘⌘⇧`), both rebindable, and `ShortcutConflicts` exists to report a collision with
another tool's binding. It is surfaced in Settings rather than as a first-run card — a conflict
notice in front of someone who has not yet used either chord is a warning about nothing — but the
justification for having no such step is no longer "there is no hotkey".

---

## Verification

- `swift test --package-path desktop/context-for-claude` — 1123 tests today (was 146 when this plan
  was written); new behaviour adds tests (pid exclusion, sound gating, step machine).
- `scripts/build.sh` then a genuinely cold run. A local build is signed with a developer
  certificate, so it carries the **developer** identifiers and those are the ones to reset —
  `tccutil reset All com.omi.context-for-claude.dev`, `defaults delete com.omi.context-for-claude.dev`,
  delete the Keychain session, clear both MCP registrations (`context-for-claude-dev`). Resetting
  the release identifiers instead would destroy the installed app's grants and leave the build under
  test untouched. **Reset TCC only while the app is installed** — `tccutil` resolves bundle ids through
  LaunchServices and grants survive uninstall, so resetting after deleting the app silently restores
  the old grants on reinstall.
- Screenshot every beat and compare against the reference; the menu bar gets a side-by-side against a
  real system menu.
- `python3 scripts/eval.py` must not regress — it scores MCP answer honesty and is unrelated to this
  work, so any movement means something leaked.

## Explicitly out of scope

This section used to read: *"A scrubbable rewind timeline, an in-app search panel, and a global
hotkey. The search bar is Claude."* All three shipped. They are named here only so nobody reads the
sentence above as still binding.

What remains out of scope is the rule the sentence was an instance of: **first run may not teach a
surface or a gesture the app does not have, and may not stage a result it did not get.** Every
tutorial gate is still a real one (`TutorialGate`), the cinematic's windows are still synthetic
(`CinematicWindowArt`), and no card may claim a chord `GlobalShortcuts.readiness` says is not armed.
