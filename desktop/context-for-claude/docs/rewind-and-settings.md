# Rewind + Settings — Spec

Transcribed from reference screenshots of Coast Local. This file is the **only** record of those
images: implementers cannot see them, so treat every value here as the requirement. Where a detail
is absent, it was not visible in the reference and is an implementer decision — say so rather than
inventing a "reference" for it.

Two corrections to `first-run-experience.md` that this spec supersedes:

1. **The search bar is real UI that routes to Claude.** It is not a fake, and it is not a competing
   retrieval engine. You type a query; it hands the query to Claude (pre-filled Claude Code tab, or
   the `claude` CLI). "The search bar is Claude" means the *answer* comes from Claude, not that no
   bar exists.
2. **The shortcut-conflict warning is back in scope.** `first-run-experience.md` says a conflict
   notice would be theatre because the app registers no hotkey. Once `⌘⌘` and `⌘⌘⇧` are registered
   that reasoning no longer holds, and conflict detection becomes a real feature (see General pane).

---

## Part 1 — Rewind (the timeline window)

**Port, don't reinvent.** The Omi desktop app at `/Users/architlal/Documents/omi/desktop/macos/`
already implements Rewind. Capture in this package was already ported from there rather than
rewritten (see `README.md`), so Rewind follows the same precedent: copy and adapt into
`desktop/context-for-claude`, keeping this package standalone — it shares no code or data with the
Omi desktop app, so a port means a real copy, not a dependency.

### Window chrome
- Large window, rounded corners, translucent light chrome. Centered header title — Coast uses
  "Coasting"; ours should use our own word for the mode, not theirs.
- **Top-left:** a "Search All" pill showing its shortcut hint `/`, plus a gear button that opens
  Settings.
- **Center:** the captured frame, large, with a colored border keyed to the current segment.
- **Frame edges:** `‹` and `›` chevrons for previous/next segment, sitting on the left and right
  edges of the frame itself.
- **Bottom-left over the frame:** a date/time pill with a calendar icon, e.g.
  `Jul 29, 2026 at 10:21 PM`, with a `▾` disclosure that opens a picker.
- **Bottom-right over the frame:** four circular buttons, in order — globe (open externally),
  live-text (scan), zoom out, zoom in.
- **Bottom:** the timeline track — a horizontal bar of colored segments (color derived per app), with
  circular app-icon badges pinned at their positions along the track, and a light playhead handle.

### Behaviour
- Scrubbing the track moves the frame; scrolling left moves back in time.
- Segment colors are derived from the app that owned the frame, so the track reads as a day's shape
  at a glance.
- Zoom controls zoom the **track**; `⌘ +` / `⌘ −` zoom the **frame image** instead. These are two
  different zooms and must not be conflated.
- **A trackpad pinch over the track zooms it too**, and is the discoverable way in — the buttons are
  easy to miss. Pinch out to zoom in (a shorter span across the same width, finer granularity); pinch
  in to zoom out. The span clamps to 120 s at one end and the loaded day at the other.
- Pinch and the buttons drive **one** zoom state (`RewindZoom` → `RewindModel.setTrackWindow`), so the
  two can never disagree. They differ only in what they pin: a pinch holds the instant under the
  pointer at the pointer's own fraction of the width, the buttons hold the playhead.
- "Open externally" opens the webpage, file, or folder captured in that frame; its icon adapts to
  what the frame actually contains.
- "Live Text" highlights selectable/copyable text detected in the frame, and dims when no text has
  been detected yet.

---

## Part 2 — Settings

A standard macOS settings window: left sidebar with rounded selection, header reading "Settings" with
the current pane name beneath it. Five panes, each with an SF Symbol: **General** (gear), **Agents**
(terminal prompt), **Capture** (record circle), **Storage** (drive), **Exclusions** (eye with slash).

The window opens at the **timeline's own rectangle** (`RewindWindow.defaultSize`, 1180 × 760, minimum
820 × 560) rather than at a size of its own. The two windows already shared their chrome, ground and
corner radius; a different size was the one thing left making them read as different objects.

