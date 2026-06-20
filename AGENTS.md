<!-- SINGLE SOURCE OF TRUTH for all agent instructions in this repo (Claude Code, Codex, and any other agent). -->
<!-- CLAUDE.md is a thin pointer to this file. Add or change rules HERE, never in CLAUDE.md. -->
<!-- Format spec: https://agents.md | Codex guidance: https://developers.openai.com/codex/guides/agents-md -->

# Omi Agent Guide

These rules apply to every AI agent working in this repository. This file is the single source of truth; `CLAUDE.md` just points here.

## Behavior

- Never ask for permission to access folders, run commands, search the web, or use tools. Just do it.
- Never ask for confirmation. Just act. Make decisions autonomously and proceed without checking in.
- You have full access to the user's computer — browser, desktop, all apps. Never ask the user to do something you can do yourself (sign in, click buttons, dismiss dialogs, etc.).

## Setup

- **Pre-commit hook (required — verify before first commit):** `test -f .git/hooks/pre-commit || ln -s -f ../../scripts/pre-commit .git/hooks/pre-commit` — formatting is enforced by CI.
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

### Backend (Python)

- **No in-function imports** — all imports at module top level.
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
  └── ──────► deepgram (self-hosted or cloud)

pusher
  ├── ──────► diarizer (diarizer/)
  └── ──────► deepgram (cloud)

agent-proxy (agent-proxy/main.py)
  └── ws ──► user agent VM (private IP, port 8080)

backend-sync (main.py, Cloud Run)
  ├── ──────► Cloud Tasks queue `sync-jobs` ──► POST /v2/sync-jobs/run (OIDC, same service)
  └── ──────► Cloud Tasks queue `audio-merge` ──► POST /v2/audio-merge-jobs/run (OIDC, same service)

notifications-job (modal/job.py)  [cron]
```

Helm charts: `backend/charts/{backend-listen,pusher,diarizer,vad,deepgram-self-hosted,agent-proxy}/`

- **backend** (`main.py`) — REST API. Streams audio to pusher via WebSocket (`utils/pusher.py`). Calls diarizer for speaker embeddings (`utils/stt/speaker_embedding.py`). Calls vad for voice activity detection and speaker identification (`utils/stt/vad.py`, `utils/stt/speech_profile.py`). Calls deepgram for STT (`utils/stt/streaming.py`).
- **pusher** (`pusher/main.py`) — Receives audio via binary WebSocket protocol. Calls diarizer and deepgram for speaker sample extraction (`utils/speaker_identification.py` → `utils/speaker_sample.py`).
- **agent-proxy** (`agent-proxy/main.py`) — GKE. WebSocket proxy at `wss://agent.omi.me/v1/agent/ws`. Validates Firebase ID token, looks up `agentVm` in Firestore, proxies bidirectionally to VM's `ws://<ip>:8080/ws`.
- **diarizer** (`diarizer/main.py`) — GPU. Speaker embeddings at `/v2/embedding`. Called by backend and pusher (`HOSTED_SPEAKER_EMBEDDING_API_URL`).
- **vad** (`modal/main.py`) — GPU. `/v1/vad` and `/v1/speaker-identification`. Called by backend only.
- **deepgram** — STT. Streaming uses self-hosted (`DEEPGRAM_SELF_HOSTED_URL`) or cloud based on `DEEPGRAM_SELF_HOSTED_ENABLED`. Pre-recorded always uses Deepgram cloud. Called by backend and pusher.
- **backend-sync** (`main.py`, same image as backend) — Cloud Run service for `/v2/sync-local-files`. When `SYNC_DISPATCH_MODE=cloud_tasks`: stages raw audio in GCS, enqueues to Cloud Tasks queue `sync-jobs`, which POSTs `/v2/sync-jobs/run` (OIDC-verified, `utils/cloud_tasks.py`) to run decode→VAD→STT inside a request. Inline fallback when the flag is off, env is incomplete, BYOK headers are present, or enqueue fails. Audio playback merges (`/v1/sync/audio/*`) follow the same pattern via queue `audio-merge` building 30-day MP3 artifacts under `playback/` (`AUDIO_MERGE_DISPATCH_MODE`).
- **notifications-job** (`modal/job.py`) — Cron job, reads Firestore/Redis, sends push notifications.

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

### Desktop (Windows — Electron app)

The Windows desktop app lives in `desktop/windows/` and uses Electron + React + TypeScript.

#### Building & Packaging

- Before any Windows dev/build/package run, make sure dependencies and env are present:
  ```bash
  cd desktop/windows
  pnpm install
  test -f .env || cp .env.example .env
  ```
