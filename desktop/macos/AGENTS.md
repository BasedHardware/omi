# Desktop (macOS) — Developer Guide

## Project Overview
OMI Desktop App for macOS (Swift)

## Logs & Debugging

### Local App Logs
- **App log file**: `/private/tmp/omi.log` (production). Each non-production
  launch writes to its own owner-only log; ask the running named bundle for its
  exact path with `./scripts/omi-ctl log-path` rather than reading a shared dev log.

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

### Product analytics integrity

- A desktop chat query starts after local concurrency/quota preflight and must
  emit exactly one terminal outcome: `completed`, `failed`, or `cancelled`.
  Intentional Stop and supersession are cancellations, never errors.
- Query latency ends when the final answer is visible. Persistence, title
  generation, and other post-answer work have their own reliability signals and
  must not inflate user-visible query duration.
- Product authority is independent from telemetry. Revoked or timed-out turns
  cannot apply late callbacks/results or persist a late response even if
  analytics is disabled or refactored.
- PostHog receives bounded dimensions and shape metadata only. Never send raw
  prompts, responses, notification/window titles, filesystem paths, or exception
  messages. Keep diagnostic detail in the private local log and Sentry.
- Production `QueryTracer` output is shape-only and stored under a `0700`
  directory in `0600` files. Full prompt/response/tool content is a deliberate
  non-production debugging capability only.

### Fallback / resilience telemetry
Provider/mode switches and fail-open paths must call `DesktopDiagnosticsManager.recordFallback(area:from:to:reason:outcome:)` (PostHog `desktop_health_event` / `fallback_triggered`) or Rust `fallback::record_fallback`. Same field contract as root `AGENTS.md` → Fallback / resilience telemetry. Do not invent new health-event enum cases or product “Recording Error” events for successful heals (`outcome=recovered`).

## Repository
- This is the `desktop/macos/` subfolder of the **OMI monorepo** (`BasedHardware/omi`)
- macOS Swift app + Rust backend live here

## Release Pipeline

Merging `desktop/macos/**` changes queues them for the next daily or manually dispatched candidate. A candidate advances to beta automatically only after every qualification gate passes:

1. **GitHub Actions** (`desktop_auto_release.yml`) — batches mainline changes, auto-increments the version, and pushes a `v*-macos` build-candidate tag
2. **Codemagic** (`codemagic.yaml`, workflow `omi-desktop-swift-release`) — triggered by the tag, runs on Mac mini M2:
   - Builds universal binary (arm64 + x86_64)
   - Signs with Developer ID, notarizes with Apple
   - Creates DMG + Sparkle ZIP
   - Runs `scripts/smoke-signed-desktop-artifact.sh` on the signed app, Sparkle ZIP, and DMG before publishing, including a mandatory in-app synthetic Keychain write/read/delete canary
   - Publishes an immutable non-live GitHub candidate with smoke evidence
3. **Trusted macOS qualification runner** (`desktop_qualify_beta.yml`) — dispatched by Codemagic after candidate publication and restricted to the `self-hosted`, `macos`, `omi-desktop-qualification` runner. It verifies published asset digests against signed-smoke evidence, runs the static release checks, rebuilds the exact tag, runs hermetic T2 plus the fault-injection suite, and writes canonical `qualifiedBeta*` evidence metadata. The runner must be an administrator-managed Mac with Docker Desktop; it must never execute pull-request or arbitrary-ref workflows.
4. **Automatic beta promotion** (`desktop_promote_beta.yml`) — rejects stale automatic targets, honors `DESKTOP_AUTO_BETA_ENABLED=false` as an emergency pause, validates digest-matched evidence, registers the immutable manifest, and atomically advances the explicit beta pointer

The shared Python backend must contain the manifest/pointer endpoints before the first beta promotion. Deploy it separately with `gcp_backend.yml`; merging desktop code does not deploy the prod backend. Static GCS/CDN feed ownership remains follow-up work and is not the channel source of truth.

