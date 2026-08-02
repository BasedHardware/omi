# First-Run Experience — Plan

**Premise: the search bar is Claude.** This app ships no search panel, no scrubbable timeline, and
no global hotkey. Every retrieval surface is Claude, reached over MCP. First run therefore has four
jobs, in order: look unmistakably good, take consent honestly, register with Claude, and then prove
the whole thing works by getting a real answer out of Claude.

Anything that would fake a retrieval UI inside this app is out of scope by definition — it would be
teaching a surface that does not exist.

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
  1x and 2x: mark + wordmark top-left, "Drag Context for Claude into Applications to install", and an
  arrow between the two icon positions. Extract the icon art with `sips` from the `.icns` first
  (ImageMagick reads `.icns` unreliably).
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
720×520 floating card (`OnboardingWindow.swift:17,44-54`); the cinematic needs a full-screen variant
on the display under the pointer, then it shrinks back to the card for Phase 4.

Beats, each with its own sound:

1. **Dim** — desktop darkens over ~0.6 s, music fades in.
2. **Build the mark** — the restored mark draws itself on (head, then eyes, then legs), wordmark
   resolves after it. This is the moment the app introduces itself, so it holds for a beat.
3. **Collapse to a bar** — mark and wordmark morph via matched geometry into a single horizontal bar.
4. **Stretch into a prompt** — the bar widens into a prompt field with the mark at the left and a
   caret; a question types itself ("what was I working on today?"). Swoosh on the stretch.
5. **Windows swoosh in** — a swarm of window cards flies in from off-screen on staggered swooshes and
   settles into a grid. These render the user's **real** recent captured frames when any exist, and
   fall back to neutral placeholders on a fresh install — never fabricated screenshots of fake apps.
6. **Recede** into the welcome card.

Constraints: `Esc` and a visible "Skip intro" abort at any point; `InkReduceMotion` (already present)
collapses every motion beat to a cross-fade; the whole sequence must be idempotent and never run
again once `context.onboarded` is set.

---

## Phase 4 — Onboarding cards

`welcome → value → sign in to Omi → permissions → connectors → tutorial intro`, with progress dots
and click sounds. Reuses the existing `Step` machine (`OnboardingView.swift:15-17`, currently
`intro, value, connector, signIn, setup, done`) — sign-in and connector registration already work and
are not rebuilt, only restyled onto the Phase 0 palette.

---

## Phase 5 — Permission choreography

**macOS 26 draws the drag affordance itself.** The dashed row and "Drag this row up into the list"
arrow are System Settings' own UI on 26.x — no app can draw inside that window. So we guide and
highlight the real thing; we never redraw or simulate it as though it were ours.

1. Our card plays a small animated replica first — a ghost row rising into a list — so the user
   recognises what they are about to be shown.
2. We open the exact pane (`Permissions.swift:32-45` already has the per-capability URLs), then locate
   the System Settings window and the drag-target row through the Accessibility API
   (`Capture/AXElement.swift` already wraps AX), and draw a floating overlay: a pulsing ring plus an
   animated hand pointing at the real row.
3. The row shows a live "waiting" state that flips to a checkmark the instant TCC reports the grant,
   with `chime.wav`. Screen Recording additionally needs the existing relaunch nudge, because the
   window server only honours the grant in a new process.

Permissions stay one-at-a-time with the existing lead-in/after-grant pacing
(`OnboardingView.swift:592-596`) — that pacing was a deliberate earlier fix and is not to be undone.

---

## Phase 6 — The tutorial, which ends inside Claude

1. **"Learn how this works"** card — Start / Skip.
2. **Collect frames.** Open a Wikipedia article, with a coach mark: "Scroll around and collect your
   first frames." A **live counter reads our own store** — real frames, not a timer pretending.
3. **"Your screen is now searchable."** Only shown once frames actually landed.
4. **Hand off to Claude.** Explain that Claude reads its MCP config at startup and must be restarted;
   offer a button that relaunches Claude Desktop, shows the `claude` CLI equivalent, and puts a
   suggested question on the clipboard.
5. **Prove it.** The MCP server writes a last-query timestamp into the data directory; the app watches
   for it, so "Found it" appears only when Claude has genuinely called one of our tools. This is the
   payoff beat, and it is earned rather than staged.
6. **"You're all set"** → `MenuBarSpotlight.show()` for "one more thing — I live up here."

No shortcut-conflict step: we register no hotkey, so there is no conflict to warn about. Adding a fake
one would be theatre.

---

## Verification

- `swift test` — 146 tests today; new behaviour adds tests (pid exclusion, sound gating, step machine).
- `scripts/build.sh` then a genuinely cold run: `tccutil reset All com.omi.context-for-claude`,
  `defaults delete com.omi.context-for-claude`, delete the Keychain session, clear both MCP
  registrations. **Reset TCC only while the app is installed** — `tccutil` resolves bundle ids through
  LaunchServices and grants survive uninstall, so resetting after deleting the app silently restores
  the old grants on reinstall.
- Screenshot every beat and compare against the reference; the menu bar gets a side-by-side against a
  real system menu.
- `python3 scripts/eval.py` must not regress — it scores MCP answer honesty and is unrelated to this
  work, so any movement means something leaked.

## Explicitly out of scope

A scrubbable rewind timeline, an in-app search panel, and a global hotkey. The search bar is Claude.
