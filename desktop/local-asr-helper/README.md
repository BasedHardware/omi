# Omi Local ASR Helper

The desktop app sends one JSON transcription request on stdin and reads one JSON
response on stdout. `fixture_segments` are still accepted for contract tests, but
normal requests now require a real MLX Whisper or faster-whisper runtime.

Capability probe:

```bash
cargo run --quiet --manifest-path desktop/local-asr-helper/Cargo.toml -- --capabilities
```

Runtime setup:

- The desktop add-on manager sets `OMI_LOCAL_ASR_PYTHON` to the managed runtime
  after installing a production-shaped runtime/model artifact manifest.
- MLX Whisper requires native Apple Silicon, `mlx-whisper`, and either a cached
  Hugging Face model or a local model directory set with
  `OMI_MLX_WHISPER_MODEL_DIR` or `OMI_MLX_WHISPER_MODEL_DIR_SMALL`.
- faster-whisper requires `faster-whisper` and either a cached Hugging Face model
  or a local model directory set with `OMI_FASTER_WHISPER_MODEL_DIR` or
  `OMI_FASTER_WHISPER_MODEL_DIR_SMALL`.
- `OMI_LOCAL_ASR_ALLOW_MODEL_DOWNLOAD` is disabled for managed installs; model
  directories come from the verified add-on manifest.
- For local development, point `OMI_LOCAL_ASR_MANIFEST_URL` at fixture or staging
  artifacts to exercise the same install path as production.
- The repo-local fixture path is `make local-asr-fixture`, which writes a
  manifest to `/tmp/omi-local-asr-fixture/manifest.json`. `make serve-local`
  auto-injects that manifest when it exists while keeping the local-mode Rust
  backend sentinel invalid.

Distribution recommendation:

- Do not rely on the user's shell Python for production installs. A macOS app
  launched from Finder will not inherit pyenv/Homebrew environment, and system
  Python cannot be assumed to contain MLX packages.
- Keep the base app install small and make local Whisper an optional add-on:
  install a managed ASR runtime under
  `~/Library/Application Support/Omi/LocalASR`, then point
  `local-asr-helper` at that managed Python and a managed model cache. The
  Settings screen offers Install/Repair/Remove actions and re-runs
  `--capabilities` after each action.
- The production add-on installer never invokes pip, Homebrew, pyenv, or system
  Python. It downloads Omi-hosted runtime and model zip artifacts from the
  desktop backend manifest, verifies SHA-256 checksums, validates
  `--capabilities`, and then atomically promotes the install.
- Prefer MLX Whisper on native Apple Silicon and keep faster-whisper as a
  non-MLX fallback only where it is intentionally supported.

Real PCM smoke command:

```bash
say -o /tmp/omi-asr-smoke.aiff "hello local whisper"
afconvert /tmp/omi-asr-smoke.aiff -f WAVE -d LEI16@16000 -c 1 /tmp/omi-asr-smoke.wav
python3 - <<'PY'
import wave
with wave.open("/tmp/omi-asr-smoke.wav", "rb") as wav:
    data = wav.readframes(wav.getnframes())
with open("/tmp/omi-asr-smoke.pcm", "wb") as f:
    f.write(data)
PY

printf '{"request_id":"smoke-1","audio_path":"/tmp/omi-asr-smoke.pcm","language":"en","sample_rate":16000,"channels":1,"engine":"mlx-whisper","model":"small"}' \
  | cargo run --quiet --manifest-path desktop/local-asr-helper/Cargo.toml
```

Background pipeline harness:

```bash
# Deterministic fixture mode. Requires no local model or cloud credentials.
desktop/local-asr-helper/local_background_asr_harness.py \
  --generate-speech "hello local background transcription" \
  --reference "hello local background transcription" \
  --mode fixture \
  --max-chunk-seconds 2 \
  --output /tmp/omi-local-background-asr-report.json

# Real local Whisper mode. Build the helper first or point at an existing helper.
cargo build --manifest-path desktop/local-asr-helper/Cargo.toml
OMI_LOCAL_ASR_HELPER_PATH="$PWD/desktop/local-asr-helper/target/debug/local-asr-helper" \
  desktop/local-asr-helper/local_background_asr_harness.py \
  --generate-speech "hello local background transcription" \
  --reference "hello local background transcription" \
  --mode local \
  --engine mlx-whisper \
  --model base \
  --output /tmp/omi-local-background-asr-local-report.json
```

The harness is intentionally focused on the desktop background transcription
path, not one-off helper invocation. It converts or generates 16 kHz mono PCM,
runs the Swift `LocalBackgroundTranscriptionSession`, and writes JSON with:

- chunk boundaries and overlap start times;
- helper engine/model;
- raw per-chunk Whisper/helper segments;
- timestamp-remapped session-relative segments;
- deterministic joined transcript;
- latency and real-time-factor data;
- optional WER/CER scores when `--reference` is provided.

Use `--audio path/to/file.wav` or `--audio path/to/file.pcm` instead of
`--generate-speech` to inspect a checked-in or manually recorded sample. The
`--deepgram-compare` flag is reserved as the explicit future extension point and
requires `DEEPGRAM_API_KEY`; it is not required for local smoke validation.

In the dev app, open Settings -> Advanced -> Dev Tools -> Raw Transcription
History to inspect the recent locally persisted sessions and raw segment text.
Use the Refresh button after stopping a local background recording.

The dev desktop app build (`desktop/run.sh`) builds this helper and copies it to
`<app>.app/Contents/Resources/local-asr-helper`, which is the bundled path used
by `LocalASRHelperLocator`.