Signed artifact smoke scope:
- Always-on release audit covers bundle identity, version/tag alignment, signing/Keychain entitlements, Sparkle metadata, backend URL leakage, helper/runtime packaging, artifact readability, and local storage package surface.
- Codemagic uploads `build/desktop-smoke-result.json` with artifact digests and completed checks; promotion tooling should compare this result to the exact release asset before changing channels.
- The synthetic `--auth-storage-canary` is mandatory before beta publication and runs inside the exact signed app without real credentials. Optional broader live probes (`--launch --network --auth --chat --permissions --storage`) require an isolated release runner and explicit canary env vars; production-bundle launch is fail-closed unless `OMI_SIGNED_ARTIFACT_SMOKE_ALLOW_PRODUCTION_LAUNCH=1`, and `--auth` requires `OMI_SIGNED_ARTIFACT_SMOKE_AUTH_PROOF_COMMAND` to prove app-level persistence rather than a raw bearer-token curl.
- Artifact creation and user visibility are split: create/upload the immutable candidate first, then advance beta/stable visibility only after digest-matched qualification passes.
- Automatic beta is fail-closed: any signed-smoke, digest, static, T2, fault-suite, newest-tag, manifest, or pointer failure leaves the candidate non-live. Set `DESKTOP_AUTO_BETA_ENABLED=false` in Codemagic or the GitHub `prod` environment to pause automatic qualification/promotion without changing stable.

Stable/prod is manual:
- Automatic qualification never nominates or promotes stable. Stable workflows remain `workflow_dispatch` only.
- Nominate the current qualified beta with `desktop_nominate_stable_candidate.yml`. Nomination records the tag/SHA, operator, rationale, soak review, telemetry review, release-note review, and qualification evidence. It never changes beta/stable pointers or deploys production.
- Before preparing stable/prod promotion, follow `docs/agent-prod-promotion-runbook.md` for target discovery, curated stable release-log creation, shared-backend coupling, approval shape, and deterministic post-promotion checks. External readiness is handled separately.
- Run GitHub Actions workflow `desktop_promote_prod.yml` with the nominated `release_tag=v*-macos` stable candidate and `confirm=promote-stable`.
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
- `OmiSupport` — shared desktop runtime helpers (`Sources/OmiSupport/`, e.g.
  `DesktopLocalProfile` and `Dictionary(lastWriteWins:)`)

`Rewind/Core/` remains in the executable target for now — it still references main-app
types (`TaskActionItem`, `PowerMonitor`, etc.) and needs a shared-models carve-out first.

**Do not add new `.swift` files directly under `Desktop/Sources/`.** Place new
code in a feature directory (`Onboarding/`, `MainWindow/`, `Chat/`, etc.). CI
enforces this via `scripts/check-sources-root-layout.py`.

When carving out additional leaf modules, prefer bottom-up order (models and
storage before UI) and wire `import` + `public` on the extracted target's API.

### Swift Formatting

Swift formatting uses a pinned `swift-format` binary (release 602.0.0 at commit
`62eaad2`), bootstrapped from source via `scripts/swift-format-wrapper.sh`. The
config lives at `Desktop/.swift-format` (2-space indent, 120-column limit).
Generated sources under `Desktop/Sources/Generated/` are excluded from the
formatter scope. Bootstrap once: `./scripts/swift-format-wrapper.sh bootstrap`.
Lint the full scope: `./scripts/swift-format-wrapper.sh lint -r $(./scripts/swift-format-wrapper.sh scope)`.

### SwiftLint

SwiftLint safety rules run as an explicit macOS manifest check (not a SwiftPM
build-tool plugin) through `scripts/swiftlint-wrapper.sh`. The wrapper pins the
upstream 0.65.0 universal macOS release artifact by SHA-256 and caches the
verified binary under `~/.cache/omi-swiftlint`; use
`./scripts/swiftlint-wrapper.sh lint` to run the full configured scope.
Generated sources and test fixtures remain excluded and the committed baseline
is down-only. SwiftLint baseline locations are absolute, so the wrapper
materializes a temporary baseline rooted at the current checkout before linting;
do not hand-edit those paths to match a specific machine.

