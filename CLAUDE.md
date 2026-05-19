# Omi Development Guide
<!-- Official guidance for writing these files:
     CLAUDE.md: https://docs.anthropic.com/en/docs/claude-code/memory
     AGENTS.md: https://developers.openai.com/codex/guides/agents-md
     Format spec: https://agents.md -->

## Behavior

- Never ask for permission to access folders, run commands, search the web, or use tools. Just do it.
- Never ask for confirmation. Just act. Make decisions autonomously and proceed without checking in.
- You have full access to the user's computer — browser, desktop, all apps. Never ask the user to do something you can do yourself (sign in, click buttons, dismiss dialogs, etc.).

## Setup

### Pre-commit Hook (required — install before first commit)
Formatting is enforced by CI. **Verify the hook exists before your first commit:**
```bash
# Check if installed:
test -f .git/hooks/pre-commit && echo "OK" || ln -s -f ../../scripts/pre-commit .git/hooks/pre-commit
```

### Mobile App
```bash
cd app && bash setup.sh ios    # or: bash setup.sh android
```

---

## Backend (Python)
<!-- Maintainers: @beastoin (service map, logging security), @Thinh (imports, memory mgmt) -->

### Rules
- **No in-function imports** — all imports at module top level.
- **Import hierarchy** (low → high): `database/` → `utils/` → `routers/` → `main.py`. Never import upward.
- **Memory management** — `del` byte arrays after processing, `.clear()` dicts/lists holding data.
- **Async I/O** — never `requests.*` in async (use `httpx.AsyncClient` pools from `utils/http_client.py`), never `Thread().start().join()` (use `critical_executor`/`storage_executor`), never `time.sleep()` in async (use `asyncio.sleep()`). Run `python scripts/scan_async_blockers.py` before committing.
- **`async def` vs `def` endpoints** — use `def` for endpoints that only call sync code (Firestore, Redis, file I/O). FastAPI runs `def` in a threadpool automatically. Only use `async def` when the endpoint genuinely `await`s something (httpx, file.read(), WebSocket, asyncio.sleep) or uses asyncio APIs directly (asyncio.create_task, asyncio.get_running_loop). Never call sync DB/storage/file functions directly inside `async def` — wrap with `await run_blocking(executor, func, args)`.
- **Blocking calls in async** — these block the event loop: `database.*` functions (Firestore sync SDK), `open()`/`shutil.*` (file I/O), `upload_*`/`delete_*` from storage (GCS SDK), `creds.refresh()` (Google auth HTTP). In `async def`, always offload via `await run_blocking(executor, func, args)` from `utils.executors`. Use `critical_executor` for auth/rate-limits, `db_executor` for Firestore/Redis CRUD, `llm_executor` for LLM calls, `storage_executor` for GCS/file I/O, `postprocess_executor` for coordinators, `sync_executor` for STT/VAD. See `backend/CLAUDE.md` for full pool assignment rules. Never use bare `asyncio.to_thread()` (it uses the shared default pool — saturation stalls DNS and other asyncio internals).

### Logging Security
Never log raw sensitive data. Use `sanitize()` and `sanitize_pii()` from `utils.log_sanitizer`.
- `sanitize()` for `response.text`, API responses, error bodies.
- `sanitize_pii()` for names, emails, user text.
- Keep UIDs, IPs, status codes visible for debugging.
- Never put raw `response.text` in exception messages.

### Service Map
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

---

## App (Flutter)
<!-- Maintainers: @Thinh (l10n, formatting) -->

### Localization
- All user-facing strings must use l10n: `context.l10n.keyName` instead of hardcoded strings.
- Add new keys via `jq` (never read full ARB files). See skill `add-a-new-localization-key-l10n-arb`.
- **Translate all 48 non-English locales** — no English text in non-English ARB files. The exact list is whatever `ls app/lib/l10n/app_*.arb` returns minus `app_en.arb`; don't hardcode a count from memory. After adding any key, run the `omi-add-missing-language-keys-l10n` skill to fill missing translations, then verify with `cd app && flutter gen-l10n` — zero "untranslated message(s)" warnings means done.
- Regenerate after changes: `cd app && flutter gen-l10n`

### Firebase Prod Config
Never run `flutterfire configure` — it overwrites prod credentials. Prod config files in `app/ios/Config/Prod/`, `app/lib/firebase_options_prod.dart`, `app/android/app/src/prod/`.

