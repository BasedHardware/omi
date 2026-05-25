# Driving the macOS Swift app without taking over the cursor

**Problem:** an agent testing the desktop app physically grabs the mouse for every
button click, so you can't use the machine while it runs. We want agents to drive
the app *by commands sent to the app itself*, never by moving the physical cursor.

This doc explains why the cursor gets hijacked, how the industry solves it, what we
already do on the Flutter app, and the recommended approach for our SwiftUI app.

---

## 1. Why the cursor gets taken over (root cause)

There are three distinct ways to "click a button" on macOS, and only one of them
moves the physical cursor:

| Mechanism | Moves cursor? | How it works |
|---|---|---|
| **CGEvent synthetic mouse click** (`CGEvent(mouseEventSource:…)` at screen coords) | **YES** | Posts a global mouse-down/up at an (x,y) point. This is what `cliclick`, `computer-use`, and screenshot-driven agents use. The OS warps the cursor to the point and clicks. |
| **Accessibility action** (`AXUIElementPerformAction(el, kAXPressAction)`) | **NO** | Tells the *specific UI element* to perform its press action directly through the a11y tree. No coordinates, no cursor. |
| **In-app command** (the app exposes a control channel and calls its own handlers) | **NO** | An external process tells the app "navigate to settings" / "tap save"; the app runs the real action closure in-process. No event synthesis at all. |

The agent that's bothering you is using mechanism #1 (synthetic clicks at
coordinates). The fix is to move it to #2 or #3.