### Synchronous state-machine callbacks

- A reducer transition is atomic through model assignment, effect delivery, UI
  projection, and snapshot publication. A callback may request another event,
  but it must not recursively reduce against a half-published transition.
- Coordinators with synchronous effect/snapshot callbacks drain nested events
  through a FIFO, non-reentrant queue. Do not fix recursion with one-off boolean
  suppression or by dispatching after an arbitrary delay.
- Tests for callback-driven machines must synchronously enqueue from both an
  effect callback and an observer/snapshot callback, assert callback depth stays
  one, and assert the resulting event order.

### Collection safety

- Never use `Dictionary(uniqueKeysWithValues:)` for API responses, decoded
  persistence, runtime projections, or any other data whose key uniqueness is
  not enforced by the Swift type system. A duplicate key traps and terminates
  the process.
- Use `Dictionary(lastWriteWins:)` from `OmiSupport` when the newest record in
  input order is authoritative. Use another explicit non-trapping merge policy
  when the domain requires different semantics.
- A raw trapping initializer is allowed only for a statically proven uniqueness
  contract, with a local reason:
  `// omi-collection-safety: static-unique-keys -- <why the type guarantees uniqueness>`.
  Runtime validation, backend expectations, and “should be unique” are not
  static contracts.
- Run `python3 scripts/check_desktop_test_quality.py` after changing Swift
  collection construction.

### Swift test quality

- Behavior fixes require tests that call the production API and assert outcomes.
  Reading a production `.swift` file and asserting that it contains a function
  name or implementation string is not behavioral coverage.
- Source inspection is reserved for narrow forbidden-pattern or static wiring
  tripwires. New tripwires must carry a local reason:
  `// omi-test-quality: source-inspection -- static contract: <what cannot be expressed behaviorally>`.
  The tripwire supplements rather than replaces behavioral coverage.
- Do not add wall-clock sleeps to unit tests. Inject a `Clock`/sleeper, drive a
  callback/continuation, or await a deterministic state signal. An unavoidable
  real-scheduler integration wait needs
  `// omi-test-quality: wall-clock-wait -- <why injection cannot test this boundary>`.
- `python3 scripts/check_desktop_test_quality.py` ratchets both legacy
  source-inspection sites and wall-clock waits; its baselines may only decrease.

## Key Architecture Notes

### Authentication
- Firebase Auth with Apple/Google Sign-In
- Desktop apps should use backend OAuth flow: `/v1/auth/authorize`
- Apple Services ID: `me.omi.web` (shared across all apps)
- iOS apps use native Sign-In, Desktop uses backend OAuth + custom token
- Session death is owned by `AuthSessionCoordinator` (`INV-AUTH-1`); use `invalidateSession` for expired/revoked Firebase creds, not nuclear `signOut()`.

#### Session 401 vs BYOK/provider 401

