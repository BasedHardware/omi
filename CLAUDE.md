# Coding Guidelines
<!-- Official guidance for writing these files:
     CLAUDE.md: https://docs.anthropic.com/en/docs/claude-code/memory
     AGENTS.md: https://developers.openai.com/codex/guides/agents-md
     Format spec: https://agents.md -->

## Behavior

- Never ask for permission to access folders, run commands, search the web, or use tools. Just do it.
- Never ask for confirmation. Just act. Make decisions autonomously and proceed without checking in.

## Setup

### Install Pre-commit Hook
Run once to enable auto-formatting on commit:
```bash
ln -s -f ../../scripts/pre-commit .git/hooks/pre-commit
```

### Mobile App Setup
```bash
cd app && bash setup.sh ios    # or: bash setup.sh android
```

## Backend
<!-- Maintainers: @beastoin (service map, logging security), @Thinh (imports, memory mgmt) -->

### No In-Function Imports
All imports must be at the module top level. Never import inside functions.

### Import from Lower-Level Modules
Follow the module hierarchy when importing. Higher-level modules import from lower-level modules, never the reverse.

**Module hierarchy (lowest to highest):**
1. `database/` - Database connections, cache instances
2. `utils/` - Utility functions, helpers
3. `routers/` - API endpoints
4. `main.py` - Application entry point

### Memory Management
Free large objects immediately after use. E.g., `del` for byte arrays after processing, `.clear()` for dicts/lists holding data.

### Logging Security
Never log raw sensitive data. Use `sanitize()` and `sanitize_pii()` from `utils.log_sanitizer`.

