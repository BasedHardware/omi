# Omi Local ASR Helper

The desktop app sends one JSON transcription request on stdin and reads one JSON
response on stdout. `fixture_segments` are still accepted for contract tests, but
normal requests now require a real MLX Whisper or faster-whisper runtime.

Capability probe:

```bash
cargo run --quiet --manifest-path desktop/local-asr-helper/Cargo.toml -- --capabilities
```

Runtime setup:

- Set `OMI_LOCAL_ASR_PYTHON` to the Python executable that has the ASR runtime.
  It defaults to `python3`.
- MLX Whisper requires native Apple Silicon, `mlx-whisper`, and either a cached
  Hugging Face model or a local model directory set with
  `OMI_MLX_WHISPER_MODEL_DIR` or `OMI_MLX_WHISPER_MODEL_DIR_SMALL`.
- faster-whisper requires `faster-whisper` and either a cached Hugging Face model
  or a local model directory set with `OMI_FASTER_WHISPER_MODEL_DIR` or
  `OMI_FASTER_WHISPER_MODEL_DIR_SMALL`.
- For development only, `OMI_LOCAL_ASR_ALLOW_MODEL_DOWNLOAD=1` lets the Python
  runtime resolve the default Hugging Face model names.

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

The dev desktop app build (`desktop/run.sh`) builds this helper and copies it to
`<app>.app/Contents/Resources/local-asr-helper`, which is the bundled path used
by `LocalASRHelperLocator`.
