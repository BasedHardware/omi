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
3. **Automatic qualification** (`scripts/qualify-desktop-beta.sh --automatic`) — verifies published asset digests against signed-smoke evidence, runs the static release checks, rebuilds the exact tag, runs hermetic T2 plus the fault-injection suite, and writes canonical `qualifiedBeta*` evidence metadata
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
- **Agent runtime preparation cache**: local `./run.sh` calls reuse validated agent packaging from the worktree-local `.harness/agent-runtime` cache when source, locks, preparation logic, pinned runtime, mode, OS/architecture, Node/npm versions, and every file copied from the prepared runtime are unchanged. Hits verify the complete agent `dist`, both packaged dependency trees, their symlinks, and staged Node; working `agent/node_modules` is not hashed. The script logs `Cache HIT`, `MISS`, or `BYPASS`; hits preserve output mtimes but spend roughly a second on a warm local filesystem hashing the packaged outputs for integrity (hardware/filesystem dependent). CI and `--skip-npm` always bypass the stamp. Set `OMI_AGENT_RUNTIME_FORCE_REBUILD=1` for an explicit local rebuild. Do not copy this cache between worktrees or treat it as a release artifact.
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
source of truth; UI may optimistic-render, then must not double-apply the same turn.

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
3. **One idempotency key per logical turn** — every optimistic
   `stageOptimisticTurn` / kernel write MUST share the SAME key with
   `recordSurfaceTurn` / `projectCrossSurfaceTurn`. Stage first for sync UI,
   then let `KernelTurnProjection.apply` `promoteOptimisticTurn` (in-place,
   no append) when `turn_recorded` arrives. Keys are opaque strings; never
   dedupe by assistant/user text.
4. **Kernel apply is idempotent** — `KernelTurnProjection.apply` promotes
   pending optimistic turns or appends via `recordCompletedTurn`; already-seen
   continuity keys are ignored. Empty keys do not suppress.
5. **Cross-surface agent identity is structured** — `agentSpawn` / `agentCompletion`
   content blocks (plus tool-block `spawnedAgentID` / sessionId / runId lines) are
   authoritative. Persist structured blocks through `saveMessage` metadata key
   `content_blocks` (via `ChatContentBlockCodec`) so they survive reload; kernel
   apply still materializes `agentCompletion` from bracket text when a turn
   arrives without an optimistic stage. Legacy `[Background agent id=…]` bracket
   text remains dual-read only. Do not invent new free-text formats; extend the
   schema + tests together.
   Proactive notifications stage under continuity key `notification:<uuid>`
   (origin `proactive_notification`) — same stage/promote path as other surface
   turns; do not reintroduce `appendAssistantMessage` for timeline writes.
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
- **Continuity PRs / RC:** `--suite continuity` (typed + PTT + blind recall) on
  a named `omi-*` bundle after auth seed; `--suite all` for RC. Evidence under
  `.harness/agent-continuity-gauntlet/*/manifest.json` with matching git SHA.
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