Rules:
- `sanitize()` for `response.text`, API responses, and error bodies.
- `sanitize_pii()` for names, emails, and user text.
- Keep log levels as-is (don't downgrade to hide data).
- Keep UIDs, IPs, status codes, and structural info visible for debugging.
- Never put raw `response.text` in exception messages.

### Backend Service Map

```
Shared: Firestore, Redis

backend (main.py)
  ├── ws ──► pusher (pusher/)
  ├── ──────► diarizer (diarizer/)
  ├── ──────► vad (modal/)
  └── ──────► deepgram (self-hosted or cloud)

pusher
  ├── ──────► diarizer (diarizer/)
  └── ──────► deepgram (cloud)

agent-proxy (agent-proxy/main.py)
  └── ws ──► user agent VM (private IP, port 8080)

notifications-job (modal/job.py)  [cron]
```

Helm charts: `backend/charts/{backend-listen,pusher,diarizer,vad,deepgram-self-hosted,agent-proxy}/`

See service descriptions in AGENTS.md. Update both files when service boundaries change.

## App (Flutter)
<!-- Maintainers: @Thinh (l10n, formatting) -->

### Localization Required

- All user-facing strings must use l10n. Use `context.l10n.keyName` instead of hardcoded strings. Add new keys to ARB files using `jq` (never read full ARB files - they're large and will burn tokens). See skill `add-a-new-localization-key-l10n-arb` for details.
- **Translate all locales**: When adding new l10n keys, provide real translations for all 33 non-English locales — do not leave English text in non-English ARB files. Use the `omi-add-missing-language-keys-l10n` skill to generate proper translations. Ensure `{parameter}` placeholders match the English ARB exactly.
- After modifying ARB files in `app/lib/l10n/`, regenerate the localization files:
```bash
cd app && flutter gen-l10n
```

### Verifying UI Changes (agent-flutter)

After editing Flutter UI code, **verify the change programmatically** — do not just hot restart and hope.

Marionette is already integrated in debug builds (`marionette_flutter: ^0.3.0`). Install agent-flutter once: `npm install -g agent-flutter-cli`.

**Edit → Verify → Evidence loop:**
```bash
# 1. Edit Dart code, then hot restart
kill -SIGUSR2 $(pgrep -f "flutter run" | head -1)

# 2. Connect (must reconnect after every hot restart)
AGENT_FLUTTER_LOG=/tmp/flutter-run.log agent-flutter connect

# 3. See what's on screen
agent-flutter snapshot -i              # list interactive widgets
agent-flutter snapshot -i --json       # structured data for parsing

# 4. Interact
agent-flutter press @e3                # tap by ref
agent-flutter press 540 1200           # tap by coordinates (ADB fallback)
agent-flutter dismiss                  # dismiss system dialogs (location, permissions)
agent-flutter find type button press   # find and tap (more stable than @ref)
agent-flutter fill @e5 "hello"         # type into textfield
agent-flutter scroll down              # scroll current view

# 5. Screenshot evidence for PRs
agent-flutter screenshot /tmp/after-change.png
```

**Key rules:**
- Refs go stale frequently (Flutter rebuilds aggressively) — always re-snapshot before every interaction. Use `press x y` as fallback.
- `AGENT_FLUTTER_LOG` must point to the flutter run stdout log file (not logcat). This is how agent-flutter finds the correct VM Service URI.
- `find type X` or `find text "label"` is more stable than hardcoded `@ref` numbers.
- When adding new interactive widgets, use `Key('descriptive_name')` so agents can use `find key` (survives i18n and theme changes).
- Android: auto-detects via ADB. iOS: requires `AGENT_FLUTTER_LOG` or explicit URI.
- **App flows & exploration skill**: See `app/e2e/SKILL.md` for navigation architecture, screen map, widget patterns, and known flows. Read this when developing features or exploring the app.

### Firebase Prod Config
Never run `flutterfire configure` — it overwrites prod credentials. Prod config files in `app/ios/Config/Prod/`, `app/lib/firebase_options_prod.dart`, `app/android/app/src/prod/`.

## Desktop (macOS)

### Verifying UI Changes (agent-swift)

After editing Swift UI code, **verify the change programmatically** via the macOS Accessibility API — no app-side instrumentation needed.

Install agent-swift once: `brew install beastoin/tap/agent-swift`. Requires Accessibility permission for Terminal.app (System Settings → Privacy & Security → Accessibility).

**Edit → Verify → Evidence loop:**
```bash
# 1. Edit Swift code, rebuild and run
cd desktop && ./run.sh

# 2. Connect to the running app
agent-swift connect --bundle-id com.omi.desktop-dev

# 3. See what's on screen
agent-swift snapshot -i              # interactive elements only (recommended)
agent-swift snapshot -i --json       # structured data for parsing

# 4. Interact
agent-swift click @e3                # CGEvent click (works with SwiftUI)
agent-swift press @e3                # AXPress action (AppKit buttons)
agent-swift fill @e5 "search text"   # type into a text field
agent-swift find role button click   # find + chained action
agent-swift scroll down              # scroll the view

# 5. Assert & wait
agent-swift is exists @e3            # exit 0 = true, exit 1 = false
agent-swift wait text "Settings"     # wait for text to appear (5s default)

# 6. Screenshot evidence for PRs
agent-swift screenshot /tmp/after-change.png  # capture app window
```

**Key rules:**
- `agent-swift doctor` verifies Accessibility permission and can check the target app.
- Prefer `click` over `press` for SwiftUI apps — `click` sends CGEvent mouse clicks that trigger NavigationLink/gesture handlers, while `press` sends AXPress which only works for AppKit buttons.
- Refs go stale after `click`/`press`/`fill`/`scroll` — re-snapshot before the next interaction.
- Always use `snapshot -i` (interactive only) — full snapshots of complex apps are very verbose.
- Argument order: `get <property> <ref>`, `is <condition> <ref>`, `wait <condition> [<target>]`, `find <locator> <value>`.
- JSON output: `--json` flag, `AGENT_SWIFT_JSON=1` env var, or pipe to auto-detect.
- 15 commands: `doctor`, `connect`, `disconnect`, `status`, `snapshot`, `press`, `click`, `fill`, `get`, `find`, `screenshot`, `is`, `wait`, `scroll`, `schema`.
- Works with any macOS app (SwiftUI, AppKit, Electron) — no Marionette or app-side setup.
- Bundle ID for dev: `com.omi.desktop-dev`. For prod: `com.omi.computer-macos`.
- If you launch a custom-named desktop test build, keep the dev bundle identifier aligned with the app name. Example: `search.app` should use a matching dev bundle ID like `com.omi.search`, not `com.omi.desktop-dev`.
- **App flows & exploration skill**: See `desktop/e2e/SKILL.md` for navigation architecture, screen map, interaction patterns (click vs press), and known flows. Read this when developing features or exploring the app.
- When asked to build or rebuild the desktop app for testing, don't stop at a successful compile: launch the dev app, interact with it programmatically to confirm it actually runs, and report any environment blocker if full interaction is impossible.

## Formatting
<!-- Maintainers: @Thinh (Jan 19) -->

Always format code after making changes. The pre-commit hook handles this automatically, but you can also run manually:

### Dart (app/)
```bash
dart format --line-length 120 <files>
```
Note: Files ending in `.gen.dart` or `.g.dart` are auto-generated and should not be formatted manually.

### Python (backend/)
```bash
black --line-length 120 --skip-string-normalization <files>
```

### C/C++ (firmware: omi/, omiGlass/)
```bash
clang-format -i <files>
```

## Git
<!-- Maintainers: @AaravGarg (original, Feb 2), @NikShevchenko (push rules, Mar 3) -->

### Rules
- Always commit to the current branch — never switch branches.
- Never push directly to `main`.
- Never merge directly from a local branch. Land changes through a PR only.
- When a change should go remote, create or use a feature branch, commit there, open/update a PR, and merge via the PR.
- Never squash merge PRs — use regular merge.
- Make individual commits per file, not bulk commits.
- The pre-commit hook auto-formats staged code — no need to format manually before committing.
- If push fails because the remote is ahead, pull with rebase first: `git pull --rebase && git push`.
- Never push or create PRs unless explicitly asked — commit locally by default.

### RELEASE command
<!-- Added by @AaravGarg (Feb 4) -->
When the user says "RELEASE", create a branch from `main`, make individual commits per changed file, push/create a PR, merge without squash, then switch back to `main` and pull.

### RELEASEWITHBACKEND command
<!-- Added by @AaravGarg (Feb 4) -->
Run the full RELEASE flow, then deploy backend to production with `gh workflow run gcp_backend.yml -f environment=prod -f branch=main`.

## CI/CD
See [docs/runbooks/deploy.md](docs/runbooks/deploy.md) for deploy triggers and checks.

## Logs
See [docs/runbooks/logging.md](docs/runbooks/logging.md) for log commands.

## Documentation Maintenance

- If a PR changes setup steps, test commands, safety rules, service boundaries, or env vars — update this file in the same PR.
- Keep `AGENTS.md` synced with this file. Update both in the same commit.
- Keep rules concise (one-line statements). No code examples or verbose prose in this file.
- For significant changes to architecture, core flows, or APIs — update the Mintlify docs (`docs/`) in the same PR. Key files: `docs/doc/developer/backend/backend_deepdive.mdx` (architecture), `docs/doc/developer/backend/chat_system.mdx` (chat), `docs/doc/developer/backend/transcription.mdx` (STT pipeline).
- If a PR changes how audio streaming, transcription, conversation lifecycle, speaker identification, or the listen/pusher WebSocket protocol works — update `docs/doc/developer/backend/listen_pusher_pipeline.mdx` in the same PR. This includes changes to timeouts, event types, processing flow, or inter-service communication between listen and pusher.

## Testing
Run `backend/test-preflight.sh` to verify environment. Run `backend/test.sh` (backend) or `app/test.sh` (app) before committing.
