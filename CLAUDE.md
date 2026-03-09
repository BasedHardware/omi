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

### Firebase Prod Config
Never run `flutterfire configure` — it overwrites prod credentials. Prod config files in `app/ios/Config/Prod/`, `app/lib/firebase_options_prod.dart`, `app/android/app/src/prod/`.

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

## Testing

### Unit Tests
Run `backend/test-preflight.sh` to verify environment. Run `backend/test.sh` (backend) or `app/test.sh` (app) before committing.

### E2E Tests (agent-flutter)

The app supports widget-level E2E testing via [agent-flutter](https://github.com/beastoin/agent-flutter) + Marionette (already integrated in debug builds).

**Prerequisites:** Android emulator running, Node.js 18+, `npm install -g agent-flutter-cli`.

**Quick start:**
```bash
# Run all 4 E2E flows (auto-starts flutter run if needed)
app/e2e/run-all.sh

# Or with an existing flutter run session
AGENT_FLUTTER_LOG=/tmp/flutter-run.log app/e2e/run-all.sh
```

**Manual usage:**
```bash
agent-flutter doctor              # verify setup
agent-flutter connect             # connect to running app
agent-flutter snapshot -i         # list interactive widgets
agent-flutter press @e3           # tap by ref
agent-flutter find type button press  # find and tap
agent-flutter screenshot out.png  # capture screen
```

**Key rules for writing E2E scripts:**
- Always re-snapshot after UI mutations (`press`, `scroll`, `fill`) — refs go stale.
- Use `AGENT_FLUTTER_LOG` pointing to flutter run's stdout log (not logcat) for reliable auto-detect.
- Prefer `find type X` over hardcoded `@ref` numbers for stability.
- See `app/e2e/README.md` for env vars, flow coverage, and helper API.
