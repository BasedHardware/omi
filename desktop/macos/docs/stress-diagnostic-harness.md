# Stress Diagnostic Harness

`scripts/stress_ptt_chat.py` is the first deterministic contract for desktop
PTT, realtime, chat bridge, and subagent stress runs. It validates JSONL events
offline and can optionally probe an already-running non-production automation
bridge. It never launches, restarts, kills, or discovers `/Applications/Omi.app`.

## JSONL Contract

Each line is one terminal event:

```json
{"run_id":"run-1","iteration":1,"scenario":"ptt_voiced","terminal_reason":"ptt_voiced_success","timestamp":"2026-07-07T12:00:00.000Z","duration_ms":120,"details":{}}
```

Scenarios:
- `ptt_voiced`
- `ptt_silent`
- `chat_bridge`
- `subagent_launch`

Terminal reasons:
- `ptt_voiced_success`
- `ptt_silent_rejected`
- `chat_bridge_success`
- `subagent_launch_success`
- `too_short_tap`
- `audio_frames_missing`
- `silent_audio`
- `realtime_token_mint_failure`
- `provider_fallback`
- `bridge_launch_failure`
- `response_already_running`

The release gate passes only when at least one event exists and none of these
forbidden reasons appear: `too_short_tap`, `audio_frames_missing`,
`silent_audio`, `realtime_token_mint_failure`, `bridge_launch_failure`,
`response_already_running`. `provider_fallback` is tracked but allowed so the
gate can distinguish a degraded but recovered provider path from a silent turn.
The scenario-specific success reasons are allowed and make partial exports easy
to spot in summaries.

## Offline Validation

```bash
cd desktop/macos
python3 scripts/stress_ptt_chat.py --input-jsonl /path/to/stress-run.jsonl
```

The script prints a JSON summary and exits `0` when the release gate passes, or
`2` when the JSONL is invalid or forbidden terminal reasons are present.
For release-candidate gates, require the expected coverage explicitly:

```bash
python3 scripts/stress_ptt_chat.py \
  --input-jsonl /path/to/stress-run.jsonl \
  --require-scenario ptt_voiced \
  --require-scenario ptt_silent \
  --require-scenario chat_bridge \
  --require-scenario subagent_launch
```

## Live Bridge Probe

First launch a named non-production bundle yourself:

```bash
cd desktop/macos
OMI_APP_NAME="omi-stress-diagnostics" ./run.sh
```

Then probe the already-running bridge:

```bash
cd desktop/macos
export OMI_AUTOMATION_TOKEN="$(tr -d '\r\n' < "${TMPDIR:-/tmp}/omi-automation-47777.token")"
python3 scripts/stress_ptt_chat.py \
  --base-url http://127.0.0.1:47777 \
  --iterations 5 \
  --scenario ptt_voiced \
  --scenario chat_bridge \
  --emit-jsonl
```

Live mode expects future automation actions named `stress_ptt_voiced`,
`stress_ptt_silent`, `stress_chat_bridge`, and `stress_subagent_launch`. Until
those are registered by the app, live probes fail loud with
`bridge_launch_failure`; offline JSONL validation is the stable release-gate
surface for this first slice.
The script only sends automation tokens to loopback bridge URLs by default. Use
`--allow-remote-token` only for an intentional non-production remote bridge.

## Release-Gate Path

The intended gate is:

1. A signed named bundle or dev bundle exports stress JSONL from PTT/realtime and
   chat/subagent bridge runs.
2. CI or the release operator runs `stress_ptt_chat.py --input-jsonl` with the
   required scenarios listed above.
3. Promotion stops on forbidden terminal reasons, while preserving the exact
   per-iteration taxonomy for diagnosis.
