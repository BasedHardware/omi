<!-- SINGLE SOURCE OF TRUTH for all agent instructions in this repo (Claude Code, Codex, and any other agent). -->
<!-- CLAUDE.md is a thin pointer to this file. Add or change rules HERE, never in CLAUDE.md. -->
<!-- Format spec: https://agents.md | Codex guidance: https://developers.openai.com/codex/guides/agents-md -->

# Omi Agent Guide

These rules apply to every AI agent working in this repository. This file is the single source of truth; `CLAUDE.md` just points here.

**Two audiences read this file.** Engineering standards (Definition of Done, coding guidelines, testing, formatting) apply to everyone — maintainers and open-source contributors alike. Rules about this repo's `main` branch, production app bundles, deploys, and local machine workflows assume a maintainer environment; if you are working in a fork, follow your user's process for landing changes and skip those. Contributor flow: `docs/doc/developer/Contribution.mdx`. Product direction and locked invariants: `PRODUCT.md` and `docs/product/invariants/`.

## Definition of Done

Every change must satisfy this checklist before it is committed or put in a PR. When in doubt about any other rule in this file, satisfying this list is the priority.

1. **Behavior changed → a test changed.** Bug fixes include the regression test that would have caught the bug. New features test the core path and the main error path — no more.
2. **The component's test suite passes** (`backend/test.sh`, `app/test.sh`, or the component's documented equivalent), run locally before committing.
3. **You exercised the change yourself** — ran the real user-facing path, not just compiled or lint-passed. If you truly could not, say so explicitly instead of implying it works.
4. **Verification evidence is written down** — the commands you ran and what they showed, in the commit message or PR description.
5. **No orphaned deferrals** — new `TODO`/`FIXME`/`HACK` comments reference a tracking issue or are resolved before merge.
6. **Docs moved with the code** — if you changed setup, test commands, service boundaries, env vars, or agent-relevant behavior, the matching doc (this file, a component `AGENTS.md`, or `docs/doc/developer/`) is updated in the same PR. Product-direction or invariant changes update `PRODUCT.md` / `docs/product/invariants/` in the same PR.

## Leave It Better Than You Found It

Improve the code you touch — within your blast radius:

- If you touch a file and see a small related defect (dead code, a bug adjacent to your fix, a missing test for code you are modifying), fix it **in a separate commit in the same PR** so it is independently reviewable and revertable.
- Only make an opportunistic fix you can verify — covered by an existing or new test, or trivially checkable. If you can't verify it, open a GitHub issue instead of touching it.
- Never expand beyond files you were already modifying, refactor working code for style alone, or "clean up" code you haven't run. Deferring is wrong when the fix is in scope and verifiable; expanding scope is wrong everywhere else.

## Behavior

- Never ask for permission to access folders, run commands, search the web, or use tools. Just do it.
- Never ask for confirmation. Just act. Make decisions autonomously and proceed without checking in.
- You have full access to the user's computer — browser, desktop, all apps. Never ask the user to do something you can do yourself (sign in, click buttons, dismiss dialogs, etc.).

## Setup

- **Worktree setup (required before first commit/push):** `make setup` — installs the repo Git hooks using linked-worktree-safe paths.
- **Pre-commit hook (required before first commit):** `ln -s -f ../../scripts/pre-commit "$(git rev-parse --git-path hooks)/pre-commit"` — auto-formats staged files on commit.
- Mobile app setup: `cd app && bash setup.sh ios` (or `android`).

## Safety Rules

- Never kill, stop, or restart the production macOS apps (`/Applications/Omi.app` / `Omi Beta.app`, bundle id `com.omi.computer-macos`) during local development or testing.
- Development scripts/commands must target only dev or named test app processes (e.g. `Omi Dev.app` / `com.omi.desktop-dev`, or `omi-*` named bundles), never production.
- Never push directly to `main`. Land changes through a PR only. Never squash-merge — use a regular merge.
- Never push or create PRs unless explicitly asked — commit locally by default.
- **Nothing lands on `main` until the user explicitly says so.** Do not commit, merge, push, or open a PR against `main` until the user gives an explicit go-ahead in that turn. Keep all work on feature branches; a prior approval never carries over to later changes.
- **Exception — reverts merge right away.** When the user asks to revert a previously merged PR/commit, open the revert PR and merge it immediately without waiting for a separate merge go-ahead; the revert request itself is the approval.
- **Exception — verified + peer-approved changes may auto-merge.** If you have actually tested the change (exercised the real user-facing path, not just compiled/lint-passed) **and** an independent agent review approved it, you may open the PR and merge it without waiting for a separate go-ahead — especially for bug fixes. Still require explicit user sign-off for risky, wide-blast-radius, or hard-to-reverse changes (migrations, release/CI pipeline, schema, access control, data deletion).
- **Prefer testing locally first.** The user prefers to build and run the app locally to verify a change works before it goes to a PR or merge. Default to a local named-bundle build + run for desktop changes (and the equivalent local run for other components) before proposing to land anything.

