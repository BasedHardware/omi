# A refused v3 reprocess answers the retryable contract

**What changed.** `POST /v1/conversations/{id}/reprocess` now answers `503` with the existing
`conversation_processing_retryable` detail and `Retry-After: 2` when the v3 writer returns without storing a
completed summary, instead of a bare `500`. That covers both the typed `ProcessingNotCompleted` raised by
`utils/conversations/v3/processing.py` (`v3_processing_not_completed`) and the persistence fence's
`ProcessingPersistenceFenced` with the same message. The conversation is unchanged in either case: the write was
refused (a newer sync transcript revision, a lost summary lease, another writer, a deletion) or the run ended
without a completed status, so a retry after the source settles can succeed. The existing provider-retry kill
switch, `CONVERSATION_PROCESSING_RETRYABLE_PROVIDER_FAILURE_ENABLED`, restores the generic `500`.

**Why.** SCA-5449. On the served build `543aa7fb2a39` on 2026-11-28, eight reprocess requests answered a bare
`500` after 8-298 s, every one ending at `utils/conversations/v3/processing.py` — a different cause from
SCA-5082/SCA-4388. The reprocess route sets no request deadline of its own (`utils.other.request_deadline` is
only armed by `POST /v1/conversations/from-segments`), so the concurrent `RequestDeadlineExceeded: notes
fallback started after the request budget was spent` lines in those minutes belong to from-segments requests.
For reprocess, the wait is the notes lane: the v3 notes client is one attempt at 90 s (`models.notes_client`,
`max_retries=0`), the agentic writer may run before the one-shot fallback, and the notes loop's own ceiling is
`NOTES_LOOP_DEADLINE_SECONDS` (3 × 60 s). The refusal then came from the write, not from a provider timeout.

**Attribution.** The raise site measures `elapsed_seconds` and records the last notes lane in a contextvar
(`utils.llm.notes_observability`: `short_tasks` for the 30 s v3 short window, `agentic_notes`, `one_shot_notes`).
One line names both:

```
event=v3_processing_not_completed stage=<decline reason|summary_not_persisted|status_not_completed> notes_stage=<lane> elapsed_seconds=<wait>
```

The route adds `event=reprocess_processing_not_completed outcome=retryable_503 stage=... notes_stage=...
elapsed_seconds=...` and counts `omi_conversation_processing_retryable_responses_total{failure_class="other",
route="reprocess"}`. A refused write therefore attributes the budget as well as the cause on the next occurrence.

**Not changed.** The from-segments budget, the explicit-app contract (SCA-4388), the hourly reprocess limit,
prompts, model choice, and every persistence fence.

**Tests.** `tests/unit/test_reprocess_v3_not_completed.py` covers the typed stage from a persistence decline, the
completion-condition stage, the route's 503 + `Retry-After`, the fence exception mapping, and the kill switch
restoring the generic `500`.

**Acceptance.** The next three measured ticks for `POST /v1/conversations/:id/reprocess` carry no `500`
attributed to `v3_processing_not_completed`, and at least one post-serve attempt records the serving sha,
request timestamp, status and latency.
