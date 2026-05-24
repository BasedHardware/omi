# STT Provider Comparison Gate

Run the offline production-readiness eval from the backend directory:

```bash
python3 scripts/stt/provider_comparison_gate.py \
  --manifest tests/fixtures/stt_provider_eval/manifest.json \
  --output-md /tmp/stt-provider-eval.md \
  --output-json /tmp/stt-provider-eval.json
```

The default command replays synthetic and saved provider outputs only. It does not require `ASSEMBLYAI_API_KEY` or `DEEPGRAM_API_KEY`.

The report compares `always_deepgram`, `always_assemblyai`, `current_policy`, and `shadow_only`. `current_policy` means AssemblyAI default for passive background workloads. `shadow_only` is retained only as a rollback/diagnostic comparator. The report includes speaker safety, default viability, and rollout readiness gates plus an AssemblyAI gap report that names the limiting scenario, likely cause, and mitigation.

The fixture manifest covers clean turns, fast turns, overlap, sparse speech, low-signal/no-speech, multilingual turns, duplicate chunk replay, provider failure/fallback, saved real-provider E2E output, and saved policy-router output.

Cost estimates use public pay-as-you-go diarized prerecorded rates checked on 2026-05-25: AssemblyAI Universal-2 plus diarization is `$0.170/hour`, Deepgram Nova-3 monolingual plus diarization is `$0.408/hour`, and Deepgram Nova-3 multilingual plus diarization is `$0.468/hour`. Older experiment notes omitted Deepgram diarization cost and should not be used for rollout cost decisions.

Live-provider smoke tests are optional:

```bash
ASSEMBLYAI_API_KEY=... DEEPGRAM_API_KEY=... \
python3 scripts/stt/provider_comparison_gate.py \
  --manifest tests/fixtures/stt_provider_eval/manifest.json \
  --live
```

Synthetic and saved-output gates are necessary but insufficient for default health decisions. Use the latest gap-closing report to operate the AssemblyAI default with Deepgram fallback and privacy-safe real-session metrics.
