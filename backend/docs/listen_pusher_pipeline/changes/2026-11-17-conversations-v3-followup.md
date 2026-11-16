# Conversations v3 follow-up: custom-STT allowance on open, location, playback check

Follow-up to the [v3 contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3) and
`2026-11-16-conversations-v3.md`. No runtime flag changed; the v3 stage still defaults to beta.

- **On-open summaries respect the custom-STT allowance.** `GET /v1/conversations/{id}/summary/stream` now applies
  the same `should_skip_omi_paid_postprocessing` check as background processing before any Omi-paid notes. When
  the allowance refuses, `prepare()` takes no writer lease and `stream()` ends with the stored row's `done` frame,
  so no notes call runs. Before this, a refused open still ran the notes model and then failed to persist it
  for lack of a lease.
- **Derived conversations keep their location.** `planner.build()` copies `geolocation` from the existing row,
  or else from the first contributing recording.
- **Playback check without the shared helper.** The playback, sync and plugin-backup-audio paths check
  `recording_pieces is not None` locally, because backend unit shard 5 stubs `utils.conversations` and could
  not import the shared helper from `utils/conversations/layer.py`.

Evidence: `tests/unit/test_conversations_v3_stream.py` (refused stream serves the stored row with no lease and
no notes call; allowance parametrized on `prepare()`) and `tests/unit/test_conversations_v3_engine.py`
(location). PR #25529.
