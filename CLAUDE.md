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

### Backend Service Map

The backend has 7 services. Here's how they talk to each other:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Shared State                             │
│  Firestore (users, conversations, memories, action_items, …)   │
│  Redis (cache, rate limits, pub/sub on 'cache_invalidation')    │
└──────────┬──────────────────────────────────┬───────────────────┘
           │                                  │
   ┌───────┴────────┐               ┌────────┴────────┐
   │ backend        │  WebSocket    │ pusher           │
   │ backend-sync   ├──────────────►│ /v1/trigger/…    │
   │ backend-integ. │  (binary      │                  │
   │ backend-listen │   protocol)   │ Also calls:      │
   │                │               │ → diarizer       │
   │ Calls:         │               │ → vad            │
   │ → diarizer     │               │ → speech-profile │
   │ → vad          │               └─────────────────-┘
   │ → speech-prof. │
   └────────────────┘
           │
   ┌───────┴──────────────────────────────────────────────────────┐
   │                   GPU Services (HTTP POST)                   │
   │  diarizer  /v2/embedding          (speaker embeddings)       │
   │  vad       /v1/vad                (voice activity detection) │
   │  speech-profile /v1/speaker-identification                   │
   └──────────────────────────────────────────────────────────────┘

   notifications-job: cron job, reads Firestore + Redis, sends push
```

**Communication protocols:**
- **backend-listen → pusher**: WebSocket with custom binary protocol (struct-packed headers, message types 101-105). See `utils/pusher.py` → `connect_to_trigger_pusher()`.
- **backend/pusher → diarizer**: HTTP POST to `HOSTED_SPEAKER_EMBEDDING_API_URL`. See `utils/stt/speaker_embedding.py`.
- **backend/pusher → vad**: HTTP POST to `HOSTED_VAD_API_URL` (results cached in Redis 24h). See `utils/stt/vad.py`.
- **backend/pusher → speech-profile**: HTTP POST to `HOSTED_SPEECH_PROFILE_API_URL`. See `utils/stt/speech_profile.py`.
- **All services → Firestore**: Shared database via `database/_client.py`.
- **All services → Redis**: Shared cache + pub/sub for cache invalidation via `database/redis_db.py` and `database/redis_pubsub.py`.

**Service discovery env vars:**
- `HOSTED_PUSHER_API_URL` — pusher WebSocket endpoint
- `HOSTED_VAD_API_URL` — VAD service
- `HOSTED_SPEAKER_EMBEDDING_API_URL` — diarizer
- `HOSTED_SPEECH_PROFILE_API_URL` — speaker identification

## App (Flutter)

### Localization Required

- All user-facing strings must use l10n. Use `context.l10n.keyName` instead of hardcoded strings. Add new keys to ARB files using `jq` (never read full ARB files - they're large and will burn tokens). See skill `add-a-new-localization-key-l10n-arb` for details.

- After modifying ARB files in `app/lib/l10n/`, regenerate the localization files:
```bash
cd app && flutter gen-l10n
```

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

- Never squash merge PRs — use regular merge
- Make individual commits per file, not bulk commits
- **RELEASE command**: When the user says "RELEASE", perform the full release flow:
  1. Create a new branch from main
  2. Make individual commits per changed file
  3. Push and create a PR
  4. Merge the PR (no squash — regular merge)
  5. Switch back to main and pull
- **RELEASEWITHBACKEND command**: Same as RELEASE, plus deploy the backend to production after merging:
  ```bash
  gh workflow run gcp_backend.yml -f environment=prod -f branch=main
  ```

## Testing

### Always Run Tests Before Committing
After making changes, always run the appropriate test script to verify your changes.

- **Backend changes**: Run `backend/test.sh`
- **App changes**: Run `app/test.sh`
