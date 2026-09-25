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
- Firestore's automatic single-field indexes serve the same-direction
  `(updated_at ASC, __name__ ASC)` keyset (and its DESC twin); declaring
  either as a composite is rejected by the index registry.
- Items whose documents lack `updated_at` are outside the feed (the field
  is the ordering key); they predate the sync surface.

**Watermark overlap**: `updated_at` is a timestamp, not a transaction
sequence — a write can land between a page's read and the client's watermark
capture while sharing (or even preceding) the last emitted value. On each
sync pass, clients should re-read starting from
`watermark - 60 seconds` and deduplicate received items by `id`; the
`(updated_at, id)` keyset cursor guarantees no row inside the window is
skipped, and the overlap covers delayed-commit visibility.

### Unsupported: `GET /v1/mcp/conversations`, `GET /v1/mcp/memories`

Passing a valid `updated_since` to these endpoints returns HTTP **400**
with a detail string containing `incremental_sync_unsupported` — a
permanent capability gap, not a transient outage, so no `Retry-After` is
sent and clients must not retry:

- **Conversations**: `updated_at` is synthesized from the Firestore
  snapshot `update_time` at read time; generic writes do not persist a
  queryable `updated_at` field, so no revision-ordered index can be built.
  Supported alternative: page the endpoint with the `X-Next-Cursor` cursor
  (`created_at DESC, id` keyset).
- **Memories**: the read view mixes canonical and historical records, and
  legacy documents lack `updated_at`, so a revision feed would silently
  drop updates. Supported alternative: page the endpoint without
  `updated_since` (sort, offset/limit, or cursor).

## Deletion semantics

- **Action items**: deletes are hard deletes by default — a hard-deleted
  item leaves no row and is **not** emitted by the sync feed. Rows that
  persist with `deleted: true` (soft tombstones written by retirement
  flows) are emitted with `deleted: true` so clients can reconcile them.
- **Conversations / memories**: both models persist soft-delete tombstone
  rows (discarded/deleted markers), so deletes **are** recorded — but
  their `updated_since` feeds are unsupported (400) and the plain list
  cursors already skip tombstones. Clients must re-fetch or reconcile on
  their own cadence; no deletes are silently claimed covered today.

## Conversation detail bounds

`GET /v1/mcp/conversations/{id}` returns the full transcript through the
shared bounded reader: at most 4096 segments and 500,000 transcript
characters. When output is clipped, the additive `truncated` field is
`true`; `speaker_name` is populated on each segment, and `apps_results` is
preserved. List/search responses stay lean: no transcript, no photos, and
`apps_results` projected from the card field paths.
