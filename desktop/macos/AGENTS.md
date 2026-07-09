# Desktop (macOS) — Developer Guide

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
When debugging issues for a specific user, check Sentry dashboard for crashes and PostHog for events.

## Repository
- This is the `desktop/macos/` subfolder of the **OMI monorepo** (`BasedHardware/omi`)
- macOS Swift app + Rust backend live here

## Release Pipeline

Merging `desktop/macos/**` changes to `main` triggers a beta desktop release:

1. **GitHub Actions** (`desktop_auto_release.yml`) — auto-increments version, pushes a `v*-macos` tag
2. **Codemagic** (`codemagic.yaml`, workflow `omi-desktop-swift-release`) — triggered by the tag, runs on Mac mini M2:
   - Builds universal binary (arm64 + x86_64)
   - Signs with Developer ID, notarizes with Apple
   - Creates DMG + Sparkle ZIP
   - Runs `scripts/smoke-signed-desktop-artifact.sh` on the signed app, Sparkle ZIP, and DMG before publishing
   - Publishes GitHub release, uploads to GCS, registers in Firestore
3. **Sparkle beta update** delivers the new version to beta users

Signed artifact smoke scope:
- Always-on release audit covers bundle identity, version/tag alignment, signing/Keychain entitlements, Sparkle metadata, backend URL leakage, helper/runtime packaging, artifact readability, and local storage package surface.
- Codemagic uploads `build/desktop-smoke-result.json` with artifact digests and completed checks; promotion tooling should compare this result to the exact release asset before changing channels.
- Optional live probes (`--launch --network --auth --chat --permissions --storage`) require an isolated release runner and explicit canary env vars; production-bundle launch is fail-closed unless `OMI_SIGNED_ARTIFACT_SMOKE_ALLOW_PRODUCTION_LAUNCH=1`, and `--auth` requires `OMI_SIGNED_ARTIFACT_SMOKE_AUTH_PROOF_COMMAND` to prove app-level persistence rather than a raw bearer-token curl.
- Future release gating should split artifact creation from user visibility: create/upload the immutable artifact first, run the live smoke against that artifact, then flip beta/stable appcast/Firestore visibility only after the digest-matched smoke passes.

Stable/prod is manual:
- Before preparing stable/prod promotion, follow `docs/agent-prod-promotion-runbook.md` for target discovery, curated stable release-log creation, shared-backend coupling, approval shape, and deterministic post-promotion checks. External readiness is handled separately.
- Run GitHub Actions workflow `desktop_promote_prod.yml` with `release_tag=v*-macos` and `confirm=promote-stable`.
- The workflow runs `.github/scripts/check-desktop-release-promotion.py`, deploys the Rust backend from that exact tag, verifies `/health` reports the release tag/SHA, promotes the Firestore bridge release, marks the GitHub release `channel: stable`, then moves `desktop-backend-prod-deployed`.
- Do not manually edit a release to stable before the backend is promoted; the promotion workflow owns that mutation.
- The promotion workflow is roll-forward only. Stable rollback needs a newer fixed release or a separate manual infrastructure rollback plan, because both desktop feeds choose the newest stable app release.

**Codemagic CLI & API:**
- Token: `$CODEMAGIC_API_TOKEN` (set in `~/.zshrc`)
- App ID: `66c95e6ec76853c447b8bcbb`
- List builds: `curl -s -H "x-auth-token: $CODEMAGIC_API_TOKEN" "https://api.codemagic.io/builds?appId=66c95e6ec76853c447b8bcbb" | python3 -c "import json,sys; [print(f\"{b.get('status','?'):12} tag={b.get('tag','-'):30} start={(b.get('startedAt') or '-')[:19]}\") for b in json.load(sys.stdin).get('builds',[])[:5]]"`

Promotion from beta to stable is handled by `desktop_promote_prod.yml`, not Codemagic.

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

## Module Layout (SwiftPM)

`Desktop/Package.swift` is incrementally splitting the monolithic executable into
library targets with enforced dependency edges:

- `OmiTheme` — shared colors, typography, chrome (`Sources/Theme/`)
- `OmiWAL` — write-ahead log model + coordinator (`Sources/OmiWAL/`)
- `OmiSupport` — shared desktop runtime helpers (`Sources/OmiSupport/`, e.g. `DesktopLocalProfile`)

`Rewind/Core/` remains in the executable target for now — it still references main-app
types (`TaskActionItem`, `PowerMonitor`, etc.) and needs a shared-models carve-out first.

**Do not add new `.swift` files directly under `Desktop/Sources/`.** Place new
code in a feature directory (`Onboarding/`, `MainWindow/`, `Chat/`, etc.). CI
enforces this via `scripts/check-sources-root-layout.py`.

