# Claude Project Context

## Project Overview
OMI Desktop App for macOS (Swift)

## Logs & Debugging

### Local App Logs
- **App log file**: `/private/tmp/omi.log` (production) or `/private/tmp/omi-dev.log` (dev builds)

### Release Health (Sentry)
Check errors in the latest (or specific) release using the **sentry-release skill**:
```bash
./scripts/sentry-release.sh              # new issues in latest version (default)
./scripts/sentry-release.sh --version X  # specific version
./scripts/sentry-release.sh --all        # include carryover issues
./scripts/sentry-release.sh --quota      # billing/quota status
```
See `.claude/skills/sentry-release/SKILL.md` for full documentation.

### User Issue Investigation
When debugging issues for a specific user (crashes, errors, behavior), use the **user-logs skill**:
```bash
# Sentry (crashes, errors, breadcrumbs)
./scripts/sentry-logs.sh <email>

# PostHog (events, feature usage, app version)
./scripts/posthog_query.py <email>
```
See `.claude/skills/user-logs/SKILL.md` for full documentation and API queries.

## Repository
- This is the `desktop/` subfolder of the **OMI monorepo** (`BasedHardware/omi`)
- macOS Swift app + Rust backend live here

## Release Pipeline

Merging `desktop/**` changes to `main` triggers a fully automated release:

1. **GitHub Actions** (`desktop_auto_release.yml`) — auto-increments version, pushes a `v*-macos` tag
2. **Codemagic** (`codemagic.yaml`, workflow `omi-desktop-swift-release`) — triggered by the tag, runs on Mac mini M2:
   - Builds universal binary (arm64 + x86_64)
   - Signs with Developer ID, notarizes with Apple
   - Creates DMG + Sparkle ZIP
   - Publishes GitHub release, uploads to GCS, registers in Firestore
   - Deploys Rust backend to Cloud Run
3. **Sparkle auto-update** delivers the new version to users

**Codemagic CLI & API:**
- Token: `$CODEMAGIC_API_TOKEN` (set in `~/.zshrc`)
- App ID: `66c95e6ec76853c447b8bcbb`
- List builds: `curl -s -H "x-auth-token: $CODEMAGIC_API_TOKEN" "https://api.codemagic.io/builds?appId=66c95e6ec76853c447b8bcbb" | python3 -c "import json,sys; [print(f\"{b.get('status','?'):12} tag={b.get('tag','-'):30} start={(b.get('startedAt') or '-')[:19]}\") for b in json.load(sys.stdin).get('builds',[])[:5]]"`

To promote: `./scripts/promote_release.sh <tag>` (staging → beta → stable).

## Firebase Connection
Use `/firebase` command or see `.claude/skills/firebase/SKILL.md`

Quick connect:
```bash
cd ../backend && source venv/bin/activate && python3 -c "
import firebase_admin
from firebase_admin import credentials, firestore, auth
cred = credentials.Certificate('google-credentials.json')
try: firebase_admin.initialize_app(cred)
except ValueError: pass
db = firestore.client()
print('Connected to Firebase: based-hardware')
"
```

## Key Architecture Notes

### Authentication
- Firebase Auth with Apple/Google Sign-In
- Desktop apps should use backend OAuth flow: `/v1/auth/authorize`
- Apple Services ID: `me.omi.web` (shared across all apps)
- iOS apps use native Sign-In, Desktop uses backend OAuth + custom token

### Database Structure
- **Firestore** (`based-hardware`): User data, conversations, action items
- **Redis**: Caching
- **Typesense**: Search

### User Subcollections (Firestore)
- `users/{uid}/conversations` - Has `source` field (omi, desktop, phone, etc.)
- `users/{uid}/action_items` - Tasks (no platform tracking)
- `users/{uid}/fcm_tokens` - Token ID prefix = platform (ios_, android_, macos_)
- `users/{uid}/memories` - Extracted memories

### Platform Detection
- **FCM tokens**: Document ID prefix (e.g., `macos_abc123`)
- **Conversations**: `source` field
- **Action items**: No platform tracking

### Known Limitations
- Firestore has no collection group indexes for `source` field
- Counting users by platform requires iterating all users (slow)
- Apple Sign-In: Only one Services ID per Firebase project

## API Endpoints
- Production: `https://api.omi.me`
- Local: `http://localhost:8080`

## Credentials
See `.claude/settings.json` for connection details.

## Development Workflow

