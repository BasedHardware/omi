### Running the iOS Simulator

```bash
xcrun simctl list devices | grep Booted  # get device ID
cd app && flutter run -d <device-id> --flavor dev   # dev backend (api.omiapi.com)
cd app && flutter run -d <device-id> --flavor prod   # prod backend (api.omi.me)
```

See `/local-dev mobile` skill for full setup details, env file configuration, and troubleshooting.

### Simulator Hot Restart

When the iOS Simulator is running, trigger a hot restart after finishing edits — do not wait for the user to do it manually:

```bash
kill -SIGUSR2 $(pgrep -f "flutter run" | head -1)
```

Use `SIGUSR1` for hot reload (widget/UI-only changes) or `SIGUSR2` for hot restart (logic, state, provider changes). When in doubt, use `SIGUSR2`.

### Verifying Changes with agent-flutter

After hot restart, connect agent-flutter to see and interact with the app programmatically:

```bash
# Connect (required after every hot restart — the VM Service session resets)
AGENT_FLUTTER_LOG=/tmp/flutter-run.log agent-flutter connect

# See what's on screen
agent-flutter snapshot -i

# Interact
agent-flutter press @e3                # tap by ref
agent-flutter find type button press   # find and tap (stable)
agent-flutter fill @e5 "text"          # type into field
agent-flutter scroll down              # scroll

# Visual evidence
agent-flutter screenshot /tmp/my-change.png
```

**iOS vs Android:**
- iOS simulator: Must set `AGENT_FLUTTER_LOG` (no ADB). Commands `back`, `home`, `swipe` are ADB-only — use `find text "..." press` for navigation instead.
- Android emulator: Auto-detects via ADB. All commands available.

**Troubleshooting:**
- `agent-flutter doctor` — verify prerequisites
- Connection fails after hot restart → reconnect (expected, VM Service URI changes)
- Empty snapshot → app may be on a splash screen, wait and retry
- Stale refs → re-run `snapshot` after any `press`/`fill`/`scroll`