### Controls this app deliberately does not offer

**Seven rows are gone**, listed below. Each was removed on a report, and none was narrowed — a
control the user cannot find is still a control that fires.

| Removed | Where it went, and why |
|---|---|
| **The whole Appearance pane** | Theme tiles overrode the machine's own Appearance setting inside one app; the timeline-control toggles were four ways to make the timeline worse (they are now always drawn). **Show Dock Icon** moved to General — it was never an appearance choice. |
| Open Search Shortcut | A second chord (`⌘⌘⇧`) onto the *same* window `⌘ + ⌘` opens: `ContextApp.shortcutFired` answered both with one `window.press()`. Removed from the shortcut layer too, not just the pane. |
| The standalone Accessibility row | It appeared under the recorders when the grant was missing and offered a pane this app was not listed in. Replaced by `GlobalShortcuts.askForAccessibility()`, which raises the real system alert — that is also what puts the app in the list. The recorder's own subtitle still says when a chord cannot fire. |
| Airgap Mode toggle | The switch, not the promise: `ExclusionEngine` still carries the flag and `NetworkEgress` still enforces it for anyone whose `exclusions.json` has it set. |
| Sound toggle | The cinematic carries its own mute button, which is the surface where music is actually playing. |
| Capture Quality tiles | Three of the four tiles bought disk back by making the user's own screenshots harder to read — and, since `look` hands frames to Claude as images, harder for a model to read too. What every install shipped on is now what every install gets (`FrameImage.Quality`). |
| Agents ▸ "Detected on this Mac" | A read-only survey of Claude/Codex/Cursor that nothing acted on, in the pane where the two controls that do something live. |

Every row follows one pattern: a rounded icon tile on the left, a title, a smaller grey subtitle, and
a control on the right (toggle, dropdown, button, shortcut recorder, or radio).

### General
| Row | Subtitle | Control |
|---|---|---|
| Open Activity Shortcut | Record a keyboard shortcut. Clear it to use ⌘ + ⌘. | shortcut recorder, showing `⌘ + ⌘` |
| Codex also uses ⌘ + ⌘ | Context for Claude and Codex both use ⌘ + ⌘. | accent button: `Switch Codex to ⌥⌥` |
| Launch on Login | Whether the app automatically starts when you sign in to your computer. | toggle, on |
| Show Dock Icon | Keeps the app's icon visible in the Dock during normal use. | toggle, on |
| Run onboarding again | Starts the first-run experience over: the opening sequence, the onboarding cards, then the walkthrough. Nothing is deleted. | button: `Run onboarding again`, then a confirmation |
| Updates | Version 1.0 (131000) | button: `Update Now` |
| Automatic Updates | Check for new versions automatically. | toggle, on |

**"Run onboarding again" is a walkthrough, not an uninstall.** (It was "Run setup again"; the
rename is the accurate word as well as the requested one — nothing is set up, a first-run experience
is replayed.) It clears exactly three defaults —
`context.onboarded`, `context.onboarding.step`, `context.tutorial.step` — in one owner
(`Sources/ContextApp/Onboarding/OnboardingReset.swift`), then re-enters the launch path
(`ContextAppDelegate.surfaceSomethingForTheUser`) so the eight-second cinematic really does play
again. It never signs out, never touches a TCC grant or the capture database, and never clears a
`context.settings.*` key; the Settings window closes on the way, which the confirmation says first.
Guard tests: `Tests/ContextAppTests/OnboardingResetTests.swift`.

### Airgap Mode: the switch is gone, the enforcement is not

Everything from here to the end of this section is about a **row that no longer exists in
Settings** (see the table above). It is kept because the *enforcement* is unchanged and still has to
be right: `ExclusionEngine` carries `airgapMode`, `NetworkEgress` refuses every client while it is
set, and installs whose `exclusions.json` already says so keep exactly the behaviour they chose.
What went is the toggle and its subtitle; `SettingsTests.testAirgapEnforcementSurvivesTheRemovalOfItsSwitch`
replaced the copy assertion with one on the engine. Read the paragraphs below as the specification of
what the flag does, not as a description of a row on screen.

