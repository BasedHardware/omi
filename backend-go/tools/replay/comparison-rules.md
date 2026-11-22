# Approved ordinary-sync comparison rules

Source report: slice B bundle `8c9770e02e46d23288488f7c108505ffc593df16`, four
ordinary-sync cases, 438 unexplained differences. David approved the timestamp,
goal-event and Home-token rules below on 2026-11-22. Each is executable and has a
negative test. Values remain in the comparison; the oracle validates their types,
replay windows, identities and same-side links before explaining a difference.
Null and absent remain distinct, and missing Python writes remain unexplained until
Go matches them.

## Timestamps

For every listed field, parse the value from each side and require it to fall within
that side's observed `[started_at, finished_at]` replay window. A missing or malformed
value, an invalid run window, or a value outside its own window is a failure. Counts
are occurrences in the four-case report.

| Field | Occurrences | Additional check |
| --- | ---: | --- |
| `users/{uid}/episodes/{episode_id}/compose_deferred_at` | 4 | — |
| `users/{uid}/episodes/{episode_id}/created_at` | 4 | — |
| `users/{uid}/episodes/{episode_id}/title_changed_at` | 2 | — |
| `users/{uid}/goals/{goal_id}/updated_at` | 1 | — |
| `users/{uid}/goals/{goal_id}/goal_history/{day}/recorded_at` | 1 | The history day and `date` must match the contract's fixture timezone day for that timestamp. |
| `users/{uid}/llm_usage/{day}/last_updated` | 2 | The daily bucket key must match the contract's fixture timezone day for that timestamp. |
| `users/{uid}/memory_state/apply_control/updated_at` | 2 | Parse the stored RFC3339 string (not a Firestore timestamp wrapper). |
| `users/{uid}/episode_links/{conversation_id}/updated_at` | 1 | — |

Python-only conversation timestamps, including `/conversation/title_changed_at`, are
not covered by these rules. They remain differences until Go writes the matching
fields.

## Generated identifiers and version tokens

Each check is side-local: it validates the token against the write, document, or
projection it identifies. Cross-side random values need not be byte-equal only after
the corresponding rule is approved and implemented.

| Field | Occurrences | Proposed check |
| --- | ---: | --- |
| `users/{uid}/goals/{goal_id}/events/{event_id}` document ID and its `event_id` field | 2 | On each side, the path ID equals `event_id`; `goal_id` binds to an existing parent goal; `sequence` equals that goal's `latest_progress_sequence`; and event semantics compare after excluding only the bound ID and independently checked `created_at`. |
| `/conversation/home_source_version` | 4 | Require a fresh UUIDv4 hex token, absent from seeded UUID values and unique among Home tokens in that side's run. Its same-side `episode_links/{conversation_id}` receipt must be dirty; if `home_prepared_source_version` exists, it must match. |
| `/conversation/home_display_version` | 4 | Require a fresh UUIDv4 hex token, absent from seeded values and unique in that side's run. The same-side conversation must contain a non-empty `home_display` payload. |
| `users/{uid}/episodes/{episode_id}/home_content_epoch` | 4 | Require a fresh UUIDv4 hex token, absent from seeded values and unique in that side's run, with `home_needs_prepare=true`; if `home_prepare_state.epoch` exists, it must equal the token. |
| `users/{uid}/episodes/{episode_id}/home_display_version` | 4 | Require a fresh UUIDv4 hex token, absent from seeded values and unique in that side's run. The same-side episode must be deferred for preparation and contain a non-empty `home_display` payload. |
| `users/{uid}/episode_links/home_feed_control/generation` | 4 | Require a fresh UUIDv4 hex token, absent from seeded values and unique in that side's run; the same-side control document must have `ready=false`. |

Home card responses are not part of these finalization observations, so the Home
display rules verify the persisted payload and deferred control links only. Go-only
notes hashes, ownership/revision metadata, absent conversation fields, and all other
differences remain unexplained unless separately resolved.

## `finalization_job_id` remains unexplained

No rule currently excuses `conversation.finalization_job_id`. The app has no direct
Firestore read permission for user documents. FastAPI conversation responses use
typed models that ignore unmodeled stored fields; MCP cards and REST responses select
their output fields explicitly. The Python public reader and index audit found no
query, filter, ordering or Firestore index on this field. Internal lifecycle code
does read it for state gates and fencing, including `conversation_processing_recovery`,
`no_speech_terminal`, `batch_summary_debt`, `live_member_notes`, `smart_merge`,
`conversation_quiet_checks`, and `processing_attention`. The replay-only binding rule
stays disabled until its Go queue-row evidence and Python no-binding assertion are
implemented and reviewed.
