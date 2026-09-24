# REST MCP sync and export contract

Companion to `mcp-analytics.md`. This documents the REST `/v1/mcp/*` list
endpoints' pagination and incremental-sync surface as of the Phase 2
consolidation: the list bodies keep their released top-level JSON array
shape, and pagination state travels in a response header.

## `X-Next-Cursor`

Paginated list endpoints may emit an `X-Next-Cursor` response header. When
present, pass its opaque value back as the `cursor` query parameter —
together with the **same** filter arguments — to fetch the next page. The
header is absent when no further page exists.

Endpoints carrying cursors:

| Endpoint | Cursor mode |
|---|---|
| `GET /v1/mcp/conversations` | `(created_at DESC, id DESC)` keyset |
| `GET /v1/mcp/memories` | `MemoryService.read_page` continuation or bounded offset |
| `GET /v1/mcp/action-items` | offset (list) or `(updated_at ASC, id ASC)` keyset (sync) |
| `GET /v1/mcp/chat` | offset |
| `GET /v1/mcp/screen-activity` | `(timestamp ASC, id ASC)` keyset (raw mode only) |
| `GET /v1/mcp/daily-summaries` | offset |

Cursor tokens are opaque, bound to the calling surface, the user's uid, and
the validated filter set. Replaying a cursor with different filters, a
different user, or a mangled token returns HTTP 400. `cursor` and a
non-zero `offset` are mutually exclusive.

`X-Next-Cursor` is exposed via CORS `expose_headers` in `main.py`.

## Incremental sync (`updated_since`)

`updated_since` is a strict ISO-8601 timestamp that **must** carry an
explicit timezone offset (`Z` or `±hh:mm`); naive or malformed values
return HTTP 400.

### Supported: `GET /v1/mcp/action-items`

With `updated_since`, the endpoint switches to an incremental feed ordered
`(updated_at ASC, id ASC)`:

- Every item carries its persisted `updated_at` watermark.
- `completed`, `due_start_date`, `due_end_date`, and non-zero `offset` are
  rejected with HTTP 400 (they cannot be combined truthfully).
- Requires the `action_items (updated_at ASC, __name__ ASC)` composite
  index; the DESC twin is registered for newest-first revision scans.
- Items whose documents lack `updated_at` are outside the feed (the field
  is the ordering key); they predate the sync surface.

### Gated: `GET /v1/mcp/conversations`, `GET /v1/mcp/memories`

Passing `updated_since` to these endpoints returns HTTP **503** with
`Retry-After` and a detail string containing
`incremental_sync_unavailable`:

- **Conversations**: `updated_at` is synthesized from the Firestore
  snapshot `update_time` at read time; generic writes do not persist a
  queryable `updated_at` field, so no revision-ordered index can be built.
- **Memories**: the read view mixes canonical and historical records, and
  legacy documents lack `updated_at`, so a revision feed would silently
  drop updates.

These are explicit deferred follow-ups — not implemented claims. Rollout
prerequisite for each: backfill a persisted `updated_at` on every live
document, add the query-ready `(updated_at, __name__)` index, then flip the
gate to the same feed shape used by action-items.

## Deletion semantics

- **Action items**: deletes are hard deletes by default — a hard-deleted
  item leaves no row and is **not** emitted by the sync feed. Rows that
  persist with `deleted: true` (soft tombstones written by retirement
  flows) are emitted with `deleted: true` so clients can reconcile them.
- **Conversations / memories**: both models persist soft-delete tombstone
  rows (discarded/deleted markers), so deletes **are** recorded — but
  their `updated_since` feeds are gated (503) pending the `updated_at`
  backfill, and the plain list cursors already skip tombstones. Clients
  must re-fetch or reconcile on their own cadence until the gated feeds
  ship; no deletes are silently claimed covered today.

## Conversation detail bounds

`GET /v1/mcp/conversations/{id}` returns the full transcript through the
shared bounded reader: at most 4096 segments and 500,000 transcript
characters. When output is clipped, the additive `truncated` field is
`true`; `speaker_name` is populated on each segment, and `apps_results` is
preserved. List/search responses stay lean: no transcript, no photos, and
`apps_results` projected from the card field paths.