**Do not ship Coast's Airgap copy.** It was transcribed from their screenshot and describes *their*
app; taken as our requirement it produced a switch that suppressed favicon requests and nothing else
while the app went on POSTing OCR'd screen text every sixty seconds. Two of its three clauses are
wrong for us either way: this package has no updater to check, and our telemetry
(`Sources/ContextApp/Support/Telemetry.swift`) never leaves the Mac, so there is nothing for the
switch to suppress. "Takes effect after relaunch" is wrong in any app for a privacy control.

Ours means **this app stops reaching the network.** Screen-activity sync, conversation upload,
cloud transcription, MCP key provisioning, favicon fetches, the speech-model download, every Sparkle
update request, *and* sign-in all stop, immediately and without a relaunch, enforced in one place
(`Sources/ContextApp/Backend/NetworkEgress.swift`) that every remote client asks, plus the app's
sibling process — `Sources/ContextMCPKit/Airgap.swift` suppresses `OmiBackend`, the MCP server's one
remote client, which names itself to that same audited list as `.mcpOmiBackend`.

**The flag is re-read at the moment of each request, never cached at the start of a flow**, and the
two places that got that wrong are the shape to watch for. Sign-in waits on a person in a browser,
so `OmiAuth` asks again inside the one function that posts rather than once at the press
(`OmiAuth.post(url:contentType:body:client:)`). Sparkle turns one allowed check into three requests
— feed, release notes, archive — so each is gated for itself (`UpdateEgress.Step`); with
`automaticallyDownloadsUpdates` on, gating only the check meant a switch flipped while the appcast
was in flight still pulled the archive. Sparkle offers no way to cancel a download already running,
so a switch flipped mid-archive is obeyed at the next step; that window is Sparkle's, not ours.

Nothing is discarded to achieve it —
captures keep accumulating locally and queued uploads stay queued — and nothing that works offline
stops working: capture, OCR, local transcription, search, and the local MCP tools are unaffected.
Sign-in is refused rather than excepted, and says so on screen, because a session obtained under
Airgap Mode could not be used for anything. Guard tests:
`Tests/ContextAppTests/AirgapEgressTests.swift`, `Tests/ContextMCPKitTests/AirgapTests.swift`.

**Do not write "stops all network access" on screen.** That is what the row said until the honesty
pass, and it is false in a way a user cannot discover. "The local MCP tools are unaffected" above is
the enforcement decision — `Airgap.swift` argues it, and it is right — but it has a consequence the
subtitle owes the user: with the switch on, asking Claude what you were working on returns OCR'd
screen text through `recall`/`screen`/`activity`, and Claude carries that text to Anthropic as part
of the conversation. The switch bounds what *this app* sends unprompted; it does not bound what
Claude sends when asked. The shipped subtitle now says so in its last clause, and
`SettingsTests.testTheAirgapSubtitleClaimsOnlyWhatIsEnforced` holds it there.

The conflict row appears **only when a real conflict is detected** — it is a live check against other
installed agent tools' hotkeys, not a static row. Rewrite the copy for our app, keeping the shape.

**Updates rows need a verdict before they ship.** This package has no updater. Check whether
`desktop/macos/` Sparkle integration can be ported cheaply. If it cannot, show the real version and
**omit** `Update Now` / `Automatic Updates` entirely — a button that cannot update is worse than no
button, and a disabled one still implies the feature exists.

### Agents
| Row | Subtitle | Control |
|---|---|---|
| Route to Agent | With ⌘↵ you can send your query directly to your agents. | dropdown, e.g. `Claude Code` |
| Claude target | Open a Claude Code tab in the Claude desktop app with the prompt pre-filled, or run the `claude` CLI in Terminal. | dropdown: `Claude App` / Terminal |
| Command Line Interface | Enables the `coast` CLI tool for querying your data from the terminal. Installs to `~/.local/bin/<name>` — you may need to add this to your PATH. | toggle, on |