### Building & Running
- **No Xcode project** — this is a Swift Package Manager project
- **Build command**: `xcrun swift build -c debug --package-path Desktop` (the `xcrun` prefix is required to match the SDK version)
- **Full dev run**: `./run.sh` — builds Swift app, starts Rust backend, starts Cloudflare tunnel, launches app
- **Build only**: `./build.sh` — release build without running
- **DO NOT** use bare `swift build` — it will fail with SDK version mismatch
- **DO NOT** use `xcodebuild` — there is no `.xcodeproj`
- **DO NOT** launch the app directly from `build/` — always use `./run.sh` or `./reset-and-run.sh`. These scripts install to `/Applications/Omi Dev.app` and launch from there, which is required for macOS "Quit & Reopen" (after granting permissions) to find the correct binary. Launching from `build/` causes stale binaries to run after permission restarts.
- **DO NOT** manually copy binaries into app bundles and launch them — this bypasses signing, `/Applications/` installation, and LaunchServices registration

- **DO NOT** kill, delete, or interfere with running "Omi", "omi", or "Omi Beta" app bundles — these are production/release installs the user relies on

### App Names & Build Artifacts
- `./run.sh` builds **"Omi Dev"** → installs to `/Applications/Omi Dev.app` (bundle ID: `com.omi.desktop-dev`)
- `./build.sh` builds **"Omi Beta"** → `build/Omi Beta.app` (bundle ID: `com.omi.computer-macos`)
- Different bundle IDs, different app names, but same source code
- When updating resources (icons, assets, etc.) in built app bundles, update BOTH
- To check which app is currently running: `ps aux | grep "Omi"`

### Testing with Named Bundles
When the user asks to test a feature or bug fix, **always create a separate named bundle** so it can run side-by-side with the existing dev/prod apps:
```bash
OMI_APP_NAME="fix-rewind-delay" ./run.sh
```
This creates `/Applications/fix-rewind-delay.app` with bundle ID `com.omi.fix-rewind-delay`, completely independent of "Omi Dev" and "Omi Beta". Name it after the feature/bug being tested (e.g., `OMI_APP_NAME="onboarding-capture" ./run.sh`). The user can then run multiple test builds simultaneously without interfering with each other or the production app.

**Rules:**
- NEVER use the default `./run.sh` (which overwrites "Omi Dev") when testing a specific feature — always set `OMI_APP_NAME`
- Keep the name short and descriptive (it becomes both the app name and bundle ID suffix)
- The named bundle gets its own permissions, database, and auth state — the user may need to re-grant permissions and sign in
- To connect agent-swift: `agent-swift connect --bundle-id com.omi.fix-rewind-delay`

### After Implementing Changes
- `xcrun swift build` is for **compile checks only** — it does NOT start the backend
- To actually test, ALWAYS use `./run.sh` with `OMI_APP_NAME` — it starts Rust backend + Cloudflare tunnel + Swift app together
- **When the user says "test it"**, use the `test-local` skill to build, run, and verify via macOS automation

### Verifying UI Changes (agent-swift)

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
- Dev bundle ID: `com.omi.desktop-dev`. Prod: `com.omi.computer-macos` (never automate prod).

### Changelog Entries

After completing a desktop task with user-visible impact, append a one-liner to `unreleased` in `desktop/CHANGELOG.json`:

```python
python3 -c "
import json
with open('CHANGELOG.json', 'r') as f:
    data = json.load(f)
data.setdefault('unreleased', []).append('Your user-facing change description')
with open('CHANGELOG.json', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
"
```

Guidelines:
- Write from the user's perspective: "Fixed X", "Added Y", "Improved Z"
- One sentence, no period at the end
- Skip internal-only changes (refactors, CI config, code cleanup)
- HTML is allowed for links: `<a href='...'>text</a>`
- Commit CHANGELOG.json with your other changes (same commit is fine)

## User Task Completion Reporting

When completing a task that was triggered by an app user request (bug report, feature request, support inquiry, etc.) and you have the user's email address, **send them an email about the results** using the `omi-email` skill:

```bash
node ../omi-analytics/scripts/send-email.js \
  --to "<user-email>" \
  --subject "<brief result summary>" \
  --body "<what was done, what they should expect, any next steps>"
```

- Write as Matt (first person "I", not "we") — the user already has an ongoing email thread with us, so treat this as a casual continuation of that conversation, not a fresh introduction
- Be concise and direct — they know the context, just share what was done and any next steps (e.g. "update the app")
- Only send when there are meaningful results to share (don't email for internal-only changes)