| Failure class | Owner | Action on 401 after forced refresh |
|---------------|-------|-----------------------------------|
| Firebase session token (default API `Authorization`) | `AuthSessionCoordinator` | `invalidateSession` → Sign-in CTA |
| BYOK provider key on request | `CredentialHealthManager` | Suppress/mark provider unhealthy; **do not** invalidate Firebase session |
| Realtime/voice managed lane | `CredentialHealthManager` + hub UX | `requiresLogin` only when session mint fails after refresh |
| Background poll with `RequestAuthPolicy.sessionPreserving` | Caller | Throw `.unauthorized`; no session invalidation |
| `DesktopLocalProfile` harness | Auth emulator bootstrap | Re-bootstrap emulator session; no prod invalidation side effects |

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
- **Fast default dev run**: after one successful full named-bundle launch, ordinary Swift-only `./run.sh` calls reuse the installed bundle. The fast lane runs incremental SwiftPM, atomically replaces the executable and current desktop API URL, re-signs the app, and relaunches without copying/re-signing static agent/framework assets or resetting LaunchServices/auth. Named local profiles are eligible: their current disposable `.env` is refreshed on each patch and is never cached in the bundle fingerprint. Package metadata, resources, agent/runtime inputs, entitlements, and persistent launch configuration automatically take the full path. Force that path with `./run.sh --full` or `OMI_FORCE_FULL_BUNDLE=1`. `OMI_SCAN_STALE_BUNDLES=1` is an explicit stale-LaunchServices recovery scan; do not enable it in the normal loop.
- **Focused feedback loop**: `./scripts/dev-feedback.py --once|--watch swift '<XCTest filter>'` or `... rust '<cargo filter>'` runs exactly the regression you selected and reports each iteration time. It watches only the matching component inputs, keeps watching after a failure, and never replaces the full component suite. Use it while editing; the authoritative pre-push gate runs `scripts/run-swift-ci.sh` with CI's pinned Xcode 16.4 for PR readiness.
- **Swift suite throughput**: `scripts/swift-test-suites.sh` isolates suite processes but now defaults to four workers (matching CI). Set `OMI_SWIFT_TEST_SUITE_WORKERS=1` only when diagnosing an order/concurrency-sensitive failure.
- **Local Rust backend**: direct `./run.sh` development uses Cargo debug output (`target/debug`) by default and reuses a healthy backend that this worktree owns when Rust source/config/profile have not changed. A compile failure leaves that healthy process alive. Use `OMI_DESKTOP_BACKEND_RELEASE=1` only for an explicit optimized local check; release/CI builds remain unchanged.
- **Agent runtime preparation cache**: local `./run.sh` calls reuse validated agent packaging from the worktree-local `.harness/agent-runtime` cache when source, locks, preparation logic, pinned runtime, mode, OS/architecture, Node/npm versions, and every file copied from the prepared runtime are unchanged. Hits verify the complete agent `dist`, both packaged dependency trees, their symlinks, and staged Node; working `agent/node_modules` is not hashed. The script logs `Cache HIT`, `MISS`, or `BYPASS`; hits preserve output mtimes but spend roughly a second on a warm local filesystem hashing the packaged outputs for integrity (hardware/filesystem dependent). CI and `--skip-npm` always bypass the stamp. Set `OMI_AGENT_RUNTIME_FORCE_REBUILD=1` for an explicit local rebuild. Do not copy this cache between worktrees or treat it as a release artifact. The checksum-verified universal Node archives are separately shared at `~/Library/Caches/OmiDesktop/node-archives` (override with `OMI_AGENT_RUNTIME_ARCHIVE_CACHE_DIR`), so fresh linked worktrees reuse the download but still validate it before staging.
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
- Named/dev bundles default to the development Python and Rust backends unless
  an explicit launch URL overrides them. Before QA, run
  `./scripts/omi-ctl health`; its unauthenticated identity payload reports the
  resolved backend environment/URLs plus the agent-runtime handshake state,
  negotiated protocol version, packaged runtime version, and expected protocol.
  A protocol-compatible runtime that omits a required capability is rejected at
  startup; health never reports the expected protocol as if it were negotiated.
- Run `./scripts/agent-logic-harness.sh --cross-surface-smoke` before building a
  QA bundle. This is the compact Swift/Node/Rust contract gate; reserve full
  component suites and the live continuity gauntlet for PR readiness.