Then a tip line — "You can also use <app> directly out of Claude Code/Codex/Cursor by mentioning
<app>" — above a small illustrative mock of an agent prompt box containing a sample question.

Below that, a list of detected agent surfaces with an app icon and a green-dot `Installed` pill each:
**Claude**, **Codex**, **Cursor**. Detection must be real — reflect what is actually installed, and
show a non-installed state where it is not.

Our equivalent of the CLI toggle is the existing MCP registration
(`Sources/ContextApp/Integration/ClaudeRegistrar.swift`), so this pane largely surfaces machinery that
already exists rather than adding new machinery.

### Appearance
| Row | Subtitle | Control |
|---|---|---|
| Appearance | Choose app theme | three preview tiles: System / Light / Dark, selected one ringed in the accent |
| Accent Color | Primary UI highlight color | dropdown with a color dot, e.g. `Azure` |
| Show Dock Icon | Keeps the app's icon visible in the Dock during normal use. | toggle, on |

Then a **Timeline** section: header, the description "Choose which controls appear over the timeline.
Their keyboard shortcuts keep working even when a control is hidden.", and a **live preview** of the
timeline window (date pill reading a sample time, the control buttons, and a colored track with app
icons) that reflects the toggles below it in real time.

| Row | Subtitle | Control |
|---|---|---|
| Open externally | Opens the webpage, file, or folder captured in this frame. The icon adapts to the content. | hint `↵` + toggle, on |
| Live Text | Highlights selectable and copyable text detected in the frame. Dims when no text has been detected yet. | toggle, on |
| Zoom controls | Zooms the timeline track in and out — or pinch on the track. ⌘ + / − zooms the frame image instead. | hint `⌘ ⇧ + / −` + toggle, on |
| Segment navigation | Moves to the previous or next timeline segment. These chevrons sit on the left and right edges of the frame. | hint `⌥ ← / →` + toggle, on |

Note the tension with Phase 0 of `first-run-experience.md`, which makes the app follow system
appearance and use `controlAccentColor`. An explicit theme picker and a custom accent picker are the
opposite of that. Resolve it this way: **System is the default** and maps to following the system;
Light/Dark are overrides. The accent dropdown's default is "System" meaning `controlAccentColor`, and
named colors are opt-in. Never offer purple (`INV-UI-1`).

### Capture
| Row | Subtitle | Control |
|---|---|---|
| Screen Capture | Controls whether your screen is actively being recorded. | toggle, on |
| Pause on Inactivity | Automatically suspends recording when no keyboard or mouse activity is detected. | toggle, on |
| Capture Quality | `QHD · sharp on Retina; recommended` (the subtitle describes the selected tile) | four tiles: Best Quality / **Default** / Compact / Smallest |

Footnote under the tiles: "Higher quality preserves more detail but uses more disk space."

**Pause on Inactivity ships off, not on.** The reference's default is `on`, and taking it would have
been a silent behaviour change rather than a default: the preference had no reader anywhere in the
package until `ScreenWatcher.tick` gained one, so no install has a stored value and every existing
user would have fallen through to it — losing screen capture five minutes after their last keystroke
(`CaptureActivity.idleThreshold`) on the strength of a switch they never touched. It is invisible on
top of that: the idle branch calls `noteSkip`, which logs, and never reaches `Engine.pausedReason`,
so the menu bar goes on reading *Listening* while nothing is captured. **Flipping the default back to
`on` is gated on making that paused state visible in the menu bar** — until then `off` is the only
default that does not change an existing user's capture without them asking. Guard:
`SettingsTests.testPauseOnInactivityIsOffUntilTheUserAsksForIt`.

