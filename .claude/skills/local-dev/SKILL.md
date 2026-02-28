---
name: local-dev
description: "Start local development environment — backend, macOS app, or Flutter mobile in iOS simulator. Use when: 'run the app', 'start backend', 'run simulator', 'flutter run', 'local dev', 'start dev environment', 'run mobile app'."
allowed-tools: Bash
---

# Start Local Development Environment

Start the backend server, macOS app, or Flutter mobile app for local development.

## Usage

Run `/local-dev` to start both the backend and macOS app, or:
- `/local-dev backend` - start backend only
- `/local-dev app` - build and run the macOS app (debug mode)
- `/local-dev app --clean` - clean build and run (forces Swift recompilation)
- `/local-dev app --release` - build and run in release mode
- `/local-dev mobile` - run Flutter app in iOS simulator (dev flavor, dev backend)
- `/local-dev mobile --prod` - run Flutter app in iOS simulator (prod flavor, prod backend)

## Commands

### Backend
```bash
cd backend
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
python3 -c "from dotenv import load_dotenv; load_dotenv(); import subprocess; subprocess.run(['python3', '-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'])"
```

### macOS App
```bash
app/scripts/dev-macos.sh $EXTRA_ARGS
```

Where `$EXTRA_ARGS` can be:
- `--clean` - force clean build (removes build cache, ensures Swift recompilation)
- `--release` - build in release mode instead of debug
- `--no-run` - build only, don't launch the app

### Flutter Mobile (iOS Simulator)

1. Find or boot a simulator:
```bash
xcrun simctl list devices | grep Booted  # check for running simulator
# If none booted:
xcrun simctl list devices available | grep -i "iphone" | tail -5
xcrun simctl boot <device-id>
open -a Simulator
```

2. Run the app:
```bash
cd app && flutter run -d <device-id> --flavor dev
# Or for prod backend:
cd app && flutter run -d <device-id> --flavor prod
```

Logs stream to `/tmp/flutter-run.log`.

#### Flavor & Env Files

| Flavor | Env file | Backend | Agent proxy |
|--------|----------|---------|-------------|
| `dev` | `app/.dev.env` | `api.omiapi.com` | `agent.omiapi.com` |
| `prod` | `app/.env` | `api.omi.me` | `agent.omi.me` |

Dev flavor has `USE_WEB_AUTH=false` (native sign in). Prod has `USE_WEB_AUTH=true` (Safari OAuth). The simulator works best with native sign in — use dev flavor for simulator testing.

**After changing any `.env` file**, regenerate the compiled env:
```bash
cd app && rm -rf .dart_tool/build lib/env/prod_env.g.dart lib/env/dev_env.g.dart
dart run build_runner build --delete-conflicting-outputs
```

#### Simulator Notes

- iOS Keychain persists across app uninstalls in the simulator, so Firebase Auth sessions survive reinstalls
- `claudeAgentEnabled` defaults to `false` on fresh install — toggle it on in Settings → Developer Mode
- The Flutter debug connection frequently dies ("Lost connection to device") when the app goes to background — the app itself keeps running, just relaunch `flutter run`
- Logs: `grep -E "\[AgentChat\]|\[HomePage\]" /tmp/flutter-run.log | tail -20`
- Hot restart: `kill -SIGUSR2 $(pgrep -f "flutter run" | head -1)`

## Argument Handling

When `$ARGUMENTS` is "backend", only start the backend.
When `$ARGUMENTS` is "app", build and run the macOS app.
When `$ARGUMENTS` starts with "app ", pass remaining args to the script (e.g., "app --clean").
When `$ARGUMENTS` is "mobile", run Flutter app in iOS simulator with dev flavor.
When `$ARGUMENTS` is "mobile --prod", run Flutter app in iOS simulator with prod flavor.
When `$ARGUMENTS` is empty or "all", start both backend and macOS app.