## Coding Guidelines

### Product invariants

- Read [`PRODUCT.md`](PRODUCT.md) before changing product behavior. Locked rules live in [`docs/product/invariants/`](docs/product/invariants/) (shared chat continuity, memory tiers, agent control plane, integrations harness, brand UI).
- If you touch a locked invariant’s path globs, name the invariant ID in the PR and update its guard test when behavior changes.
- Do not paste product essays into this file — keep the registry as the SSOT and link here.

### UI / Design (all platforms)

- **Never use purple.** Purple is off-brand — do not use it anywhere in the UI (icons, accents, glows, hover states, gradients). Use white/neutral for accent icons and primary actions. Enforced as a no-increase ratchet (`INV-UI-1`); see `docs/product/invariants/brand-ui.md`.

### Deferred Work Markers

- New `TODO`, `FIXME`, and `HACK` comments must reference a tracking issue or be resolved before merge.
- Existing markers are legacy debt; only delete or annotate them when the owner and next action are clear.

### Backend (Python)

- **No in-function imports** — all imports at module top level.
- **Import purity** — a module's top level must be referentially transparent: importing it must not construct clients/connections (`OpenAI(...)`, `Redis(...)`, `Pinecone(...)`, `DeepgramClient(...)`, `firebase_admin.initialize_app(...)`, `tiktoken.encoding_for_model(...)`, etc.), perform network/IO (`requests.*`, `httpx.*`, `open(...)`), read `os.environ["X"]` (subscript — use `os.getenv`/`.get`), or mutate global state. Defer construction into lazy getters (`_x=None; def get_x(): ...`); tests inject fakes via `monkeypatch.setattr` on the singleton. Scope: correctness side effects, not import duration (`import langchain` is slow-but-pure and fine). Run `python scripts/scan_import_time_side_effects.py` from `backend/`. Full prescription: `backend/docs/test_isolation.md`.
- **Test isolation** — never mutate `sys.modules` at module scope in test files. Use `monkeypatch.setattr` on a lazy-held singleton, FastAPI `app.dependency_overrides` for router deps, or (reserve only) `backend/testing/import_isolation.py`. Run `python scripts/check_module_stub_pollution.py`. Do not extend `tests/unit/memory_import_isolation.py` (deprecated). See `backend/docs/test_isolation.md`.
- **Import hierarchy** (low → high): `database/` → `utils/` → `routers/` → `main.py`. Never import upward.
- **Memory management** — `del` byte arrays after processing, `.clear()` dicts/lists holding data.
- **Async I/O** — never `requests.*` in async (use `httpx.AsyncClient` pools from `utils/http_client.py`), never `Thread().start().join()` (use `critical_executor`/`storage_executor`), never `time.sleep()` in async (use `asyncio.sleep()`). Run `python scripts/scan_async_blockers.py` from `backend/` before committing.
- **`async def` vs `def` endpoints** — use `def` for endpoints that only call sync code (Firestore, Redis, file I/O); FastAPI runs `def` in a threadpool automatically. Only use `async def` when the endpoint genuinely `await`s something (httpx, file.read(), WebSocket, asyncio.sleep) or uses asyncio APIs directly. Never call sync DB/storage/file functions directly inside `async def` — wrap with `await run_blocking(executor, func, args)`.
- **Blocking calls in async** — these block the event loop: `database.*` functions (Firestore sync SDK), `open()`/`shutil.*` (file I/O), `upload_*`/`delete_*` from storage (GCS SDK), `creds.refresh()` (Google auth HTTP). In `async def`, always offload via `await run_blocking(executor, func, args)` from `utils.executors`. Pool assignment: `critical_executor` for auth/rate-limits, `db_executor` for Firestore/Redis CRUD, `llm_executor` for LLM calls, `storage_executor` for GCS/file I/O, `postprocess_executor` for coordinators, `sync_executor` for STT/VAD. See `backend/CLAUDE.md` for full rules. Never use bare `asyncio.to_thread()`.