### Run Variants & Parallel Worktrees
- `./run.sh --yolo` — quick start against the dev backend, no local services. `OMI_SKIP_BACKEND=1` — app only, remote backend via `OMI_DESKTOP_API_URL`. `OMI_SKIP_TUNNEL=1` — no Cloudflare tunnel.
- **Parallel worktrees auto-isolate.** `scripts/dev-instance.sh` derives a unique instance from each linked git worktree, so `run.sh` (and `backend/scripts/dev-serve.sh`) pick per-worktree ports (Rust 10201+, Python 8080+, automation 47777+) and bundle name (`omi-<worktree>`). Kills are pidfile-scoped (never the global `omi-desktop-backend` name), and a taken port fails loud instead of clobbering. The primary checkout is unchanged (`Omi Dev`, 10201/8080/47777). Override any of `OMI_INSTANCE` / `PORT` / `PYTHON_PORT` / `OMI_AUTOMATION_PORT` / `OMI_APP_NAME` to opt out.
- `Omi Dev` is the canonical shared development profile (reusable permissions, auth seed source). Do not pass `OMI_APP_NAME="Omi Dev"` from a linked worktree; that creates a named bundle displayed as Omi Dev with a different bundle id and breaks permission reuse.
- Local Python backend (per-worktree port): `cd backend && ./scripts/dev-serve.sh`.

### Self-Testing the App (agents)

**Hard rule: you may not ask the user to verify a feature you have not actually exercised yourself.** Compiling, "looks correct from the code", or "scroll down to see it" are not verification. If the obvious path is blocked (permission, focus, missing tool), try a long sequence of alternatives before involving the user — extend the bridge with a new action, add a temporary in-process hook, search the web for a workaround, grant the missing permission yourself if you can, write a tiny standalone harness. Roughly: spend ten serious attempts across different approaches before you escalate. Asking the user is the last move, not the first.

Fast path (skips web login and sidebar click-through):

1. **Build + launch a named bundle** (see Testing with Named Bundles above). `./run.sh` auto-clones Omi Dev auth/onboarding plus common shortcuts/settings **before launch**. Manual seeding:
   ```bash
   ./scripts/omi-auth-dump.sh                                  # capture the Omi Dev session
   ./scripts/omi-auth-seed.sh com.omi.omi-<feature> \
     tmp/desktop-auth.json "/Applications/omi-<feature>.app"   # clears stale Keychain; UD→KC migrate
   ./scripts/omi-settings-seed.sh com.omi.omi-<feature>        # replay shortcuts/settings
   ```
2. **Prefer the local bridge — it never touches the cursor.** It calls the app's real code in-process (no synthetic mouse events). Use it before reaching for `agent-swift click`/`cliclick`/computer-use. Auto-enables on non-prod bundles; run several at once via distinct `OMI_AUTOMATION_PORT` (default 47777).
   - `./scripts/omi-ctl state` — app-state snapshot (selected tab, auth, onboarding).
   - `./scripts/omi-ctl navigate <screen> [settings-section]` — jump straight to a screen in ~150ms (`omi-ctl screens` lists targets).
   - `./scripts/omi-ctl actions` then `./scripts/omi-ctl action <name> [k=v …]` — semantic actions (e.g. `refresh_all_data`). Add new ones in `DesktopAutomationActionRegistry`. See `e2e/SKILL.md` §2b.
   - `agent-swift` only for UI the bridge can't reach yet (`click` moves the cursor).
3. **Read logs to confirm behavior:** app + chat bridge in the exact path from
   `./scripts/omi-ctl log-path` (named dev bundles) or `/private/tmp/omi.log`
   (production); `./run.sh` prints the isolated local Rust backend log path at
   launch; per-user issues in Sentry/PostHog.
4. **Verify the actual behavior**, not just that the app launched — exercise the feature and check the logs/UI reflect the change.

### Default agent development loop

1. **Edit or diagnose:** run the smallest relevant unit/static harness. For repeated saves, start `./scripts/dev-feedback.py --watch swift '<filter>'` or `... rust '<filter>'`; do not launch the app only to obtain compile evidence.
2. **Swift/UI behavior:** reuse the existing named bundle with `OMI_APP_NAME=omi-<feature> ./run.sh --yolo --fast-only`; add `--no-wait` only with a harness/external backend, then use the local bridge (`omi-ctl action`, `state`, or a semantic snapshot) to assert the changed behavior.
3. **Package boundary:** use `./run.sh --full` only for the first named launch, resource/entitlement/package/runtime input changes, or when `--fast-only` reports an expected fingerprint mismatch.
4. **QA, commit, and PR readiness:** run `./scripts/omi-macos-dev doctor`, exercise the real user-facing path, then run the appropriate full component/PR contract.