### Verifying UI Changes (agent-flutter)
After editing Flutter UI code, **verify programmatically** — don't just hot restart and hope.

```bash
kill -SIGUSR2 $(pgrep -f "flutter run" | head -1)                # hot restart
AGENT_FLUTTER_LOG=/tmp/flutter-run.log agent-flutter connect      # reconnect after restart
agent-flutter snapshot -i                                         # see interactive widgets
agent-flutter find type button press                              # find and tap
agent-flutter fill @e5 "hello"                                    # type into textfield
agent-flutter screenshot /tmp/evidence.png                        # PR evidence
```

**Key rules:**
- Re-snapshot before every interaction (refs go stale). Use `press x y` as coordinate fallback.
- `AGENT_FLUTTER_LOG` must point to flutter run stdout (not logcat).
- `find type X` / `find text "label"` is more stable than `@ref` numbers.
- Add `Key('descriptive_name')` to new interactive widgets for `find key`.
- See `app/e2e/SKILL.md` for navigation architecture, screen map, and known flows.

---

## Desktop (macOS)

### Building & Running
- `./run.sh` — full local dev (build + backend + tunnel + app)
- `./run.sh --yolo` — quick start with prod backend, no local services
- Release builds are handled entirely by Codemagic CI (no local release script)
- Build command: `xcrun swift build -c debug --package-path Desktop` (the `xcrun` prefix is required)
- **DO NOT** use bare `swift build`, `xcodebuild`, or launch from `build/` directly

### Named Test Bundles
When testing a feature or bug fix, **always create a separate named bundle**:
```bash
OMI_APP_NAME="omi-fix-rewind" ./run.sh
```
This installs to `/Applications/omi-fix-rewind.app` with bundle ID `com.omi.omi-fix-rewind`.

**Rules:**
- **ALWAYS prefix with `omi-`** (e.g., `omi-fix-rewind`, `omi-6512-polling`, `omi-vision-test`) so bundles are grouped in `/Applications/`
- NEVER use bare `./run.sh` when testing a specific change — it overwrites "Omi Dev"
- NEVER kill or interfere with "Omi", "Omi Beta" — those are production installs
- Keep app name and bundle suffix identical (e.g., `omi-search.app` → `com.omi.omi-search`)
- Named bundles get their own permissions, auth state, and database
- After building, launch and interact programmatically to confirm it runs — don't stop at compile

### Verifying UI Changes (agent-swift)
After editing Swift UI code, **verify programmatically** via macOS Accessibility API:

```bash
agent-swift connect --bundle-id com.omi.omi-fix-rewind           # connect to named bundle
agent-swift snapshot -i                                           # interactive elements only
agent-swift click @e3                                             # CGEvent click (SwiftUI)
agent-swift press @e3                                             # AXPress (AppKit buttons)
agent-swift fill @e5 "text"                                       # type into field
agent-swift wait text "Settings"                                  # wait for text
agent-swift screenshot /tmp/evidence.png                          # PR evidence
```

**Key rules:**
- Prefer `click` over `press` for SwiftUI (CGEvent triggers NavigationLink; AXPress is AppKit only).
- Re-snapshot before every interaction (refs go stale).
- Always use `snapshot -i` (interactive only) — full snapshots are very verbose.
- `agent-swift doctor` verifies Accessibility permission.
- Dev bundle ID: `com.omi.desktop-dev`. Prod: `com.omi.computer-macos`.
- See `desktop/e2e/SKILL.md` for navigation architecture and known flows.

---

## Computer Control (clicking, typing, screenshots)

For controlling the Mac GUI. Use the **right tool for each job**:

| Task | Tool | Example |
|------|------|---------|
| Click at coordinates | `cliclick` | `cliclick c:X,Y` |
| Screenshots/OCR | `codriver` | `mcp__codriver__desktop_screenshot` (scale: 0.5) |
| Native macOS app testing | `agent-swift` | See Desktop section above |
| Browser automation | `playwright` MCP | Headless, most reliable |
| Existing browser tabs | `claude-in-chrome` | Only when extension connected |

**Workflow:** screenshot (`codriver`) → find target → click (`cliclick c:X,Y`)

