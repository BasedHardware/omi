# Record-path session traces

Content-free replay fixtures for the pusher record path: seal (`record_audio_closed`), sticky upload
failure, producer tokens (`record_upload_sessions`) and the batch admission barrier
(`config/record_audio.require_record_audio_barrier`). Batch shadow re-runs recognition on stored audio and
never exercises this path; the 10-29/30 live batch stops and the unsealed no-transcript backlog were here.

Runner: `tests/unit/test_record_traces.py` drives each trace through the real `routers.pusher` websocket
handler with strict Firestore and recording fakes, once per `durable` mode listed in the trace.

```bash
cd backend && python -m pytest tests/unit/test_record_traces.py -q
```

## Format (`record-trace/1`)

- `name`: equals the file stem. `source`: the incident, RCA or PR the trace pins.
- `row`: seed fields on a completed conversation, limited to `record_lane_owner` and `record_upload_sessions`.
- `durable`: the `AUDIO_DURABLE_OUTBOX_ENABLED` modes to replay. Traces with audio frames replay only with
  `false` for now: the durable outbox commits audio to storage this runner does not fake, so a `true` audio
  replay could pass without exercising custody. Finalize-only traces run in both modes.
- `sessions`: websocket sessions in order. `frames` is a list of `"conversation"` (103), `"finalize"` (104)
  and `{"audio_seconds": N}` (101, N seconds of non-silent PCM). `upload` is `ok` or `fail` (every upload in
  that session raises).
- `expect`: `sealed`, `upload_failed`, `open_tokens` and `admissible` after the last session.
- `known_gap` (optional): the trace pins current behavior that is a known bug; the PR that fixes it flips
  `expect` and drops this field.

No audio, identifiers or user content: durations and protocol shape only. Archive listing and tail
durability are proved at admission against storage and are not modeled here.

Add one trace per record-path incident, in the PR that fixes it.
