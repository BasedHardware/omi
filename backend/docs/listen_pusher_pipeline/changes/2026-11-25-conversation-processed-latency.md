# Per-conversation processed latency and a settle time on every completed row

"What share of conversations had a usable summary within N seconds of ending (or
syncing)" now reads from Prometheus instead of a Firestore scan.

- `omi_conversation_processed_seconds{lane, basis}` is observed once per
  conversation, after the commit that makes its first usable summary durable.
  `basis="finished"` measures from `finished_at` (last speech);
  `basis="end_or_sync"` measures from the later of `finished_at` and `arrival_at`
  (server receipt), and falls back to `finished_at` when a row has no arrival time.
  The legacy lane observes from the summary receipt (first rich structured write).
  The v3 lane observes when `v3_notes_written` first becomes true (open-time notes
  and background settles). v3 rows publish a preview overview first, so the receipt
  path skips them. A backfill re-derive resets `v3_notes_written` and can observe again
  in `lane="backfill"`.
- `omi_conversation_settled_unsummarized_total{lane, reason}` counts settles without a
  summary: `discarded` and `local_only` receipts, v3 `no_notes` settles and v3
  `failed` processing. Share within N seconds is
  `bucket{le=N} / (count + unsummarized)`. A row that fails or is discarded and is
  later summarized appears in both. Server failure terminals (dead letter, orphan,
  oversized, no-speech) are not counted yet.
- `omi_closed_to_summary_seconds` keeps its name and labels. When a row has no
  acceptance metadata (`accept_unknown`), `arrival_at` now stands in for server
  acceptance, so those summaries are timed too.

`terminal_family_at` is now written by every writer that moves a conversation onto
`completed` and finds it unset: server-batch capture close, the discarded zero-preview
fanout, orphan batch capture, dead-letter/BYOK/orphan/oversized/deferred terminals,
merge rollback, no-speech and stuck-backfill closes (their undo removes it), v3 open
notes, v3 failure, the v3 projection commit, and completed creations through upsert
or create-if-absent. The shared helper is `utils/conversations/terminal_settled.py`.
It writes only the timestamp, never `terminal_family`, and follows the
`CONVERSATION_TERMINAL_FAMILY_MODE` kill switch. For capture-close writers the field
means "settled", not "summary ready". The terminal-family claim still overwrites it on
a later processing write, as before. A stamp that would grow a row at the 1 MiB ceiling
is dropped with the deterministic title.

Not stamped: tombstoned (deleted) rows and the parked-status operator repair
(`database/conversation_parked_status.py`, a field-masked one-off script).
[Pipeline contract](../../listen_pusher_pipeline.mdx)