**Rules:**
- NEVER try 3+ different click tools for the same action — pick one and commit.
- `codriver` at `scale: 0.5` → multiply coordinates by 2 before clicking.
- Prefer `cliclick` over `automac`/`mac-use-mcp` (coordinate bugs on multi-monitor).

---

## Formatting
<!-- Maintainers: @Thinh (Jan 19) -->

The pre-commit hook auto-formats, but you can run manually:

| Language | Command |
|----------|---------|
| Dart (`app/`) | `dart format --line-length 120 <files>` |
| Python (`backend/`) | `black --line-length 120 --skip-string-normalization <files>` |
| C/C++ (firmware) | `clang-format -i <files>` |

Files ending in `.gen.dart` or `.g.dart` are auto-generated — don't format manually.

---

## Git
<!-- Maintainers: @AaravGarg (original, Feb 2), @NikShevchenko (push rules, Mar 3) -->

### Rules
- **Before your first commit**, verify the pre-commit hook is installed: `test -f .git/hooks/pre-commit || ln -s -f ../../scripts/pre-commit .git/hooks/pre-commit`
- Always commit to the current branch — never switch branches.
- Never push directly to `main`. Land changes through PRs only.
- Never squash merge PRs — use regular merge.
- Make individual commits per file, not bulk commits.
- If push fails (remote ahead): `git pull --rebase && git push`.
- Never push or create PRs unless explicitly asked — commit locally by default.
- Always work in a git worktree for code changes. Use `EnterWorktree` to isolate work.
- Before creating a worktree or branch, run `git fetch origin && git pull --ff-only` on `main` — don't branch off stale local state.

### RELEASE Command
Create branch from `main`, individual commits per file, push/create PR, merge without squash, switch back to `main` and pull.

### RELEASEWITHBACKEND Command
Full RELEASE flow + `gh workflow run gcp_backend.yml -f environment=prod -f branch=main`.

---

## Testing
Run `backend/test-preflight.sh` to verify environment. Run `backend/test.sh` (backend) or `app/test.sh` (app) before committing.

## CI/CD
See [docs/runbooks/deploy.md](docs/runbooks/deploy.md) for deploy triggers and checks.

## Logs
See [docs/runbooks/logging.md](docs/runbooks/logging.md) for log commands.

## Documentation Maintenance
- If a PR changes setup, test commands, safety rules, service boundaries, or env vars — update this file in the same PR.
- Keep `AGENTS.md` synced with this file. Update both in the same commit.
- For architecture/core flow/API changes — update Mintlify docs (`docs/`) in the same PR.
- If a PR changes audio streaming, transcription, conversation lifecycle, or listen/pusher WebSocket — update `docs/doc/developer/backend/listen_pusher_pipeline.mdx`.



# Omi Windows — Dioxus Desktop App (Full Feature Parity, Self-Hosted)

Build a fully self-hosted Windows clone of the macOS Omi desktop app using Dioxus for UI and the existing `Backend-Rust/` as a sidecar local server.

---

## What We Reuse from This Repo

### Direct Reuse (~30%) — copy and run unchanged

| What | Repo Path | Notes |
|------|-----------|-------|
| **Rust backend server** | `desktop/Backend-Rust/` | Sidecar process. Axum/Tokio, cross-platform. Auth, chat completions, Firestore, Redis, LLM proxy, TTS, updates. |
| **Agent runtime** | `desktop/agent/` | TypeScript/Node.js. Multi-provider AI chat. Spawned as child process. |
| **Full Python backend** | `backend/` | All 44 routers, database layer, LLM utils, prompts, transcription pipeline. Self-hosted via Docker. |
| **Plugins ecosystem** | `plugins/` | 20+ integrations (Slack, GitHub, Notion, etc.). Works with Python backend unchanged. |
| **SDKs** | `sdks/` | Python, Swift, React Native SDKs for external tools against your self-hosted instance. |
| **Prompts** | `backend/utils/prompts.py` | Used internally by Python backend. No porting needed. |

### Logic Port (~40%) — read the Swift, write equivalent Rust/Dioxus

