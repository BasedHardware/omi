# Coding Guidelines

## Behavior

- Never ask for permission to access folders, run commands, search the web, or use tools. Just do it.
- Never ask for confirmation. Just act. Make decisions autonomously and proceed without checking in.

## Setup

### Install Pre-commit Hook
Run once to enable auto-formatting on commit:
```bash
ln -s -f ../../scripts/pre-commit .git/hooks/pre-commit
```

## Backend

### No In-Function Imports
All imports must be at the module top level. Never import inside functions.

```python
# Bad
def my_function():
    from database.redis_db import r  # Don't do this
    r.get('key')

# Good
from database.redis_db import r

def my_function():
    r.get('key')
```

### Import from Lower-Level Modules
Follow the module hierarchy when importing. Higher-level modules import from lower-level modules, never the reverse.

**Module hierarchy (lowest to highest):**
1. `database/` - Database connections, cache instances
2. `utils/` - Utility functions, helpers
3. `routers/` - API endpoints
4. `main.py` - Application entry point

```python
# Bad - utils importing from routers or main
# utils/apps.py
from main import memory_cache  # Don't import from higher level
from routers.apps import some_function  # Don't import from higher level

# Good - utils importing from database
# utils/apps.py
from database.cache import get_memory_cache
from database.redis_db import r
```

### Memory Management

Free large objects immediately after use. E.g., `del` for byte arrays after processing, `.clear()` for dicts/lists holding data.

### Logging Security

Never log raw sensitive data. Use `sanitize()` and `sanitize_pii()` from `utils.log_sanitizer`.

```python
from utils.log_sanitizer import sanitize, sanitize_pii

# sanitize() — for response bodies, error text, API responses
logger.error(f"Token exchange failed: {sanitize(response.text)}")

# sanitize_pii() — for known personal data (names, emails, user text)
logger.info(f"Found contact: {sanitize_pii(name)} -> {sanitize_pii(email)}")
```

