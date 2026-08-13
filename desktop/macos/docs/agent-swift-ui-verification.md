# Verifying UI Changes (agent-swift)

After editing Swift UI code, verify the change programmatically using [agent-swift](https://github.com/beastoin/agent-swift) — a CLI that controls any macOS app via the Accessibility API.

**One-time setup:** `brew install beastoin/tap/agent-swift` + grant Accessibility permission to Terminal.app.

```bash
# After ./run.sh launches the app:
agent-swift doctor                                   # verify Accessibility permission
agent-swift connect --bundle-id com.omi.desktop-dev  # connect to running app
agent-swift snapshot -i                              # see interactive elements
agent-swift click @e3                                # CGEvent click (SwiftUI)
agent-swift press @e3                                # AXPress (AppKit buttons)
agent-swift fill @e5 "search text"                   # type into a text field
agent-swift find role button click                   # find + chained action
agent-swift is exists @e3                            # assert element exists (exit 0/1)
agent-swift wait text "Settings"                     # wait for text to appear
agent-swift screenshot /tmp/evidence.png             # capture app window
```

**Key rules:**
- Always use `snapshot -i` (interactive only) — full snapshot of a complex SwiftUI app is extremely verbose.
- Prefer `click` over `press` for SwiftUI — `click` sends CGEvent clicks (triggers NavigationLink), `press` sends AXPress (AppKit only).
- Refs go stale after `click`/`press`/`fill`/`scroll` — re-snapshot before the next interaction.
- Argument order: `get <property> <ref>`, `is <condition> <ref>`, `wait <condition> [<target>]`, `find <locator> <value>`.
- 15 commands: `doctor`, `connect`, `disconnect`, `status`, `snapshot`, `press`, `click`, `fill`, `get`, `find`, `screenshot`, `is`, `wait`, `scroll`, `schema`.
- No app-side instrumentation needed — works via macOS Accessibility API on any Cocoa/SwiftUI app.
- Dev bundle ID: `com.omi.desktop-dev`. Prod: `com.omi.computer-macos` (stable) and `com.omi.computer-macos.beta` (Omi Beta) — never automate prod.