| What | macOS Source | What we port |
|------|-------------|--------------|
| **App state** | `Desktop/Sources/AppState.swift` (127KB) | State structure → Dioxus signals/context |
| **Audio codec** | `Desktop/Sources/Audio/AudioCodecDecoder.swift` | Opus/μ-law decoding logic |
| **Transcription** | `Desktop/Sources/TranscriptionService.swift` | Start/stop/segment lifecycle |
| **VAD gate** | `Desktop/Sources/VADGateService.swift` | Voice activity detection thresholds |
| **Audio mixing** | `Desktop/Sources/AudioMixer.swift` | Mic + system audio mix logic |
| **Floating bar** | `Desktop/Sources/FloatingControlBar/` (18 files) | Overlay window behavior |
| **Page layouts** | `Desktop/Sources/MainWindow/Pages/` (20 files) | UI structure → Dioxus RSX |
| **Proactive assistants** | `Desktop/Sources/ProactiveAssistants/` (50 files) | Trigger rules + scheduling |
| **Rewind timeline** | `Desktop/Sources/Rewind/UI/` (9 files) | Timeline scrubber + search UX |
| **BLE protocol** | `Desktop/Sources/Bluetooth/DeviceUUIDs.swift` | UUID constants + codec IDs (~200 lines) |
| **DB schema** | `Desktop/Sources/Rewind/Core/RewindModels.swift` | SQLite table definitions → rusqlite |

### New Code (~30%) — no macOS equivalent

| What | Why |
|------|-----|
| **DXGI screen capture** | macOS uses ScreenCaptureKit; Windows needs DXGI Desktop Duplication API |
| **WASAPI audio capture** | macOS uses CoreAudio; Windows needs WASAPI loopback via `cpal` |
| **Windows OCR** | macOS uses Vision framework; Windows uses `Windows.Media.Ocr` |
| **System tray** | macOS uses NSStatusItem; Windows needs `tray-icon` crate |
| **Global hotkeys** | macOS uses CGEvent tap; Windows needs `global-hotkey` crate |
| **Windows installer** | macOS uses DMG; Windows needs MSI/NSIS |
| **Docker Compose** | Self-hosted Python backend + Redis + Firestore emulator |

---

## Architecture

```
omi-windows/
├── crates/
│   ├── omi-app/              # Dioxus desktop app (main binary)
│   │   ├── src/
│   │   │   ├── main.rs        # Launch Dioxus + spawn backend sidecar
│   │   │   ├── app.rs         # Root component, routing, app state
│   │   │   ├── pages/         # UI pages (see Pages section)
│   │   │   ├── components/    # Shared UI components
│   │   │   ├── hooks/         # Custom Dioxus hooks (auth, audio, etc.)
│   │   │   └── assets/        # CSS (Tailwind via dioxus CLI), icons
│   │   └── Cargo.toml
│   │
│   ├── omi-capture/           # Screen capture + OCR (Windows-specific)
│   │   ├── src/
│   │   │   ├── dxgi.rs        # DXGI Desktop Duplication API
│   │   │   ├── ocr.rs         # Windows.Media.Ocr via windows crate
│   │   │   ├── video_chunk.rs # Frame → H.264 chunk encoder
│   │   │   └── lib.rs
│   │   └── Cargo.toml
│   │
│   ├── omi-audio/             # Mic + system audio capture
│   │   ├── src/
│   │   │   ├── mic.rs         # Mic input via cpal
│   │   │   ├── loopback.rs    # System audio via WASAPI loopback (cpal)
│   │   │   ├── mixer.rs       # Mix mic + system audio
│   │   │   ├── vad.rs         # Voice activity detection gate
│   │   │   └── lib.rs
│   │   └── Cargo.toml
│   │
│   ├── omi-ble/               # BLE wearable support
│   │   ├── src/
│   │   │   ├── scanner.rs     # btleplug device discovery
│   │   │   ├── protocol.rs    # Omi BLE protocol (UUIDs, codec IDs)
│   │   │   ├── connection.rs  # Connect/reconnect/stream audio
│   │   │   └── lib.rs
│   │   └── Cargo.toml
│   │
│   ├── omi-db/                # Local SQLite storage (mirrors RewindDatabase.swift)
│   │   ├── src/
│   │   │   ├── schema.rs      # Tables: screenshots, transcriptions, memories, action_items, goals
│   │   │   ├── screenshots.rs
│   │   │   ├── transcriptions.rs
│   │   │   ├── memories.rs
│   │   │   ├── action_items.rs
│   │   │   ├── migrations.rs
│   │   │   └── lib.rs
│   │   └── Cargo.toml
│   │
│   └── omi-transcription/     # Deepgram WebSocket client
│       ├── src/
│       │   ├── streaming.rs   # Real-time WebSocket transcription
│       │   ├── models.rs      # Transcript segments, speaker labels
│       │   └── lib.rs
│       └── Cargo.toml
│
├── backend/                   # Copy of desktop/Backend-Rust/ (sidecar)
├── agent/                     # Copy of desktop/agent/ (TypeScript, runs as child process)
├── Cargo.toml                 # Workspace root
└── README.md
```