#### Logging Security

Never log raw sensitive data. Use `sanitize()` and `sanitize_pii()` from `utils.log_sanitizer`.
- `sanitize()` for `response.text`, API responses, error bodies.
- `sanitize_pii()` for names, emails, user text.
- Keep UIDs, IPs, status codes visible for debugging.
- Never put raw `response.text` in exception messages.

#### WebSocket Concurrency

WebSocket handlers (`transcribe.py`, `pusher.py`) use `asyncio.wait(FIRST_COMPLETED)` supervisor loops — never `asyncio.gather()` on the receive task with background tasks. Key rules:
- Receive timeouts: every `websocket.receive()` wrapped in `asyncio.wait_for(..., timeout=WS_RECEIVE_TIMEOUT)`.
- Gauge placement: `inc()` in `try` body, `dec()` in `finally` — always paired.
- Task naming: WebSocket lifetime tasks must include `name=f"ws:{uid}:{task_name}"`.
- Finite vs lifetime: tasks that complete normally during active sessions (e.g. `process_pending_conversations`) go in `finite_tasks`; all others are lifetime tasks whose completion triggers teardown.

#### Backend Service Map

```
Shared: Firestore, Redis

backend (main.py)
  ├── ws ──► pusher (pusher/)
  ├── ──────► diarizer (diarizer/)
  ├── ──────► vad (modal/)
  ├── ──────► deepgram (self-hosted or cloud)
  ├── ──────► parakeet (parakeet/)
  └── ──────► llm-gateway (llm_gateway/main.py)

pusher
  ├── ──────► diarizer (diarizer/)
  └── ──────► deepgram (cloud)

agent-proxy (agent-proxy/main.py)
  └── ws ──► user agent VM (private IP, port 8080)

backend-sync (main.py, Cloud Run)
  ├── ──────► Cloud Tasks queue `sync-jobs` ──► POST /v2/sync-jobs/run (OIDC, same service)
  ├── ──────► Cloud Tasks queue `audio-merge` ──► POST /v2/audio-merge-jobs/run (OIDC, same service)
  └── ──────► Cloud Tasks queue `account-deletion` ──► POST /v1/users/account-deletion-wipes/run (OIDC, same service)

notifications-job (modal/job.py)  [cron]
agent-vm-reaper (backend/charts/agent-vm-reaper)  [cron]
```

Helm charts: `backend/charts/{agent-proxy,agent-vm-reaper,backend-listen,backend-secrets,deepgram-self-hosted,diarizer,llm-gateway,monitoring,parakeet,pusher,vad}/`