Rules:
- `sanitize()` for `response.text`, API responses, error bodies (masks token-like 8+ char strings with digits)
- `sanitize_pii()` for names, emails, user text (always masks regardless of content)
- Keep log levels as-is (don't downgrade to hide data)
- Keep UIDs, IPs, status codes, and structural info visible — they're needed for debugging
- Never put raw `response.text` in exception messages (exceptions may be logged upstream)

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

- **backend** (`main.py`) — REST API. Streams audio to pusher via WebSocket (`utils/pusher.py`). Calls diarizer for speaker embeddings (`utils/stt/speaker_embedding.py`). Calls vad for voice activity detection and speaker identification (`utils/stt/vad.py`, `utils/stt/speech_profile.py`). Calls deepgram for STT (`utils/stt/streaming.py`).
- **pusher** (`pusher/main.py`) — Receives audio via binary WebSocket protocol. Calls diarizer and deepgram for speaker sample extraction (`utils/speaker_identification.py` → `utils/speaker_sample.py`).
- **agent-proxy** (`agent-proxy/main.py`) — GKE. WebSocket proxy at `wss://agent.omi.me/v1/agent/ws`. Validates Firebase ID token, looks up `agentVm` in Firestore, proxies bidirectionally to VM's `ws://<ip>:8080/ws`. VM credentials never leave the server.
- **diarizer** (`diarizer/main.py`) — GPU. Speaker embeddings at `/v2/embedding`. Called by backend and pusher (`HOSTED_SPEAKER_EMBEDDING_API_URL`).
- **vad** (`modal/main.py`) — GPU. `/v1/vad` (voice activity detection) and `/v1/speaker-identification` (speaker matching). Called by backend only (`HOSTED_VAD_API_URL`, `HOSTED_SPEECH_PROFILE_API_URL`).
- **deepgram** — STT. Streaming uses self-hosted (`DEEPGRAM_SELF_HOSTED_URL`) or cloud based on `DEEPGRAM_SELF_HOSTED_ENABLED` (`utils/stt/streaming.py`). Pre-recorded always uses Deepgram cloud (`utils/stt/pre_recorded.py`). Called by backend and pusher.
- **notifications-job** (`modal/job.py`) — Cron job that reads Firestore/Redis and sends push notifications.

**Keep this map up to date.** When adding, removing, or changing inter-service calls (HTTP, WebSocket, new env vars), update this section and the matching section in `AGENTS.md`.

## App (Flutter)

### Localization Required

- All user-facing strings must use l10n. Use `context.l10n.keyName` instead of hardcoded strings. Add new keys to ARB files using `jq` (never read full ARB files - they're large and will burn tokens). See skill `add-a-new-localization-key-l10n-arb` for details.

- **Translate all locales**: When adding new l10n keys, provide real translations for all 33 non-English locales — do not leave English text in non-English ARB files. Use the `omi-add-missing-language-keys-l10n` skill to generate proper translations. Ensure `{parameter}` placeholders match the English ARB exactly.

- After modifying ARB files in `app/lib/l10n/`, regenerate the localization files:
```bash
cd app && flutter gen-l10n
```

### Running the iOS Simulator

```bash
xcrun simctl list devices | grep Booted  # get device ID
cd app && flutter run -d <device-id> --flavor dev   # dev backend (api.omiapi.com)
cd app && flutter run -d <device-id> --flavor prod   # prod backend (api.omi.me)
```

See `/local-dev mobile` skill for full setup details, env file configuration, and troubleshooting.

### Firebase Prod Config

Never run `flutterfire configure` — it will overwrite prod credentials with the wrong project.

Prod credential files (already correct, do not regenerate):
- `app/ios/Config/Prod/GoogleService-Info.plist`
- `app/lib/firebase_options_prod.dart`
- `app/android/app/src/prod/google-services.json`
- `app/ios/Flutter/prod{Debug,Release,Profile}.xcconfig`

### Simulator Hot Restart

When the iOS Simulator is running, trigger a hot restart after finishing edits — do not wait for the user to do it manually:

```bash
kill -SIGUSR2 $(pgrep -f "flutter run" | head -1)
```

Use `SIGUSR1` for hot reload (widget/UI-only changes) or `SIGUSR2` for hot restart (logic, state, provider changes). When in doubt, use `SIGUSR2`.

## Formatting

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

### After Completing Work
When you finish implementing a task, **commit and push your changes** before ending the conversation:

1. Stage only the files you modified:
   ```bash
   git add <file1> <file2> ...
   ```
2. Commit with a clear message (verb-first, max 72 chars):
   ```bash
   git commit -m "Fix race condition in VAD gate service"
   ```
3. Push to the current branch:
   ```bash
   git push
   ```

### Rules
- **Always commit to the current branch** — never switch branches
- **Never squash merge PRs** — use regular merge
- Make individual commits per file, not bulk commits
- The pre-commit hook auto-formats staged code — no need to format manually before committing
- If push fails because the remote is ahead, pull with rebase first: `git pull --rebase && git push`

### Desktop Changelog
When completing a task that changes `desktop/**` with user-visible impact, append a one-liner to the `unreleased` array in `desktop/CHANGELOG.json` — see `desktop/CLAUDE.md` for format.

### RELEASE command
When the user says "RELEASE", perform the full release flow:
  1. Create a new branch from main
  2. Make individual commits per changed file
  3. Push and create a PR
  4. Merge the PR (no squash — regular merge)
  5. Switch back to main and pull

### RELEASEWITHBACKEND command
Same as RELEASE, plus deploy the backend to production after merging:
  ```bash
  gh workflow run gcp_backend.yml -f environment=prod -f branch=main
  ```

## CI/CD Auto-Deploy (push to main)

### Python Backend (dev)
- **Trigger**: push to `main` with `backend/**` changes
- **Workflow**: GitHub Actions `gcp_backend_auto_dev.yml`
- **Deploys to**: Cloud Run + GKE (dev environment)
- **Check**: `gh run list --workflow=gcp_backend_auto_dev.yml --limit=3`

### Python Backend (prod) — manual only
- **Never auto-deploys.** Must trigger manually:
  ```bash
  gh workflow run gcp_backend.yml -f environment=prod -f branch=main
  ```

### Mobile App (iOS TestFlight + Android) — Codemagic
- **Trigger**: push to `main` with `app/**` changes
- **Workflow**: `ios-internal-auto` / `android-internal-auto` in `codemagic.yaml`
- **IMPORTANT**: Codemagic **skips** if the build number in `app/pubspec.yaml` is already on TestFlight. After merging `app/**` changes, you **must bump the build number** or no new build will be uploaded:
  ```bash
  # In app/pubspec.yaml, increment the +N build number:
  # version: 1.0.525+760  →  version: 1.0.525+761
  ```
- **Check**: `curl -s -H "x-auth-token: $CODEMAGIC_API_TOKEN" "https://api.codemagic.io/builds?appId=66c95e6ec76853c447b8bcbb&limit=5"`

### Desktop App (macOS) — GitHub Actions + Codemagic
- **Trigger**: push to `main` with `desktop/**` changes
- **Step 1**: GitHub Actions `desktop_auto_release.yml` auto-increments version, pushes `v*-macos` tag
- **Step 2**: Codemagic `omi-desktop-swift-release` builds, signs, notarizes, publishes

## Logs

### Flutter (iOS Simulator)
App logs go to `/tmp/flutter-run.log`. Use `print()` (not `Logger.debug`) for logs that must appear there. Grep with `[TagName]` prefixes:
```bash
grep -E "\[AgentChat\]|\[HomePage\]" /tmp/flutter-run.log | tail -20
```

### Backend (Cloud Run)
```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="backend-listen"' --project=based-hardware --limit=30 --freshness=5m --format=json
```

### Agent-proxy (GKE, namespace `prod-omi-backend`)
```bash
kubectl logs -n prod-omi-backend -l app=agent-proxy --timestamps --since=10m | grep "<uid>"
```

### Agent VM
```bash
gcloud compute ssh omi-agent-<id> --zone=us-central1-a --project=based-hardware \
  --command="journalctl -u omi-agent --no-pager --since '10 minutes ago' | grep -E 'Client|Query|Prewarm|session|disconnect|error|Persistent'"
```

### Agent Chat Debugging
For end-to-end debugging of the mobile agent chat pipeline (phone → agent-proxy → VM), see the `ai-chat-debug` skill.

## Testing

### Always Run Tests Before Committing
After making changes, always run the appropriate test script to verify your changes.

- **Backend changes**: Run `backend/test.sh`
- **App changes**: Run `app/test.sh`
