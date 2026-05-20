# Omi Local ASR Helper

This is the control-plane scaffold for local Whisper transcription. The desktop
app sends one JSON request on stdin and reads one JSON response on stdout. The
current implementation is fixture-backed so CI can exercise the same contract
before MLX Whisper and faster-whisper adapters are installed.

Smoke command:

```bash
printf '{"request_id":"fixture-1","audio_path":"/tmp/sample.pcm","language":"en","sample_rate":16000,"channels":1,"engine":"mlx-whisper","model":"small","fixture_segments":[{"id":"s1","speaker":0,"text":"hello local whisper","start":0.0,"end":1.2}]}' | cargo run --quiet --manifest-path desktop/local-asr-helper/Cargo.toml
```

