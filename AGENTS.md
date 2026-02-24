# Codex Agent Rules

These rules apply to Codex when working in this repository.

## Setup

- Install pre-commit hook: `ln -s -f ../../scripts/pre-commit .git/hooks/pre-commit`

## Coding Guidelines

### Backend

- No in-function imports. All imports must be at the module top level.
- Follow the module hierarchy when importing. Higher-level modules import from lower-level modules, never the reverse.

Module hierarchy (lowest to highest):
1. `database/`
2. `utils/`
3. `routers/`
4. `main.py`

- Memory management: free large objects immediately after use. E.g., `del` for byte arrays after processing, `.clear()` for dicts/lists holding data.

#### Backend Service Map

Services: backend (+ backend-sync, backend-integration, backend-listen — same codebase), pusher, diarizer, vad (models), notifications-job.

Inter-service communication:
- backend-listen → pusher: WebSocket with binary protocol (`utils/pusher.py` → `connect_to_trigger_pusher()`)
- backend-listen → diarizer: HTTP POST for real-time speaker embeddings (`routers/transcribe.py` → `utils/stt/speaker_embedding.py`, env `HOSTED_SPEAKER_EMBEDDING_API_URL`)
- backend-listen & pusher → vad, speech-profile: both call these via `postprocess_conversation` (`utils/conversations/postprocess_conversation.py`). Pusher triggers via `process_conversation` after receiving audio. VAD results cached in Redis 24h.
- All services share Firestore (`database/_client.py`) and Redis (`database/redis_db.py`) for cache + pub/sub (`cache_invalidation` channel via `database/redis_pubsub.py`)
- notifications-job: cron, reads Firestore + Redis, sends push notifications

### App (Flutter)

- All user-facing strings must use l10n (`context.l10n.keyName`). Add keys to ARB files using `jq` to avoid reading large files.
- After modifying ARB files in `app/lib/l10n/`, regenerate localizations: `cd app && flutter gen-l10n`

## Formatting

Always format code after making changes. The pre-commit hook handles this automatically, but you can also run manually:

- **Dart (app/)**: `dart format --line-length 120 <files>`
  - Files ending in `.gen.dart` or `.g.dart` are auto-generated and should not be formatted manually.
- **Python (backend/)**: `black --line-length 120 --skip-string-normalization <files>`
- **C/C++ (firmware: omi/, omiGlass/)**: `clang-format -i <files>`

## Testing

- Always run tests before committing:
  - Backend changes: run `backend/test.sh`
  - App changes: run `app/test.sh`