## Key Rust Crates

| Crate | Purpose |
|-------|---------|
| `dioxus` (v0.6+) | UI framework (desktop target via webview) |
| `cpal` | Cross-platform audio I/O (mic + WASAPI loopback) |
| `windows` | Win32/WinRT APIs for DXGI capture + OCR |
| `btleplug` | BLE (Omi wearable) |
| `rusqlite` | Local SQLite DB |
| `tokio-tungstenite` | WebSocket client for Deepgram streaming |
| `reqwest` | HTTP client for Backend-Rust sidecar + Python backend |
| `serde` / `serde_json` | Serialization |
| `global-hotkey` | Global keyboard shortcuts (floating bar trigger) |
| `tray-icon` + `muda` | System tray icon + menu |

---

## Pages to Build (mapped from macOS SwiftUI)

| macOS Source | Dioxus Page | Features |
|-------------|-------------|----------|
| `DashboardPage.swift` | `pages/dashboard.rs` | Overview, recent conversations, stats |
| `ChatPage.swift` (64KB) | `pages/chat.rs` | AI chat with memory context, streaming responses |
| `ConversationsPage.swift` | `pages/conversations.rs` | List + detail view of past conversations |
| `MemoriesPage.swift` (81KB) | `pages/memories.rs` | Memory browser, search, edit |
| `TasksPage.swift` (222KB) | `pages/tasks.rs` | Action items, task detail, integrations |
| `RewindPage.swift` (74KB) | `pages/rewind.rs` | Screenshot timeline, search, playback |
| `SettingsPage.swift` (281KB) | `pages/settings.rs` | All settings (audio, capture, BLE, backend, auth) |
| `AppsPage.swift` (130KB) | `pages/apps.rs` | Plugin marketplace |
| `FocusPage.swift` | `pages/focus.rs` | Focus sessions |
| `PersonaPage.swift` | `pages/persona.rs` | AI persona config |
| `FloatingControlBarView.swift` | `components/floating_bar.rs` | Overlay bar (push-to-talk, quick AI, agent pills) |

---

## Implementation Milestones

### M1 — Project Scaffold + Backend Sidecar
- Create Cargo workspace with all crates (empty stubs)
- Dioxus desktop app launches, shows a window with system tray
- On startup, spawn `Backend-Rust` as a child process on `localhost:10201`
- Health check loop: poll `/health` until backend is ready
- Basic routing: sidebar nav between empty pages
- **Deliverable:** Window opens, backend runs, pages navigate

### M2 — Auth + Settings
- Firebase auth via system browser OAuth flow (port `AuthService.swift` logic)
- Store auth token, refresh automatically
- Settings page: backend URL (default `localhost`), Python backend URL, API keys
- Persist settings in local config file (`%APPDATA%/omi/config.json`)
- **Deliverable:** User can sign in, token stored, settings persist

### M3 — Audio Capture + Live Transcription
- `omi-audio`: mic capture via `cpal`, WASAPI loopback for system audio
- `omi-transcription`: Deepgram WebSocket streaming
- Mix mic + system audio, stream to Deepgram
- VAD gate: only send audio when speech detected (port `VADGateService.swift`)
- Live transcript UI in chat/dashboard
- **Deliverable:** Speak into mic → see real-time transcript

### M4 — Local Database + Conversations
- `omi-db`: SQLite schema matching `RewindDatabase.swift` tables
- Conversation lifecycle: start → accumulate transcript → end → summarize via LLM
- Store conversations, transcriptions locally
- Conversations page: list, search, detail view
- Sync to self-hosted Python backend via REST API
- **Deliverable:** Conversations captured, stored, browsable