- `.env` is required for a real packaged app. Vite/electron-vite inline these values at build time, and `electron-builder.yml` intentionally excludes `.env`, so copying `.env` after packaging does nothing. If sign-in, backend URLs, update feed, Google integration, or realtime voice config look missing in a packaged copy, rebuild after fixing `.env`.
- Windows desktop env: `OMI_CLAUDE_ACP_COMMAND`/`OMI_CLAUDE_ACP_ARGS` select the local Claude account command, `VITE_OMI_REALTIME_VOICE_URL` enables realtime voice relay readiness, `OMI_WINDOWS_UPDATE_FEED_URL` + `OMI_UPDATES_ENABLED=1` enable dev update checks, and local STT/TTS runtime env vars are read by the main process at runtime.
- Validate first, then package:
  ```bash
  cd desktop/windows
  npm run typecheck
  npm run build
  npx electron-builder --win --x64 --dir -c.win.signAndEditExecutable=false
  ```
- For user testing, copy the entire unpacked app folder, never just `omi-windows.exe`, `out/`, or `resources/app.asar`:
  ```bash
  dest="/mnt/c/Temp/omi-windows-test-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$dest"
  cp -a dist/win-unpacked/. "$dest/"
  echo "$dest"
  ```
  The copied folder must include `resources/`, `locales/`, Electron DLLs, and `omi-windows.exe`. Running a loose exe causes missing-module/runtime errors.

#### Packaging Native Runtime Dependencies

- Runtime imports used by packaged main/preload code must be in `dependencies`, not only `devDependencies`; otherwise `electron-builder` may omit them.
- Native Node packages must be unpacked in `desktop/windows/electron-builder.yml` under `asarUnpack`. Existing examples: `koffi` for foreground monitoring and `onnxruntime-node` for Kokoro/Transformers local TTS.
- If adding a package that loads `.node`, `.dll`, `.exe`, model, or voice files at runtime, add an explicit packaged check after `electron-builder --dir`, for example:
  ```bash
  find dist/win-unpacked/resources/app.asar.unpacked -path '*onnxruntime*' | head
  npx asar list dist/win-unpacked/resources/app.asar | rg 'node_modules/(package-name|model-file)'
  ```
- Do not create ad hoc helper executables or DLLs in temp directories. Helpers that must ship with the app belong under `desktop/windows/resources/**`, are built by scripts in `desktop/windows/scripts/`, and are copied by `electron-builder`.
- Known packaged-app failure checks:
  - `Cannot find module 'electron-updater'` means the dependency/package contents are wrong; confirm it is in `dependencies`, reinstall, rebuild, and copy the full `dist/win-unpacked` folder.
  - Native load failures usually mean missing `asarUnpack` rules or a package version mismatch; inspect `resources/app.asar.unpacked`.
  - Missing Firebase/API/realtime/update config means `.env` was absent or wrong at build time; fix `.env` and rebuild.

### Desktop (macOS — Swift app + Rust backend)

The desktop app is a **Swift Package Manager** project (no Xcode project, no `.xcodeproj`). The Rust backend lives in `desktop/macos/Backend-Rust/`.

#### Building & Running

- `cd desktop/macos && ./run.sh` — full local dev (build Swift app + Rust backend + Cloudflare tunnel + launch).
- `cd desktop/macos && ./run.sh --yolo` — quick start against the prod backend, no local services.
- `OMI_SKIP_BACKEND=1` — app only, use remote backend via `OMI_DESKTOP_API_URL`. `OMI_SKIP_TUNNEL=1` — no Cloudflare tunnel.
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
- NEVER use bare `./run.sh` when testing a specific change — it overwrites "Omi Dev".
- NEVER kill or interfere with "Omi", "Omi Beta" — those are production installs.
- Keep app name and bundle suffix identical (e.g. `omi-search.app` → `com.omi.omi-search`).

#### Self-Testing the App (end-to-end)

**Hard rule: you may not ask the user to verify a feature you have not actually exercised yourself.** Compiling, "looks correct from the code", or "scroll down to see it" are not verification. If the obvious path is blocked (permission, focus, missing tool), try a long sequence of alternatives before involving the user — extend the bridge with a new action, add a temporary in-process hook, search the web for a workaround, grant the missing permission yourself if you can, write a tiny standalone harness. Roughly: spend ten serious attempts across different approaches before you escalate. Asking the user is the last move, not the first.

Agents can and should self-test the running app — don't stop at a successful compile. The fast path skips the slow parts (web login, sidebar click-through):