When carving out additional leaf modules, prefer bottom-up order (models and
storage before UI) and wire `import` + `public` on the extracted target's API.

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
- **Release builds**: Handled entirely by Codemagic CI (no local release script needed)
- **DO NOT** use bare `swift build` — it will fail with SDK version mismatch
- **DO NOT** use `xcodebuild` — there is no `.xcodeproj`
- **DO NOT** launch the app directly from `build/` — always use `./run.sh` or `./reset-and-run.sh`. These scripts install to `/Applications/Omi Dev.app` and launch from there, which is required for macOS "Quit & Reopen" (after granting permissions) to find the correct binary. Launching from `build/` causes stale binaries to run after permission restarts.
- **DO NOT** manually copy binaries into app bundles and launch them — this bypasses signing, `/Applications/` installation, and LaunchServices registration

- **DO NOT** kill, delete, or interfere with running "Omi", "omi", or "Omi Beta" app bundles — these are production/release installs the user relies on

### App Names & Build Artifacts
- `./run.sh` builds **"Omi Dev"** → installs to `/Applications/Omi Dev.app` (bundle ID: `com.omi.desktop-dev`)
- **"Omi Beta"** (bundle ID: `com.omi.computer-macos`) is built by Codemagic CI only
- To check which app is currently running: `ps aux | grep "Omi"`

### Testing with Named Bundles
When the user asks to test a feature or bug fix, **always create a separate named bundle** so it can run side-by-side with the existing dev/prod apps:
```bash
OMI_APP_NAME="omi-fix-rewind" ./run.sh
```
This creates `/Applications/omi-fix-rewind.app` with bundle ID `com.omi.omi-fix-rewind`, completely independent of "Omi Dev" and "Omi Beta". Name it after the feature/bug being tested. The user can then run multiple test builds simultaneously without interfering with each other or the production app.

**Build-lock invariant:** `./run.sh` locks per worktree (repo-root `.dev/run-sh-build.lock.d`), through build→install→seed→`open`, then releases before the long-running wait. Parallel worktrees must not block each other. Two named-bundle builds in the *same* worktree still serialize (shared `Desktop/.build/`). Do not reuse the same explicit `OMI_APP_NAME` across worktrees — `/Applications/$APP_NAME.app` is machine-global and not cross-locked.

**Rules:**
- NEVER use the default `./run.sh` (which overwrites "Omi Dev") when testing a specific feature — always set `OMI_APP_NAME`
- **ALWAYS prefix the name with `omi-`** (e.g., `omi-fix-rewind`, `omi-6512-polling`, `omi-vision-test`) so named bundles are visually grouped in `/Applications/` alongside "Omi Dev" and "Omi Beta"
- Keep the name short and descriptive (it becomes both the app name and bundle ID suffix)
- The named bundle gets its own permissions and database. `./run.sh` auto-seeds auth/onboarding from "Omi Dev" unless `OMI_SKIP_AUTH_SEED=1` is set.
- To connect agent-swift: `agent-swift connect --bundle-id com.omi.omi-fix-rewind`
- **Skip the web login:** sign into "Omi Dev" once; named bundles launched by `./run.sh` clone that session before launch.
- **Jump to a screen without clicking:** the automation bridge auto-enables on non-prod bundles — `./scripts/omi-ctl navigate <screen>` (e.g. `rewind`, `memories`, `settings rewind`). See "Fast-Path for Local Iteration" in `e2e/SKILL.md`.

### After Implementing Changes
- `xcrun swift build` is for **compile checks only** — it does NOT start the backend
- To actually test, ALWAYS use `./run.sh` with `OMI_APP_NAME` — it starts Rust backend + Cloudflare tunnel + Swift app together
- **When the user says "test it"**, use the `test-local` skill to build, run, and verify via macOS automation

### Agent Logic Harness
When touching desktop agent runtime, floating agent pills, realtime hub, PTT, or `pi-mono-extension`, run the focused harness before broader checks:
```bash
cd desktop/macos && ./scripts/agent-logic-harness.sh
```
It is self-driving for agents: it runs the risky Swift lifecycle/state tests, focused agent runtime tests, exact `pi-mono-extension` package tests, and prints per-step runtime. Use `--swift-only`, `--node-only`, or `--skip-install` only when narrowing a failure.

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

After completing a desktop task with user-visible impact, add one fragment file under `desktop/macos/changelog/unreleased/`:

Example `desktop/macos/changelog/unreleased/20260628-short-description.json`:

```json
{
  "change": "Your user-facing change description"
}
```

Guidelines:
- Write from the user's perspective: "Fixed X", "Added Y", "Improved Z"
- One sentence, no period at the end
- Use a unique kebab-case filename so parallel PRs do not conflict
- Skip internal-only changes (refactors, CI config, code cleanup)
- HTML is allowed for links: `<a href='...'>text</a>`
- Do not edit `CHANGELOG.json` by hand; release automation regenerates it
- Commit the fragment with your other changes (same commit is fine)

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
