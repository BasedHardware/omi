# Agent prompt: AssemblyAI background batch E2E (no desktop app)

## Context

Branch work adds **desktop always-on Audio Recording via AssemblyAI batch chunks** instead of `/v4/listen` (Deepgram streaming). Implementation is committed on the current branch.

**Goal for you:** Build and run the strongest **non-desktop-app** E2E proof that the pipeline works end-to-end. Do **not** launch Omi Dev or use agent-swift unless absolutely necessary.

## What exists today

### Backend (working — verified manually)

- `POST /v2/desktop/background-conversation/start` → `{ conversation_id }`
- `POST /v2/desktop/background-transcribe` → `{ segments, provider, run_id }` using `STTWorkload.background` → AssemblyAI
- Helpers: [`backend/utils/conversations/desktop_background.py`](backend/utils/conversations/desktop_background.py)
- Router: [`backend/routers/desktop_background.py`](backend/routers/desktop_background.py)
- Unit tests: [`backend/tests/unit/test_desktop_background_transcribe.py`](backend/tests/unit/test_desktop_background_transcribe.py)

### Script (partial E2E — single-chunk only)

[`scripts/desktop_assemblyai_e2e.py`](scripts/desktop_assemblyai_e2e.py):

```bash
# Requires: local backend on :8080, ASSEMBLYAI_PRERECORDED_STT_ENABLED=true, Omi Dev signed in
python3 scripts/desktop_assemblyai_e2e.py --background-chunk --api http://127.0.0.1:8080
```

Currently uploads **one full sample MP3 as a single PCM blob** (~154s). Proves backend + AssemblyAI once; does **not** simulate desktop chunking cadence or multi-chunk timeline.

### Desktop (implemented but not in scope for your E2E)

- Chunker/session in [`desktop/Desktop/Sources/BackgroundTranscription/`](desktop/Desktop/Sources/BackgroundTranscription/)
- AppState wiring in [`desktop/Desktop/Sources/AppState.swift`](desktop/Desktop/Sources/AppState.swift)
- Swift unit tests: [`desktop/Desktop/Tests/BackgroundTranscriptionTests.swift`](desktop/Desktop/Tests/BackgroundTranscriptionTests.swift) — chunker/merger/reducer only; **does not** exercise `AudioMixer` → AppState path

### Known gap (why desktop failed in manual test)

Live desktop recording started batch mode (`background-conversation/start`) but **never POSTed chunks** for 90+ seconds. Suspected cause: `AudioMixer` callback invokes `handleMixedBackgroundAudio` off MainActor. Your E2E should **not depend on fixing this** — but optionally add a Swift integration test that would catch it (see below).

---

## Your mission

Extend automated testing to get **as close as possible** to proving the full batch background path works **without running the desktop app**.

### Tier 1 — Must deliver (Python, runnable in CI-like env)

Extend [`scripts/desktop_assemblyai_e2e.py`](scripts/desktop_assemblyai_e2e.py) (or add `scripts/desktop_assemblyai_e2e_batch.py`) with a **`--background-batch`** mode that:

1. **Prerequisites check** (exit with clear message if missing):
   - Backend reachable at `--api` (default `http://127.0.0.1:8080`)
   - Firebase token from `defaults read com.omi.desktop-dev auth_idToken` OR `--token` flag for CI
   - Optional: grep backend `/docs` or a health endpoint; document required env vars

2. **Simulate desktop chunking in Python** (mirror [`BackgroundTranscriptionConfiguration`](desktop/Desktop/Sources/BackgroundTranscription/BackgroundTranscriptionConfiguration.swift)):
   - 16 kHz mono int16 PCM
   - Split sample audio into **15s max chunks** with **1s overlap** (same as desktop chunker defaults)
   - Use silence-boundary cuts if easy; hard-cut at 15s is acceptable for v1

3. **Full conversation lifecycle:**
   ```
   POST /v2/desktop/background-conversation/start
   for each chunk i:
     POST /v2/desktop/background-transcribe
       ?conversation_id=...
       &chunk_start_ms=<cumulative offset>
       &language=es   # or en
   POST /v1/conversations   # force-process finalize
   GET /v1/conversations?...  # verify segments exist on conversation
   ```

4. **Assertions (fail loudly):**
   - Every chunk returns HTTP 200
   - Every chunk has `provider == "assemblyai"`
   - `segments` non-empty for at least one chunk (speech sample)
   - `chunk_start_ms` offsets applied: segment `start` values increase across chunks, no regression
   - Multi-chunk: at least **2 chunks** uploaded from sample audio
   - Finalize returns 200 or expected 404 if already processed
   - Optional: fetch conversation from Firestore/API and assert `transcript_segments` length > 0

