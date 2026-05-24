# STT Provider Comparison Gate

Run the offline production-readiness eval from the backend directory:

```bash
python3 scripts/stt/provider_comparison_gate.py \
  --manifest tests/fixtures/stt_provider_eval/manifest.json \
  --output-md /tmp/stt-provider-eval.md \
  --output-json /tmp/stt-provider-eval.json
```

The default command replays synthetic and saved provider outputs only. It does not require `ASSEMBLYAI_API_KEY` or `DEEPGRAM_API_KEY`.

The report compares `always_deepgram`, `always_assemblyai`, `current_policy`, and `shadow_only`. It includes speaker safety, default viability, and canary readiness gates plus an AssemblyAI gap report that names the limiting scenario, likely cause, and rollout mitigation.

The fixture manifest covers clean turns, fast turns, overlap, sparse speech, low-signal/no-speech, multilingual turns, duplicate chunk replay, provider failure/fallback, saved real-provider E2E output, and saved policy-router output.

Live-provider smoke tests are optional:

```bash
ASSEMBLYAI_API_KEY=... DEEPGRAM_API_KEY=... \
python3 scripts/stt/provider_comparison_gate.py \
  --manifest tests/fixtures/stt_provider_eval/manifest.json \
  --live
```

Synthetic and saved-output gates are necessary but insufficient for broad defaulting. TICKET-028 must turn the latest gap-closing report into an AssemblyAI canary/default rollout plan backed by privacy-safe real-session metrics.