- **backend** (`main.py`) — REST API. Streams audio to pusher via WebSocket (`utils/pusher.py`). Calls diarizer for speaker embeddings (`utils/stt/speaker_embedding.py`). Calls vad for voice activity detection and speaker identification (`utils/stt/vad.py`, `utils/stt/speech_profile.py`). Calls deepgram or parakeet for STT (`HOSTED_PARAKEET_API_URL`, `utils/stt/streaming.py`).
- **hosted MCP OAuth** (`routers/mcp_sse.py`) — Provider-neutral OAuth for `/v1/mcp/sse`. Configure public or confidential clients with `MCP_OAUTH_CLIENTS_JSON`; allowlist the exact connector callback URI from the provider. The temporary `MCP_OAUTH_CHATGPT_*` envs still define the legacy confidential ChatGPT test client, and `MCP_OAUTH_PUBLIC_*` can expose a no-secret PKCE public client. Also set `MCP_AUTHORIZATION_SERVER_URL`, optional `MCP_RESOURCE_URL`, and token TTL env vars.
- **llm-gateway** (`llm_gateway/main.py`) — Internal FastAPI service for Omi-managed LLM auto lanes. Called by backend with service auth for `omi:auto:*` chat-completions routes; not exposed to clients.
- **pusher** (`pusher/main.py`) — Receives audio via binary WebSocket protocol. Calls diarizer and deepgram for speaker sample extraction (`utils/speaker_identification.py` → `utils/speaker_sample.py`).
- **agent-proxy** (`agent-proxy/main.py`) — GKE. WebSocket proxy at `wss://agent.omi.me/v1/agent/ws`. Validates Firebase ID token, looks up `agentVm` in Firestore, proxies bidirectionally to VM's `ws://<ip>:8080/ws`.
- **diarizer** (`diarizer/main.py`) — GPU. Speaker embeddings at `/v2/embedding`. Called by backend and pusher (`HOSTED_SPEAKER_EMBEDDING_API_URL`).
- **vad** (`modal/main.py`) — GPU. `/v1/vad` and `/v1/speaker-identification`. Called by backend only.
- **deepgram** — STT. Streaming uses self-hosted (`DEEPGRAM_SELF_HOSTED_URL`) or cloud based on `DEEPGRAM_SELF_HOSTED_ENABLED`. Pre-recorded always uses Deepgram cloud. Called by backend and pusher.
- **parakeet** (`parakeet/`) — GPU STT service for streaming and pre-recorded transcription. Called by backend when `HOSTED_PARAKEET_API_URL` is set and parakeet is selected.
- **backend-sync** (`main.py`, same image as backend) — Cloud Run service for `/v2/sync-local-files`. When `SYNC_DISPATCH_MODE=cloud_tasks`: stages raw audio in GCS, enqueues to Cloud Tasks queue `sync-jobs`, which POSTs `/v2/sync-jobs/run` (OIDC-verified, `utils/cloud_tasks.py`) to run decode→VAD→STT inside a request. Inline fallback when the flag is off, env is incomplete, BYOK headers are present, or enqueue fails. Audio playback merges (`/v1/sync/audio/*`) follow the same pattern via queue `audio-merge` building 30-day MP3 artifacts under `playback/` (`AUDIO_MERGE_DISPATCH_MODE`). Account deletion uses `ACCOUNT_DELETION_DISPATCH_MODE=cloud_tasks` to enqueue durable wipes to queue `account-deletion`, which posts `/v1/users/account-deletion-wipes/run`; API success is returned only after the deletion marker is persisted and the wipe task is durably enqueued.
- **notifications-job** (`modal/job.py`) — Cron job, reads Firestore/Redis, sends push notifications.
- **monitoring** (`backend/charts/monitoring/`) — Prometheus, Grafana, Loki, Alloy, alerts, and HPA metric adapters for backend services.
- **agent-vm-reaper** (`backend/charts/agent-vm-reaper/`) — CronJob that deletes stale `omi-agent-*` GCE VMs left by desktop agent sandboxes.
- **backend-secrets** (`backend/charts/backend-secrets/`) — ExternalSecret and SecretStore resources that sync backend runtime secrets into GKE namespaces.

Backend runtime env contract: keep `backend/deploy/runtime_env.yaml` aligned with GKE Helm values and Cloud Run runtime env; run `backend/scripts/pre-deploy-check.sh` after backend runtime env or deploy workflow changes.

Keep this map up to date. When adding, removing, or changing inter-service calls, update this section. If a PR changes audio streaming, transcription, conversation lifecycle, speaker identification, or the listen/pusher WebSocket protocol — update `docs/doc/developer/backend/listen_pusher_pipeline.mdx` in the same PR.

### App (Flutter)

- All user-facing strings must use l10n (`context.l10n.keyName`) — never hardcoded strings. Add keys to ARB files using `jq` (never read full ARB files). See skill `add-a-new-localization-key-l10n-arb`.
- When adding new l10n keys, translate all non-English locales — never leave English text in a non-English ARB file. Don't hardcode the count; the authoritative list is whatever `ls app/lib/l10n/app_*.arb` returns minus `app_en.arb`. Use the `omi-add-missing-language-keys-l10n` skill, then verify with `cd app && flutter gen-l10n` — zero "untranslated message(s)" warnings means done.
- **Firebase Prod Config** — never run `flutterfire configure`; it overwrites prod credentials. Prod config files live in `app/ios/Config/Prod/`, `app/lib/firebase_options_prod.dart`, `app/android/app/src/prod/`.

#### Verifying UI Changes (agent-flutter)