**The SwiftUI wrinkle (this is the actual trap):** our app is pure SwiftUI. SwiftUI
`Button`s render into the accessibility tree but frequently **do not expose a usable
`AXPress` action** to external `AXUIElementPerformAction` callers — the press logic
lives in SwiftUI's own gesture system, not in a classic `NSButton` cell. AppKit
`NSButton`s expose `AXPress` correctly; SwiftUI buttons often don't. So a tool like
`agent-swift` tries `press` (AX, no cursor), gets `kAXErrorCannotComplete` or finds
no press action, and **falls back to `click` (CGEvent at the element's coords) — which
moves the cursor.** That fallback is exactly the behavior you're seeing.

Sources: [AXUIElementPerformAction](https://developer.apple.com/documentation/applicationservices/1462091-axuielementperformaction),
[kAXPressAction](https://developer.apple.com/documentation/applicationservices/kaxpressaction),
[SwiftUI button a11y identifier limits (Repeato)](https://www.repeato.app/implementing-accessibility-identifiers-in-swiftui-for-ui-testing/),
[macOS accessibility automation failure modes (fazm.ai)](https://fazm.ai/t/macos-accessibility-automation).

---

## 2. How the industry solves it

### (a) XCUITest run head-out via `xcodebuild test` — the Apple-blessed default
Apple's own UI-testing framework. Tests locate elements by `accessibilityIdentifier`
and tap them via the a11y tree, not by warping the cursor. When launched from the
command line with `xcodebuild test` (not from the Xcode "run" button), the test
runner drives the app in its own session — it does **not** fight you for the mouse,
which is why CI machines run thousands of these unattended.
Sources: [Headless UITest runs (Medium)](https://medium.com/mobile-testing/headless-uitest-runs-in-xcode-9-ee757e363413),
[DevOps-friendly XCTest](https://www.linkedin.com/pulse/top-tips-devops-friendly-xctest-ios-pipeline-shashikant-jagtap),
[Hacking with Swift — UI testing cheat sheet](https://www.hackingwithswift.com/articles/148/xcode-ui-testing-cheat-sheet).

**Caveat for us:** XCUITest wants an `.xcodeproj`/`.xcworkspace` with a UITest
target. We build with **Swift Package Manager and have no Xcode project**, so adopting
XCUITest means generating/maintaining an Xcode project or a separate UITest harness.
Real cost, worth knowing before committing.

### (b) Accessibility-API driving (`AXUIElementPerformAction` + `kAXPressAction`)
External tools (Hammerspoon, custom Swift drivers, our `agent-swift`) press elements
through the a11y tree with zero cursor movement — *as long as the element exposes a
press action*. The whole game is making SwiftUI controls expose that action (see §4).

### (c) In-app automation bridge / "command channel"
The app embeds a tiny local server (or accepts URL-scheme / Apple-Event commands) and
runs its real action handlers in-process. Maximum reliability, zero event synthesis,
but you have to wire each action. **This is the pattern we already use** (see §3).

---

## 3. What we already built (and how Flutter does it)

### Desktop Swift app — we are ~70% of the way there already
- **`DesktopAutomationBridge`** (`Desktop/Sources/DesktopAutomationBridge.swift`):
  a localhost HTTP server on `127.0.0.1:47777`, auto-enabled on dev/`omi-*` bundles,
  off on the prod bundle, killable with `OMI_DISABLE_LOCAL_AUTOMATION=1`. Endpoints:
  `GET /health`, `GET /state`, `POST /navigate`, `POST /conversation/open`,
  `POST /gmail-read`. Driven by `scripts/omi-ctl` (`state`, `navigate <screen>`,
  `wait-ready`, `open-conversation`). **This already moves the cursor zero times.**
- **`agent-swift`** (Accessibility API CLI): `snapshot`, `press @ref` (AX, no cursor),
  `click @ref` (CGEvent — **moves cursor**, the fallback to avoid), `fill`, `find`,
  `wait`. Documented in `desktop/CLAUDE.md`.
- Accessibility identifiers exist but are **sparse** (~5 across 273 files):
  `SidebarView.swift:1466` (`sidebar_*`), `SettingsPage.swift:5213`
  (`syncCalendarButton`), `SpeakerBubbleView.swift` (`transcript_speaker_button_*`).
- E2E flows live as YAML in `desktop/e2e/flows/` with a guide in `desktop/e2e/SKILL.md`.

### Flutter app — the model to copy conceptually
- Uses **Marionette** (`marionette_flutter`, initialized in `app/lib/main.dart` in
  debug builds) driven by the **`agent-flutter`** CLI. Marionette drives the app
  through **Flutter's VM-service / widget tree** — it reads the widget tree and
  invokes widgets by reference. **No cursor.** ADB is only used for OS-level dialogs.
- 26 documented YAML flows in `app/e2e/`, `ValueKey`s on critical widgets for stable
  location, snapshot caches for fast replay.

**Takeaway:** Flutter's win was an *in-process widget-tree driver* (Marionette), not
coordinate clicking. Our `DesktopAutomationBridge` is the Swift equivalent — we just
haven't extended it to cover arbitrary buttons, and `agent-swift` still falls back to
cursor clicks when SwiftUI doesn't expose AXPress.

---

## 4. Recommended approach (concise)

Use a **two-layer strategy**, and ban coordinate clicking for routine testing:

**Layer 1 — make the Accessibility tree pressable (cheap, do first).**
For every interactive SwiftUI control we want to test, attach all three:
```swift
SomeButton()
  .accessibilityIdentifier("save_memory_button")   // stable locator
  .accessibilityAddTraits(.isButton)
  .accessibilityAction { viewModel.save() }          // <-- the key line
```
`.accessibilityAction { … }` makes the element expose a real press action over the
AX API, so `agent-swift press @ref` (and any AX driver / VoiceOver) fires the *actual
handler* with **no cursor movement** — eliminating the CGEvent fallback. This is the
single highest-leverage change: it turns the cursor-hijack tools into cursor-free
ones. Roll it out screen-by-screen alongside identifiers (we only have ~5 today).

**Layer 2 — extend the in-app bridge for high-value actions (most reliable).**
Grow `DesktopAutomationBridge` from "navigate + state" into a small semantic command
API for the actions agents test most (e.g. `POST /action {name:"start_recording"}`,
`/action {name:"send_chat", text:"…"}`), each calling the real handler in-process.
This is the Marionette-equivalent and is 100% deterministic — no a11y guessing, no
cursor, fastest of all. Use it for flows; use Layer 1 for breadth.

**Policy: make the cursor-free path the default and the only allowed one.**
- Agents drive the app via `omi-ctl` / the bridge (Layer 2) and `agent-swift press`
  (Layer 1) **only**.
- Forbid `agent-swift click`, `cliclick`, `computer-use`, and screenshot-coordinate
  clicking for routine testing — those are the cursor hijackers. Allow them only for
  OS-level dialogs the app can't reach (the Flutter "ADB for system dialogs" rule).
- Run on a named `omi-*` test bundle so the bridge auto-enables.

**If we want the Apple-standard regression suite too:** add an XCUITest target
(requires generating an Xcode project around the SPM package) and run it via
`xcodebuild test`. That's the long-term CI-grade option, but Layers 1+2 give you
cursor-free interactive testing *today* with far less setup.

### One-line summary
> The cursor gets hijacked because SwiftUI buttons don't expose an AX press action, so
> tools fall back to synthetic coordinate clicks. Fix it by adding
> `.accessibilityAction { … }` (+ identifier) to controls so `agent-swift press` fires
> the real handler cursor-free, and by extending our existing localhost
> `DesktopAutomationBridge` into a semantic command API — then forbid coordinate
> clicking for testing. That's exactly the in-process, command-driven model our Flutter
> app already uses via Marionette.

---
*Sources inline above. Researched on the `macos-headless-ui-testing-research` branch.*
