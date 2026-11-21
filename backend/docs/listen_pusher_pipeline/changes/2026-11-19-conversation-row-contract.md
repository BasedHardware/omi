# Conversation rows are validated at the write seam and isolated on list reads

On 2026-11-17 the v3 planner stored rows whose `structured.participants[]` lacked the required `source`. The rows
were committed as raw dicts, so the first validators were the readers: every `GET /v1/conversations` page for an
affected account returned 500 until #25588 repaired the read.

What changes (`utils/conversations/row_contract.py`, SCA-2966):
- **Write seam.** `conversations_v3.commit_projection` validates every planned row against `Conversation`, the model
  the readers use, before anything is encoded or committed. An invalid row raises `Conflict('invalid_row')`, which
  is in `service.BLOCKED`: the task is answered `blocked`, the owner is parked on the builder lease (5 min doubling
  to 1 h), nothing is written and `v3_pending` stays owed, so a code fix rebuilds the window. Backfill passes
  return `blocked` without parking the live builder. `omi_conversation_row_write_invalid_total{producer,outcome}`
  names the producer (`v3_planner`, `v3_backfill`); the log carries the row id and failing field paths only.
- **Kill switch.** `CONVERSATION_ROW_WRITE_VALIDATION_ENABLED` (default on, `ops_kill`). False counts and logs the
  invalid row (`outcome=logged`) and writes it as before. Use it only if a systematic producer bug parks many owners
  (`omi_conversations_v3_blocked_total{reason="invalid_row"}`).
- **Read isolation.** `GET /v1/conversations`, `POST /v1/conversations/search`, `POST /v1/conversations/with-tasks/page`,
  `GET /v1/folders/{id}/conversations` and `GET /v1/dev/user/conversations` drop a row their response model rejects,
  count it as `omi_fallback_total{component="conversation_row_contract",reason="malformed_doc"}`, log its id and
  field paths, and return the rest of the page. Folder and Developer API lists already skipped such rows with their
  own loops; they now use the shared primitive. Pagination metadata still counts the fetched page.

No stored data, prompt, schema or version changes. Rollback: revert, or set the kill switch false for the write
seam only.

Regression coverage: `backend/tests/unit/test_conversation_row_contract.py`,
`backend/tests/unit/test_conversation_producer_round_trips.py` (shared helper
`backend/tests/unit/fixtures/conversation_round_trip.py`), and
`backend/tests/unit/test_structured_model_definitions_parity.py` (SDK copy vs the fallback the image loads).