After any Flutter UI edit, verify programmatically with [agent-flutter](https://github.com/beastoin/agent-flutter). Marionette is integrated in debug builds. Install once: `npm install -g agent-flutter-cli`.

Edit → Verify → Evidence loop:
1. Edit code, hot restart: `kill -SIGUSR2 $(pgrep -f "flutter run" | head -1)`
2. Connect: `AGENT_FLUTTER_LOG=/tmp/flutter-run.log agent-flutter connect`
3. Verify: `agent-flutter snapshot -i`
4. Interact: `agent-flutter press @e3` / `press 540 1200` / `find type button press` / `fill @e5 "text"` / `dismiss`
5. Evidence: `agent-flutter screenshot /tmp/evidence.png`

Key rules:
- Must reconnect after every hot restart (kills VM Service session).
- Refs go stale frequently — always re-snapshot before every interaction. Use `press x y` as fallback.
- `AGENT_FLUTTER_LOG` must point to flutter run stdout (not logcat).
- Prefer `find type X` / `find key "name"` over hardcoded `@ref`. Add `Key('descriptive_name')` to new interactive widgets.
- App flows & screen map: `app/e2e/SKILL.md`. Full command reference: `agent-flutter schema`.

### Desktop (macOS — Swift app + Rust backend)

The desktop app is a **Swift Package Manager** project (no Xcode project, no `.xcodeproj`). The Rust backend lives in `desktop/macos/Backend-Rust/`.
- For user-visible desktop changes, follow `desktop/macos/AGENTS.md` → Changelog Entries and add one `desktop/macos/changelog/unreleased/*.json` fragment.

#### Building & Running

- `cd desktop/macos && ./run.sh` — full local dev (build Swift app + Rust backend + Cloudflare tunnel + launch).
- `cd desktop/macos && ./run.sh --yolo` — quick start against the prod backend, no local services.
- `OMI_SKIP_BACKEND=1` — app only, use remote backend via `OMI_DESKTOP_API_URL`. `OMI_SKIP_TUNNEL=1` — no Cloudflare tunnel.
- **Parallel worktrees auto-isolate.** `scripts/dev-instance.sh` derives a unique instance from each linked git worktree, so `run.sh` (and `backend/scripts/dev-serve.sh`) pick per-worktree ports (Rust 10201+, Python 8080+, automation 47777+) and bundle name (`omi-<worktree>`). Kills are pidfile-scoped (never the global `omi-desktop-backend` name), and a taken port fails loud instead of clobbering. The primary checkout is unchanged (`Omi Dev`, 10201/8080/47777). Override any of `OMI_INSTANCE` / `PORT` / `PYTHON_PORT` / `OMI_AUTOMATION_PORT` / `OMI_APP_NAME` to opt out.
- **`run.sh` build lock is per-worktree, launch-phase only.** It serializes same-checkout builds that share `Desktop/.build/` + `build/$APP_NAME.app`, holds through install/seed/`open`, then releases before the long-running backend wait — never a per-user global mutex. Cross-worktree `./run.sh` must not block each other. Do not point two worktrees at the same explicit `OMI_APP_NAME` (shared `/Applications` path is not cross-locked).
- `Omi Dev` is the canonical shared development profile: `/Applications/Omi Dev.app`, bundle id `com.omi.desktop-dev`, reusable permissions, and auth seed source. Do not pass `OMI_APP_NAME="Omi Dev"` from a linked worktree; that creates a named bundle displayed as Omi Dev with a different bundle id and breaks permission reuse.
- Local Python backend (per-worktree port): `cd backend && ./scripts/dev-serve.sh`.
- Compile-only check: `cd desktop/macos && xcrun swift build -c debug --package-path Desktop` (the `xcrun` prefix is required to match the SDK).
- **DO NOT** use bare `swift build`, `xcodebuild`, or launch from `build/` directly. Always launch via `cd desktop/macos && ./run.sh` (installs to `/Applications/` and registers with LaunchServices, required for permission "Quit & Reopen").
- Release builds are handled entirely by Codemagic CI (no local release script).
- For PRs that change function signatures or cross-file types, run a clean release build before merge: `cd desktop/macos && rm -rf .build && xcrun swift build -c release --triple arm64-apple-macosx` — incremental debug builds miss stale-cache type errors that Codemagic's clean release build catches later.

#### Named Test Bundles

When testing a feature or fix, **always create a separate named bundle** so it runs side-by-side with dev/prod:
```bash
cd desktop/macos && OMI_APP_NAME="omi-fix-rewind" ./run.sh
```
This installs `/Applications/omi-fix-rewind.app` with bundle id `com.omi.omi-fix-rewind`, with its own permissions, database, and auth state.

Rules:
- **ALWAYS prefix the name with `omi-`** (e.g. `omi-fix-rewind`, `omi-vision-test`) so bundles group together in `/Applications/`.
- NEVER use `Omi Dev` as a named bundle. If you need the shared permission/profile grant, launch from the primary checkout with no `OMI_APP_NAME`; otherwise use an `omi-*` named bundle and expect separate macOS permissions.
- NEVER use bare `./run.sh` when testing a specific change — it overwrites "Omi Dev".
- NEVER kill or interfere with "Omi", "Omi Beta" — those are production installs.
- Keep app name and bundle suffix identical (e.g. `omi-search.app` → `com.omi.omi-search`).

#### Self-Testing the App (end-to-end)

**Hard rule: you may not ask the user to verify a feature you have not actually exercised yourself.** Compiling, "looks correct from the code", or "scroll down to see it" are not verification. If the obvious path is blocked (permission, focus, missing tool), try a long sequence of alternatives before involving the user — extend the bridge with a new action, add a temporary in-process hook, search the web for a workaround, grant the missing permission yourself if you can, write a tiny standalone harness. Roughly: spend ten serious attempts across different approaches before you escalate. Asking the user is the last move, not the first.

Agents can and should self-test the running app — don't stop at a successful compile. The fast path skips the slow parts (web login, sidebar click-through):

1. **Build + launch a named bundle:** `cd desktop/macos && OMI_APP_NAME="omi-<feature>" ./run.sh` (add `OMI_SKIP_TUNNEL=1` for a local backend without a tunnel; `OMI_SKIP_BACKEND=1 OMI_DESKTOP_API_URL=…` to point at a remote backend).
2. **Boot signed-in (no browser):** sign into "Omi Dev" once; `./run.sh` auto-clones auth/onboarding plus common shortcuts/settings into named bundles **before launch** (UserDefaults is read at startup). To do it manually:
   ```bash
   cd desktop/macos && ./scripts/omi-auth-dump.sh                  # capture the Omi Dev session
   ./scripts/omi-auth-seed.sh com.omi.omi-<feature> \
     tmp/desktop-auth.json "/Applications/omi-<feature>.app"  # clears stale Keychain; UD→KC migrate
   ./scripts/omi-settings-seed.sh com.omi.omi-<feature>       # replay shortcuts/settings
   ```
   On next launch `restoreAuthState()` picks it up and boots already-signed-in.
3. **Inspect / drive the app:**
   - **Prefer the local bridge — it never touches the cursor.** It calls the app's real code in-process (no synthetic mouse events), so it won't take over the user's machine. Use it before reaching for `agent-swift click`/`cliclick`/computer-use. Auto-enables on non-prod bundles; run several at once by giving each its own `OMI_AUTOMATION_PORT` (default 47777).
   - `./scripts/omi-ctl state` — app-state snapshot (selected tab, auth, onboarding).
   - `./scripts/omi-ctl navigate <screen> [settings-section]` — jump straight to a screen in ~150ms (`omi-ctl screens` lists targets).
   - `./scripts/omi-ctl actions` then `./scripts/omi-ctl action <name> [k=v …]` — discover and run semantic actions (e.g. `refresh_all_data`, `toggle_transcription enabled=false`). Add new ones in `DesktopAutomationActionRegistry`. See `desktop/macos/e2e/SKILL.md` §2b.
   - `agent-swift connect --bundle-id com.omi.omi-<feature>` then `snapshot -i`, `find role textfield fill "…"`, `click @eN`, `screenshot /tmp/evidence.png` — only for UI the bridge can't reach yet (`click` moves the cursor).
4. **Read logs to confirm behavior:**
   - App + chat bridge: `/private/tmp/omi-dev.log` (dev builds) or `/private/tmp/omi.log`.
   - Local Rust backend: stdout of the `./run.sh` process.
   - Per-user issues: check Sentry dashboard for crashes, PostHog for events.
5. **Verify the actual behavior**, not just that the app launched — exercise the feature and check the logs/UI reflect the change.

#### Verifying UI Changes (agent-swift)

After any Swift UI edit, verify programmatically with [agent-swift](https://github.com/beastoin/agent-swift) (macOS Accessibility API, no app-side instrumentation). Install once: `brew install beastoin/tap/agent-swift`; grant Accessibility permission to Terminal.app.

Edit → Verify → Evidence loop:
1. Edit code, rebuild + launch: `cd desktop/macos && OMI_APP_NAME="omi-<feature>" ./run.sh`
2. Connect: `agent-swift connect --bundle-id com.omi.omi-<feature>`
3. Verify: `agent-swift snapshot -i` (interactive elements only)
4. Interact: `agent-swift click @e3` / `fill @e5 "text"` / `find role button click`
5. Assert: `agent-swift is exists @e3` / `wait text "Settings"`
6. Evidence: `agent-swift screenshot /tmp/evidence.png`

Key rules:
- `agent-swift doctor` verifies Accessibility permission and target app.
- Prefer `click` over `press` for SwiftUI — `click` sends CGEvent clicks (triggers NavigationLink), `press` sends AXPress (AppKit only).
- Refs go stale after `click`/`press`/`fill`/`scroll` — re-snapshot before the next interaction.
- Always use `snapshot -i` — full snapshots of complex apps are very verbose.
- Argument order: `get <property> <ref>`, `is <condition> <ref>`, `wait <condition> [<target>]`, `find <locator> <value>`.
- Dev bundle id: `com.omi.desktop-dev`. Prod: `com.omi.computer-macos` (never automate prod).
- App flows & screen map: `desktop/macos/e2e/SKILL.md`. Full command reference: `agent-swift schema`.

## Computer Control (clicking, typing, screenshots)

For controlling the Mac GUI, use the right tool for each job:

| Task | Tool | Example |
|------|------|---------|
| Click at coordinates | `cliclick` | `cliclick c:X,Y` |
| Mac desktop screenshots | `screencapture` | `screencapture -x /tmp/screen.png` |
| Native macOS app testing | `agent-swift` | See Desktop section above |
| Browser automation | `playwright` MCP | Headless, most reliable |

Rules:
- NEVER try 3+ different click tools for the same action — pick one and commit.
- Prefer `cliclick` over `automac`/`mac-use-mcp` (coordinate bugs on multi-monitor).

## Formatting

**Install the pre-commit hook before your first commit** (see Setup). Verify: `test -x "$(git rev-parse --git-path hooks)/pre-commit" && echo OK`.

The **pre-commit hook** auto-formats staged files on commit (Dart, Python, ARB/JSON, web/Prettier, C/C++, Rust). You can also format manually:

| Language | Manual command |
|----------|----------------|
| Dart (`app/`) | `dart format --line-length 120 <files>` |
| Python (`backend/`) | `black --line-length 120 --skip-string-normalization <files>` |
| ARB (`app/lib/l10n/`) | `jq --indent 4 '.' <file> > tmp && mv tmp <file>` |
| C/C++ (firmware) | `clang-format -i <files>` |
| Rust (`desktop/macos/Backend-Rust/`) | `rustfmt --edition 2021 <files>` |
| Web (`web/`) | `npx prettier --write <files>` |

Files ending in `.gen.dart` or `.g.dart` are auto-generated — don't format manually.

## Git

- **Before your first commit**, install the pre-commit hook (see Setup). Commits without the hook bypass formatting and let violations land on `main`.
- Before starting work, run `git fetch origin && git pull --ff-only` on `main` — don't branch off stale local state.
- Always commit to the current branch — never switch branches mid-task. Always work in a git worktree for code changes (`git worktree add`).
- Never push directly to `main`. Land changes through PRs only. Never squash-merge — use a regular merge.
- Make individual commits per feature or testable surface, not per file or unrelated bulk changes.
- If push fails (remote ahead): `git pull --rebase && git push`.
- Never push or create PRs unless explicitly asked — commit locally by default.

### RELEASE Command
Create a branch from `main`, make individual commits per feature or testable surface, push and open a PR, merge without squash, then switch back to `main` and pull.

### RELEASEWITHBACKEND Command
Full RELEASE flow + `gh workflow run gcp_backend.yml -f environment=prod -f branch=main`.

## Testing

### Philosophy — coverage grows by ratchet, not by mandate

- **Every bug fix adds the regression test that would have caught it.** This is the one non-negotiable way coverage grows; it compounds exactly where the codebase has proven fragile.
- **New features test the core path and the main error path.** Don't chase exhaustive coverage — a small test that will still be meaningful in a year beats ten brittle ones.
- **CI tests must be hermetic**: no live services, no network, no sleeps, no ordering dependence. A test that needs a live service stays out of the CI suite; note in the PR how you ran it instead.
- **Hermetic tests must run in CI.** Put new hermetic tests where the component's runner discovers them and confirm they execute in a full local run; if a test requires a live service, keep it out of CI and document how you ran it in the PR.
- Delete or fix a flaky/obsolete test you encounter (see Leave It Better) — a suite people distrust is worse than a smaller suite.

### Running Tests

- Run `backend/test-preflight.sh` first to verify tools, packages, and env vars.
- High-risk backend workflows (checkpoint/resume, retry/idempotency, side-effect fanout, rollout/repair jobs) must be listed in `backend/testing/workflow_contracts.json` with local contract tests; source-only changes must run those tests before PR.
- OpenAPI contract checks use `backend/scripts/openapi_runner.sh`, which syncs the pinned `backend/openapi-requirements.txt` runner env and prewarms `tiktoken`; CI and `scripts/pre-push` must use this same path.
- Backend changes: run `backend/test.sh`. App changes: run `app/test.sh`. Run before committing.
- Backend unit tests need `python3`, `pytest`, packages from `requirements.txt`, `ENCRYPTION_SECRET` (set by test.sh). Integration tests optionally need `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `ADMIN_KEY`, Redis, `GOOGLE_APPLICATION_CREDENTIALS`.

## CI/CD & Logs

- Desktop release pipeline: merging `desktop/macos/**` to `main` auto-increments the version, tags `v*-macos`, and triggers Codemagic to build/sign/notarize/publish a beta GitHub release. Stable/prod requires the agent runbook `desktop/macos/docs/agent-prod-promotion-runbook.md`, then manual `.github/workflows/desktop_promote_prod.yml` dispatch with `release_tag` and `confirm=promote-stable`; that workflow is roll-forward only, deploys the Rust backend from the exact tag, verifies `/health`, promotes the Firestore bridge release, then marks the GitHub release stable. Desktop Rust backend deploys require environment-scoped `DESKTOP_BACKEND_BASE_API_URL` so OAuth callbacks set runtime `BASE_API_URL`.
- Backend deploy: `gh workflow run gcp_backend.yml -f environment=prod -f branch=main`.
- Firmware release (Omi CV1): manual `.github/workflows/firmware_release.yml`. Bump `CONFIG_BT_DIS_FW_REV_STR` in `omi/firmware/omi/omi.conf` first, then `gh workflow run firmware_release.yml -f publish=publish -f changelog="..." -f minimum_app_version_code=...` (omit `publish` for a build-only QA run). It builds via Docker (NCS 2.9.0 sysbuild + MCUboot), names the OTA asset `Omi_CV1_OTA_v<ver>.zip` (the "ota" substring is required), and publishes a `Omi_CV1_v<ver>` GitHub Release with the `KEY_VALUE` body that `backend/routers/firmware.py` serves. Build logic lives in `omi/firmware/scripts/ci/`.

## Documentation Maintenance

- **This file (`AGENTS.md`) is the single source of truth for agent instructions.** Add or change rules here. `CLAUDE.md` is only a pointer — do not put instructions in it.
- **Any AI editing this file must keep it concise and simple** — short, plain bullets a human or agent can scan fast. Prefer editing/replacing an existing line over adding new ones; no verbose prose.
- **Write rules mechanically, and back them with checks.** Agents of very different capability read this file; a rule is only reliable if a weak agent can apply it without judgment ("put live-service tests under X, excluded from CI" beats "avoid heavy tests"). Prefer encoding a rule as a script or CI check with a clear failure message — enforced rules don't drift; requested behavior does.
- **When a defect ships because guidance was misread or missing, tighten the guidance in the fix PR** — make the rule mechanical enough that the same misreading can't recur, or add a check that catches it.
- If a PR changes setup, test commands, safety rules, service boundaries, or env vars — update this file in the same PR.
- For architecture / core flow / API changes — update Mintlify docs (`docs/doc/developer/`) in the same PR.
- For product direction or locked invariants — update `PRODUCT.md` and `docs/product/invariants/` (and guard tests) in the same PR.
- If a PR changes audio streaming, transcription, conversation lifecycle, or listen/pusher WebSocket — update `docs/doc/developer/backend/listen_pusher_pipeline.mdx`.

## Cursor Cloud specific instructions

Running in a Cursor Cloud VM (Linux x86)? See **[.cursor/cloud-agent-environment.md](.cursor/cloud-agent-environment.md)** — what runs here, the credential-free **hermetic E2E harness** (preferred), running the backend live, and known pre-existing test failures.
