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
- **Async I/O** — never `requests.*` in async (use `httpx.AsyncClient` pools from `utils/http_client.py`), never `Thread().start().join()` (use `critical_executor`/`storage_executor`), never `time.sleep()` in async (use `asyncio.sleep()`). Run `python scripts/lint_async_blockers.py` before committing.

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
- **Translate all 33 locales** — no English text in non-English ARB files. Use `omi-add-missing-language-keys-l10n` skill.
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