`omi-macos-dev` defaults to bounded JSON summaries so an agent can safely inspect a busy machine. Pass `--verbose` to the specific command for path-level records (for example, `clean plan --verbose`); cleanup always requires the exact current plan hash. The normal 14-day retention window can be deliberately bypassed with `--older-than 0` only when the operator has explicitly approved immediate cleanup.

Never ask a user to test an unexercised path. A fast named-bundle launch plus a semantic bridge assertion is valid inner-loop evidence; a clean full bundle is release/QA evidence.

### After Implementing Changes

- `xcrun swift build` is for **compile checks only** — it does NOT start the backend
- Voice-path verification means a natural authenticated PTT turn on a named bundle — signed-out, forced-transcript, or reducer-only runs do not count; provider mint or payload changes must also show the deploy-inline provider probe.
- **When the user says "test it"**, use the `test-local` skill to build, run, and verify via macOS automation

### macOS Version Compatibility
- The deployment floor is `.macOS("14.0")` in `Desktop/Package.swift`. Every change must work on every supported macOS version from that floor up.
- Never call an API newer than the floor unguarded: wrap it in `if #available(macOS XX, *)` **and give the `else` branch a working fallback** (degrade the feature, don't blank it). Example: System Audio capture gates on `#available(macOS 14.4, *)` and hides cleanly below it.
- Version-dependent system facts (renamed apps, moved paths, changed defaults) get an explicit mapping with the old value still handled — stored user data may predate the change (example: `AppIconCache.renamedApps` maps "System Preferences" → "System Settings").
- Raising the deployment floor or dropping a fallback is a product decision — never do it as a side effect of another change.

### Open-Source Merge Hygiene
- Before starting and before committing, `git fetch origin && git rebase origin/main` (or merge) — other contributors land changes continuously; never review your diff against a stale base.
- Keep diffs surgical: touch only lines your change needs. No drive-by reformatting, renames, or import reshuffles in files others may have in-flight PRs against.
- After rebasing onto new upstream work, re-run the test suites for every file you touched **and** every file the rebase brought in that overlaps your change; a clean build alone is not revision.
- If your change modifies shared surfaces (Theme tokens, `SettingsSection`, bridge actions, INV-* contract files), grep for all usages — including tests and e2e flows — and update them in the same commit so concurrent contributors inherit a consistent tree.

### Agent Logic Harness
When touching desktop agent runtime, floating agent pills, realtime hub, PTT, or `pi-mono-extension`, run the focused harness before broader checks:
```bash
cd desktop/macos && ./scripts/agent-logic-harness.sh
```
It is self-driving for agents: it runs the risky Swift lifecycle/state tests, focused agent runtime tests, exact `pi-mono-extension` package tests, and prints per-step runtime. Use `--swift-only`, `--node-only`, or `--skip-install` only when narrowing a failure.

### Chat Continuity Write-Path Contract (INV-6)

Invariant: Main Chat, Home chat, and floating/notch chat are one timeline over one
`ChatProvider` (`historyChatProvider`). Kernel `main_chat` turns are the durable
source of truth; journal acceptance publishes the immediate pending projection,
and UI must never append a pre-journal turn.

Rules (fail the PR if any break):
1. **Single provider + floating viewport** — floating presentation is chrome + a
   viewport cursor (`FloatingChatViewport` message ids / `clientTurnId`) over
   `ChatProvider.messages`. It must not own a second durable transcript array
   (`chatHistory` of `ChatMessage` copies is forbidden).
2. **Single `turn_recorded` UI apply gate** — only `KernelTurnProjection` on
   `ChatProvider.mainInstance` (`historyChatProvider`) may attach the runtime
   turn handler (one replaceable slot). Speculative warm and other surfaces must
   reuse `mainInstance`; never construct a second `ChatProvider()` that calls
   `attachClient` / `setTurnRecordedHandler` on the shared runtime.
3. **One idempotency key per logical turn** — call `recordJournalExchange` (or
   the corresponding kernel control RPC) with one opaque continuity key and
   await acceptance before binding a visible row. Direct-control spawn receipts
   already materialize their exchange; refresh that journal instead of issuing a
   second write. Never dedupe by assistant/user text.
4. **Kernel apply is idempotent** — `KernelTurnProjection` upserts only by the
   canonical turn ID published by ordered journal replay. Rejection must leave no
   visible row, and replay/acknowledgement must replace rather than append.
5. **Cross-surface agent identity is structured** — `agentSpawn` / `agentCompletion`
   content blocks (plus tool-block `spawnedAgentID` / sessionId / runId lines) are
   authoritative. Persist structured blocks through the kernel journal/outbox so
   they survive reload; kernel apply still materializes `agentCompletion` from
   bracket text for legacy rows. Legacy `[Background agent id=…]` bracket
   text remains dual-read only. Do not invent new free-text formats; extend the
   schema + tests together.
   Proactive notifications use continuity key `notification:<uuid>` (origin
   `proactive_notification`) and enter the notification-to-chat cache only after
   journal acceptance; do not reintroduce local timeline append paths.
6. **Pill cache is derived** — open-by-id hydrates from kernel (`listFloatingAgentPills`
   / `listAgentSessions` / `inspectAgentRun`) when the in-memory pill is missing;
   refresh-on-miss is a fast path only. Success = resolvable agent after hydrate.
   Do not keep a second durable pill store.
7. **Snapshots are aliases** — `automationFloatingChatSnapshot` ==
   `automationChatSnapshot` / `automationMainChatSnapshot` over the same messages;
   no surface-specific transcript filter.
8. **Resources live on the producing message** — artifacts attach to the
   `ChatMessage` that produced them (stage/promote keeps `resources` on that id).
   UI must not invent a standalone artifact-only turn. Floating/notch resource
   strips bind `message.displayResources` on viewport-derived messages only
   (never flatMap the whole provider timeline). Aggregate strips must filter
   with `ChatContinuityInvariants.resourcesBelongingToMessages` /
   `FloatingControlBarState.viewportDisplayResources`.
9. **Agent card/list preview = prompt/objective** — collapsed header / list
   subtitle uses `ChatContinuityInvariants.agentPreviewText(prompt:output:)`
   (prompt wins; output is expanded-body only). Do not put raw completion output
   in the one-line preview.
10. **Forbidden dual-write patterns** — never: construct `ChatProvider()` for
    speculative warm (use `ChatProvider.mainInstance`); add
    `addTurnRecordedHandler` / multi-handler append APIs; introduce
    `suppressNextRecordedTurn`; store `@Published var chatHistory` of
    `ChatMessage` copies on `FloatingControlBarState`.
11. **Tests** — continuity behavior changes require a hermetic behavioral test (call
   projection/provider APIs, assert message counts/IDs). Source-string greps for
   function names are not continuity coverage (forbidden-pattern tripwires are the
   exception). Live gauntlet/stress are gates, not substitutes for hermetic tests.

### Continuity PR Definition of Done (INV-6)

A PR that touches chat write-path, kernel projection, floating viewport, agent
timeline identity/open, or pill projection is incomplete until:

1. **Contract still true** — INV-6 rules above hold after the change (or are
   updated in the same PR with a matching behavioral test).
2. **Hermetic behavioral test** for the invariant touched (stage/promote,
   snapshot alias, structured identity, open-by-id hydrate, viewport derive /
   restore, resources-on-message, agent preview text). Not a source grep
   (except forbidden-pattern tripwires).
3. **`./scripts/agent-logic-harness.sh` green** (includes
   `KernelTurnRecordedProjectionTests`, `ChatTimelineContinuityTests`,
   `FloatingControlBarStateTests`, `RuntimeOwnerIdentityTests` in the Swift
   focus filter).
4. **Write-path / cross-surface changes:** run a named-bundle continuity
   gauntlet and note evidence in the PR:
   ```bash
   cd desktop/macos && OMI_APP_NAME=omi-gauntlet OMI_SKIP_TUNNEL=1 ./run.sh
   # run.sh seeds auth after install (UD tokens → app Keychain migrate). Manual reseed:
   # ./scripts/omi-auth-seed.sh com.omi.omi-gauntlet tmp/desktop-auth.json "/Applications/omi-gauntlet.app"
   ./scripts/agent-continuity-gauntlet.sh --suite continuity --bundle-id com.omi.omi-gauntlet
   ./scripts/check-gauntlet-evidence-at-head.sh
   ```
   CI only runs gauntlet `--self-check` (wiring). Live suite is a PR/RC gate,
   not PR CI. Do not assert exact assistant wording.
5. **Hermetic e2e** only if a bridge action/surface contract changed. Do not
   expand flow `covers:` lists as fake continuity coverage.
6. **No second message store** / no new free-text identity format / no
   `suppressNextRecordedTurn`-style dual-write bandage.
7. Changelog fragment only if user-visible.

### Gauntlet / stress gate policy

- **CI:** `agent-continuity-gauntlet.sh --self-check` only (via desktop-core /
  agent-logic harness). Never require live LLM in PR CI.
- **Prompt / gateway changes:** `--suite prompts` on a named `omi-*` bundle;
  P4 requires a completed public-web lookup with a source URL and fails on
  provider tool-choice incompatibilities. **Continuity PRs / RC:** `--suite
  continuity` (typed + PTT + blind recall) after auth seed; `--suite all` for
  RC. Evidence under `.harness/agent-continuity-gauntlet/*/manifest.json` with
  matching git SHA.
- **Anti-flake:** clear owner/kernel surface before probes; per-run nonces;
  hard-fail on blind-recall / structural snapshot only; zero automatic retries
  on model wrongness.
- **Stress:** offline JSONL + forbidden terminal reasons remain the default
  gate; live bridge probes stay optional until continuity `terminal_reason`s
  exist in the taxonomy.

### Live gauntlet vs hermetic INV-6 coverage

Do not confuse these gates — a green live suite does **not** prove write-path
contract rules, and hermetic unit tests do **not** prove bridge/LLM continuity.

| Gate | What it covers | What it does **not** cover |
| --- | --- | --- |
| **Hermetic** (`agent-logic-harness.sh` Swift filter: `KernelTurnRecordedProjectionTests`, `ChatTimelineContinuityTests`, `FloatingControlBarStateTests`, `RuntimeOwnerIdentityTests`) | stage/promote same key → one message pair; floating snapshot aliases main; structured agent identity; open-by-id hydrate preference; floating viewport derive / SoT; resources on producing message; agent preview = prompt; owner-swap preserves Firebase tokens; forbidden dual-write tripwires | Live bridge auth, LLM tool use, PTT hub, race/busy policy under a real runtime |
| **Gauntlet `--self-check`** | Bridge action registration (incl. R3 `ask_main_chat_no_wait` / `main_chat_busy_state`), resilience suite wiring, hermetic contract test presence in harness filter | Any live turn |
| **Live `--suite continuity` / `agents` / `owner` / `prompts`** | Typed + PTT + blind recall, spawn/status, owner swap probe, prompt regressions on a named bundle | stage/promote single-writer, snapshot alias, hydrate preference, viewport SoT (those stay hermetic) |
| **Live `--suite resilience` (R1–R4)** | Cold bridge launch, warm reuse, bridge busy/race rejection (R3; requires real `is_sending`/`is_streaming` once, latch only extends the race window), subagent launch+status (R4) | INV-6 write-path unit invariants above |

`--self-check` fails if R3 race actions or the hermetic INV-6 test methods /
harness filter classes drift away.

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
