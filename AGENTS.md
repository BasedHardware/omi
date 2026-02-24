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

```
              ┌───────────────────────────────┐
              │  Firestore · Redis (shared)   │
              └─────┬─────────────────┬───────┘
                    │                 │
          ┌────────┴───┐       ┌─────┴──────┐
          │  backend   │──ws──▶│  pusher     │
          │  main.py   │       │  pusher/    │
          └──┬───┬─────┘       └──┬───┬──────┘
             │   │                │   │
             │   └────┬───────────┘   │
             │        ▼               │
             │   ┌──────────┐         │
             │   │ diarizer │         │
             │   │ diarizer/│         │
             │   └──────────┘         │
             │                        │
             └──────────┬─────────────┘
                        ▼
              ┌───────────────────┐
              │   vad · speech-   │
              │   profile         │
              │   modal/          │
              └───────────────────┘

          notifications-job (modal/job.py)
              cron · Firestore · Redis
```

- **backend** (`main.py`) — REST API. Streams audio to pusher via WebSocket (`utils/pusher.py`). Calls diarizer for speaker embeddings during transcription (`routers/transcribe.py`).
- **pusher** (`pusher/main.py`) — Receives audio via binary WebSocket protocol. Runs `process_conversation` which calls vad and speech-profile (`utils/conversations/postprocess_conversation.py`).
- **diarizer** (`diarizer/main.py`) — Speaker embeddings. Called from backend via `utils/stt/speaker_embedding.py` (`HOSTED_SPEAKER_EMBEDDING_API_URL`).
- **vad** (`modal/main.py`) — Voice activity detection. Called via `utils/stt/vad.py` (`HOSTED_VAD_API_URL`). Results cached in Redis 24h.
- **speech-profile** (`modal/main.py`) — Speaker identification. Called via `utils/stt/speech_profile.py` (`HOSTED_SPEECH_PROFILE_API_URL`).
- **notifications-job** (`modal/job.py`) — Cron job, reads Firestore/Redis, sends push notifications.

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