1. **Build + launch a named bundle:** `cd desktop/macos && OMI_APP_NAME="omi-<feature>" ./run.sh` (add `OMI_SKIP_TUNNEL=1` for a local backend without a tunnel; `OMI_SKIP_BACKEND=1 OMI_DESKTOP_API_URL=…` to point at a remote backend).
2. **Boot signed-in (no browser):** sign into "Omi Dev" once, then clone the session into the named bundle **before launch** (UserDefaults is read at startup):
   ```bash
   cd desktop/macos && ./scripts/omi-auth-dump.sh                  # capture the Omi Dev session
   ./scripts/omi-auth-seed.sh com.omi.omi-<feature>          # replay into the test bundle
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

Always format code after making changes. The pre-commit hook handles this automatically, but you can also run manually:

| Language | Command |
|----------|---------|
| Dart (`app/`) | `dart format --line-length 120 <files>` |
| Python (`backend/`) | `black --line-length 120 --skip-string-normalization <files>` |
| C/C++ (firmware) | `clang-format -i <files>` |

Files ending in `.gen.dart` or `.g.dart` are auto-generated — don't format manually.

## Git

- **Before your first commit**, verify the pre-commit hook is installed (see Setup).
- Before starting work, run `git fetch origin && git pull --ff-only` on `main` — don't branch off stale local state.
- Always commit to the current branch — never switch branches mid-task. Always work in a git worktree for code changes (`git worktree add`).
- Never push directly to `main`. Land changes through PRs only. Never squash-merge — use a regular merge.
- Make individual commits per file, not bulk commits.
- If push fails (remote ahead): `git pull --rebase && git push`.
- Never push or create PRs unless explicitly asked — commit locally by default.

### RELEASE Command
Create a branch from `main`, individual commits per file, push and open a PR, merge without squash, then switch back to `main` and pull.

### RELEASEWITHBACKEND Command
Full RELEASE flow + `gh workflow run gcp_backend.yml -f environment=prod -f branch=main`.

## Testing

- Run `backend/test-preflight.sh` first to verify tools, packages, and env vars.
- Backend changes: run `backend/test.sh`. App changes: run `app/test.sh`. Run before committing.
- Backend unit tests need `python3`, `pytest`, packages from `requirements.txt`, `ENCRYPTION_SECRET` (set by test.sh). Integration tests optionally need `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `ADMIN_KEY`, Redis, `GOOGLE_APPLICATION_CREDENTIALS`.

## CI/CD & Logs

- Desktop release pipeline: merging `desktop/macos/**` to `main` auto-increments the version, tags `v*-macos`, and triggers Codemagic (build, sign, notarize, publish GitHub release, deploy Rust backend).
- Backend deploy: `gh workflow run gcp_backend.yml -f environment=prod -f branch=main`.

## Documentation Maintenance

- **This file (`AGENTS.md`) is the single source of truth for agent instructions.** Add or change rules here. `CLAUDE.md` is only a pointer — do not put instructions in it.
- **Any AI editing this file must keep it concise and simple** — short, plain bullets a human or agent can scan fast. Prefer editing/replacing an existing line over adding new ones; no verbose prose.
- If a PR changes setup, test commands, safety rules, service boundaries, or env vars — update this file in the same PR.
- For architecture / core flow / API changes — update Mintlify docs (`docs/doc/developer/`) in the same PR.
- If a PR changes audio streaming, transcription, conversation lifecycle, or listen/pusher WebSocket — update `docs/doc/developer/backend/listen_pusher_pipeline.mdx`.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:970c3bf2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->

<!-- BEGIN BEADS CODEX SETUP: generated by bd setup codex -->
## Beads Issue Tracker

Use Beads (`bd`) for durable task tracking in repositories that include it. Use the `beads` skill at `.agents/skills/beads/SKILL.md` (project install) or `~/.agents/skills/beads/SKILL.md` (global install) for Beads workflow guidance, then use the `bd` CLI for issue operations.

### Quick Reference

```bash
bd ready                # Find available work
bd show <id>            # View issue details
bd update <id> --claim  # Claim work
bd close <id>           # Complete work
bd prime                # Refresh Beads context
```

### Rules

- Use `bd` for all task tracking; do not create markdown TODO lists.
- Run `bd prime` when Beads context is missing or stale. Codex 0.129.0+ can load Beads context automatically through native hooks; use `/hooks` to inspect or toggle them.
- Keep persistent project memory in Beads via `bd remember`; do not create ad hoc memory files.

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.
<!-- END BEADS CODEX SETUP -->