### M5 — Screen Capture + OCR + Rewind
- `omi-capture`: DXGI Desktop Duplication for periodic screenshots (every 2-5 sec)
- OCR via `windows::Media::Ocr` (built into Windows 10+)
- Video chunk encoding (H.264 via `openh264` or frame-only JPEG storage)
- Store screenshots + OCR text in SQLite
- Rewind page: timeline scrubber, search by OCR text, app filter
- **Deliverable:** Screen history captured, searchable, browsable

### M6 — Chat + Memories + Action Items
- Chat page: streaming AI responses via Backend-Rust `/v2/chat/completions`
- Memory browser: view, search, edit extracted memories
- Action items: extract from conversations, display, manage
- Goals page
- **Deliverable:** Full AI chat with memory context

### M7 — Floating Control Bar + Shortcuts
- Transparent always-on-top Dioxus window (overlay)
- Global hotkey via `global-hotkey` crate (Cmd→Ctrl mapping)
- Push-to-talk: hold key → capture audio → transcribe → AI response
- Agent pills (proactive suggestions)
- **Deliverable:** Floating bar works like macOS version

### M8 — BLE Wearable Support
- `omi-ble`: scan, connect, pair Omi wearable via `btleplug`
- Port BLE protocol from `Bluetooth/DeviceUUIDs.swift` (service/char UUIDs)
- Audio codec decoding (port `AudioCodecDecoder.swift` — Opus/μ-law)
- Stream wearable audio → same transcription pipeline
- Device settings page
- **Deliverable:** Omi wearable pairs and streams on Windows

### M9 — Agent Runtime + Proactive Assistants
- Spawn `agent/` TypeScript runtime as child process (Node.js)
- IPC between Dioxus app and agent via stdio/WebSocket
- Proactive assistants: port trigger logic from `ProactiveAssistantsPlugin.swift`
- App/plugin marketplace integration
- **Deliverable:** Agents run, proactive suggestions appear

### M10 — Self-Hosted Python Backend
- Docker Compose file for the full Python backend stack:
  - `backend/main.py` (FastAPI)
  - `backend/pusher/` (WebSocket relay)
  - Firestore emulator or Postgres adapter
  - Redis
  - Deepgram (self-hosted or cloud key)
- One-command local setup: `docker compose up`
- Windows app defaults to `localhost` backend URLs
- **Deliverable:** Entire stack runs locally, no cloud dependency

---

## macOS → Windows API Mapping

| Feature | macOS API | Windows Equivalent (Rust crate) |
|---------|-----------|--------------------------------|
| Screen capture | ScreenCaptureKit | DXGI Desktop Duplication (`windows` crate) |
| System audio | CoreAudio tap | WASAPI loopback (`cpal`) |
| Microphone | AVAudioEngine | WASAPI (`cpal`) |
| OCR | Vision framework | `Windows.Media.Ocr` (`windows` crate) |
| BLE | CoreBluetooth | `btleplug` |
| Global hotkeys | CGEvent tap | `global-hotkey` crate |
| System tray | NSStatusItem | `tray-icon` + `muda` crates |
| Notifications | UNUserNotificationCenter | `winrt-notification` crate |
| Keychain | macOS Keychain | Windows Credential Manager (`keyring` crate) |
| Launch at login | SMAppService | Registry `HKCU\...\Run` |
| Local DB | GRDB (SQLite) | `rusqlite` |

---

## File Counts (effort estimate)

The macOS app has **~280 Swift source files** totaling ~3.5MB of code. Key large files:
- `SettingsPage.swift` — 281KB (will split into sub-components)
- `TasksPage.swift` — 222KB (will split into sub-components)
- `APIClient.swift` — 159KB (mostly HTTP calls → reuse Backend-Rust)
- `RewindDatabase.swift` — 139KB (port schema to rusqlite)
- `AppState.swift` — 127KB (port to Dioxus signals/context)

Estimated Rust LOC for full parity: **~40-50K lines** across all crates.

---

## What NOT to Port

- Apple Sign-In (use Google OAuth only on Windows)
- Apple Notes reader (`AppleNotesReaderService.swift`)
- macOS-specific permission dialogs (replace with Windows equivalents)
- `codemagic.yaml` CI (use GitHub Actions for Windows builds)
- DMG packaging (use MSI/NSIS installer instead)
