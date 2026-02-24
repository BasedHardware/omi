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
Shared: Firestore, Redis

backend (main.py)
  ├── ws ──► pusher (pusher/)
  ├── ──────► diarizer (diarizer/)
  ├── ──────► vad (modal/)
  └── ──────► deepgram (self-hosted or cloud)

pusher
  ├── ──────► diarizer (diarizer/)
  └── ──────► deepgram (cloud)

notifications-job (modal/job.py)  [cron]
```

Helm charts: `backend/charts/{backend-listen,pusher,diarizer,vad,deepgram-self-hosted}/`

- **backend** (`main.py`) — REST API. Streams audio to pusher via WebSocket (`utils/pusher.py`). Calls diarizer for speaker embeddings (`utils/stt/speaker_embedding.py`). Calls vad for voice activity detection and speaker identification (`utils/stt/vad.py`, `utils/stt/speech_profile.py`). Calls deepgram for STT (`utils/stt/streaming.py`).
- **pusher** (`pusher/main.py`) — Receives audio via binary WebSocket protocol. Calls diarizer and deepgram for speaker sample extraction (`utils/speaker_identification.py` → `utils/speaker_sample.py`).
- **diarizer** (`diarizer/main.py`) — GPU. Speaker embeddings at `/v2/embedding`. Called by backend and pusher (`HOSTED_SPEAKER_EMBEDDING_API_URL`).
- **vad** (`modal/main.py`) — GPU. `/v1/vad` (voice activity detection) and `/v1/speaker-identification` (speaker matching). Called by backend only (`HOSTED_VAD_API_URL`, `HOSTED_SPEECH_PROFILE_API_URL`).
- **deepgram** — STT. Streaming uses self-hosted (`DEEPGRAM_SELF_HOSTED_URL`) or cloud based on `DEEPGRAM_SELF_HOSTED_ENABLED` (`utils/stt/streaming.py`). Pre-recorded always uses Deepgram cloud (`utils/stt/pre_recorded.py`). Called by backend and pusher.
- **notifications-job** (`modal/job.py`) — Cron job, reads Firestore/Redis, sends push notifications.

Keep this map up to date. When adding, removing, or changing inter-service calls, update this section and the matching section in `CLAUDE.md`.

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