5. **CLI UX:**
   ```bash
   python3 scripts/desktop_assemblyai_e2e.py --background-batch [--api URL] [--language es] [--token TOKEN]
   ```
   Print summary: chunk count, total segments, conversation_id, sample transcript snippet.

6. **Document** in script header how to run locally:
   ```bash
   cd backend && DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib" ./run-local.sh
   # .env: ASSEMBLYAI_PRERECORDED_STT_ENABLED=true, ASSEMBLYAI_API_KEY=...
   python3 scripts/desktop_assemblyai_e2e.py --background-batch
   ```

### Tier 2 — Backend pytest integration (no live AssemblyAI if possible)

Add [`backend/tests/integration/test_desktop_background_batch_e2e.py`](backend/tests/integration/test_desktop_background_batch_e2e.py) OR extend unit tests:

- Mock `transcribe_bytes` for most tests (fast, no API key)
- One optional `@pytest.mark.integration` test that calls real AssemblyAI when `ASSEMBLYAI_API_KEY` set (skip otherwise)
- Test multi-chunk append: 3 chunks with offsets → Firestore segments merged correctly
- Test `provider_cluster_id` → distinct `speaker_id` when mock returns two clusters

Run: `cd backend && python3 -m pytest tests/unit/test_desktop_background_transcribe.py -v`

### Tier 3 — Swift integration test (no desktop app launch)

Add test in [`desktop/Desktop/Tests/BackgroundTranscriptionTests.swift`](desktop/Desktop/Tests/BackgroundTranscriptionTests.swift) or new file:

- **`testMixerCallbackDispatchesChunksToSession`**: Feed 16+ seconds of synthetic PCM through `BackgroundAudioChunker` the same way AppState would after receiving mixer output; mock HTTP handler returns fake segments; assert `transcribeNext` called and segments merged.
- **`testFifteenSecondContinuousSpeechProducesChunk`**: Append PCM at 100ms frames for 16s → assert at least one chunk enqueued without silence gaps.

Run: `cd desktop && xcrun swift test -c debug --package-path Desktop --filter BackgroundTranscription`

This catches the class of bug where audio never reaches the session (won't fix MainActor alone but validates chunker + session + drain loop).

### Tier 4 — Optional: chunker parity test (Python ↔ Swift)

Export chunk boundaries from Python chunker and assert Swift `BackgroundAudioChunker` produces same cut points for a fixture PCM file. Low priority unless easy.

---

## Out of scope

- Launching Omi Dev / agent-swift / live mic
- PTT path (`/v2/voice-message/transcribe`)
- `/v4/listen` WebSocket
- Prod Helm rollout

---

## Success criteria

You are done when:

1. `python3 scripts/desktop_assemblyai_e2e.py --background-batch` passes against local backend with AssemblyAI enabled, printing conversation_id + segment count.
2. `cd backend && python3 -m pytest tests/unit/test_desktop_background_transcribe.py -v` passes (0 failures).
3. Swift `BackgroundTranscription` tests pass including at least one **multi-chunk / 15s boundary** test.
4. README or script docstring explains how to run without desktop app.

---

## Reference files

| File | Purpose |
|------|---------|
| [`backend/routers/desktop_background.py`](backend/routers/desktop_background.py) | HTTP endpoints |
| [`scripts/desktop_assemblyai_e2e.py`](scripts/desktop_assemblyai_e2e.py) | Extend this |
| [`desktop/Desktop/Sources/BackgroundTranscription/BackgroundAudioChunker.swift`](desktop/Desktop/Sources/BackgroundTranscription/BackgroundAudioChunker.swift) | Match chunk sizes |
| [`.cursor/plans/assemblyai_background_listen_098fc011.plan.md`](.cursor/plans/assemblyai_background_listen_098fc011.plan.md) | Full architecture plan |

## Environment

```bash
# backend/.env (required)
ASSEMBLYAI_PRERECORDED_STT_ENABLED=true
ASSEMBLYAI_PRERECORDED_STT_WORKLOADS=sync,background,postprocess
ASSEMBLYAI_API_KEY=<key>
LOCAL_DEVELOPMENT=true
```

Auth: `LOCAL_DEVELOPMENT=true` maps failed token verify → uid `123`.

---

## Notes from manual debugging

- Single-chunk `--background-chunk` **passed** (AssemblyAI returned transcript for NBC sample).
- Desktop live path: conversation created but **no chunk POSTs** — fix is likely `Task { @MainActor in handleMixedBackgroundAudio(...) }` in mixer callback; **separate task**, not required for your Python E2E.