**Capture Quality tiles state their consequence, not only their cost.** "Higher quality … uses more
disk space" is a disk remark; on this app it is also a *retention* one, because `Limit` deletes
oldest-first once the frames folder passes the threshold (`Engine.scheduleRetentionSweep`). So the
same threshold holds materially less history at Best Quality than at Default, and the Best Quality
subtitle says so. No byte figure or multiplier is quoted anywhere in this copy: the measured table in
`ScreenWatcher` was taken at one downscale, and reusing it at another would be a fabricated
measurement.

### Storage
- A large header showing real measured usage — reference reads `709.7 MB` with `no storage limits set`
  beside it. Must be measured from our own data directory, never estimated.
- **Storage management** / "<app> keeps everything. Pick a strategy if your disk is filling up." as a
  radio group:
  | Option | Icon | Subtitle |
  |---|---|---|
  | Off | pause | Keep all your data. Forever. |
  | Compress | compress | Compress older data. |
  | Limit | trash | Limit Storage. Delete oldest recordings when threshold is reached. |
- `Off` is selected by default. **`Limit` deletes user data permanently** — it needs a threshold
  control and an explicit confirmation, and it must never be reachable by a single stray click.

### Exclusions
A search field top-right, and an `Apps | Websites` segmented control.

**Apps tab**, in this order:
- **Categories** — `Password Managers ›` / "Password manager apps", one checkbox that expands to the
  member apps.
- **Excluded** — currently-excluded apps; reference shows *Keychain Access* and *Passwords* with
  checkboxes in a lighter locked-looking state, i.e. excluded by default and not user-removable.
- **System** — Notifications, Control Center, Spotlight, Siri (unchecked), Login Screen (checked).
- **Recently Recorded** — apps actually seen recently, with real icons: Arc, ChatGPT Atlas, Claude,
  Cursor, Finder, Google Chrome, Messages, Obsidian.
- **All Applications** — the full alphabetical list with icons: AOSUIPrefPaneLauncher, ARDAgent,
  AVB Configuration, About This Mac, Accessibility, Accessibility Reader, Activity Monitor,
  Add Printer, AddressBookUrlForwarder, …

**Websites tab** — search placeholder becomes "Search or add domain":
- **Categories** — `Banks ›` / "UK & US banks, neobanks, and fintech".
- **Exclude Private Tabs** / "Works across all supported browsers." — checked.
- **Recently Recorded** — real domains with favicons: anthropic.com, pay.apple.com,
  archit-lal.github.io, attention.inc, chatgpt.com, coast.app, electomate.com, …

Exclusions are a **privacy control**, so correctness matters more here than anywhere else in the app:
- Password managers and the login screen must be excluded by **default**, before any user action.
- An exclusion must take effect immediately, not at next relaunch, and must apply to frames already
  queued but not yet written.
- Favicon fetching for the website list is a network request per domain — it must be suppressed by
  Airgap Mode, which is exactly what that setting promises. It is not the *only* thing that setting
  promises: see the General pane above. A favicon-only airgap was the shipped bug, not the spec.
- **An excluded app and an excluded site are not refused at the same point, and the scope note has to
  say which.** An app is judged from its bundle identifier before `ScreenWatcher` resolves a window,
  so nothing about it is read. A site has no identity until something is read: the window title is
  scrubbed and the accessibility tree walked for a page address before `admit` is asked, and in
  `websiteReason`'s third tier — no address readable at all — the screenshot is captured and OCR'd
  first, with `revalidate` refusing at the write barrier and `discard` unlinking the image already on
  disk. The promise worth making is *nothing excluded is stored*, which is smaller than "never read".
  Copy that claimed the larger one shipped; guard:
  `SettingsTests.testExclusionsScopeNoteDoesNotClaimAnExcludedSiteIsNeverRead`.
- There is existing redaction/policy machinery at `Sources/ContextCore/Redaction.swift` and
  `Sources/ContextCore/Policy.swift`. Exclusions belong there, behind tests, not as a UI-layer filter.
