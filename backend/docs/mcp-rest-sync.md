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

## Read correctness and coverage (wave 2)

Date-filtered MCP tools and REST conversation list/search, screen activity and
summary routes accept optional `timezone`: an IANA name (for example
`Asia/Ho_Chi_Minh`) or `profile` to resolve `time_zone` from the owner's profile.
**Omitting it preserves UTC** for released clients that construct UTC day windows;
this is the existing documented sync contract and is pinned by
`test_mcp_search_date_utc.py`. New local-day callers should pass `profile`.
Date-only bounds include the entire selected local end day, including DST
transitions. Aware REST datetime bounds remain exact instants; explicit timezone
interprets naive bounds locally. Returned timestamp fields use ISO 8601 offsets,
except screen activity retains its released formatting unless timezone or timestamp_format=iso_offset is supplied. MCP keeps exact stored strings; REST keeps its existing datetime-model normalization without adding an offset.
Daily-summary date labels identify stored recaps; timezone does not regenerate or
rebucket their prose. `timezone` on the read response identifies the window used
for recording counts and missing-day classification. Historic recap creation
zones were not persisted and cannot be reconstructed reliably.

`get_memories(updated_after=...)` queries persisted `updated_at` before applying
the universal memory policies. Positive reviewed/manual and non-default category
filters also use indexed candidate predicates when no timestamp predicate is
present. Missing legacy booleans/categories retain their released defaults and
are checked after hydration. Canonical lineage/privacy/eligibility and historical
suppression are unchanged. Legacy records without `updated_at` remain outside
an `updated_after` window; without that filter the created-only leg is included.
New composite indexes are declared in the registry and generated manifest. While
an index builds, the bounded single-field fallback retains the timestamp bound,
rechecks every predicate, and emits fallback telemetry. A candidate set above
5000 rows per store returns `memory_filter_window_exceeded`, never a successful
partial empty page. Narrow the filter. Unfiltered `created_desc` and `manual_first`
retain released bounded source-window semantics: one first batch (100 rows for a
20-item request; at most 200), sorted within that newest-updated window. They
never scan all stores or fail solely because an account exceeds 5000 memories.
`scan_truncated=true`, `source_window_limit` and `coverage` explicitly identify
unknown global ordering/exhaustion; `more_in_window` and offset cursors describe
only the materialized window. The REST array reports `X-Scan-Truncated: true`.
Use `updated_desc` with a cursor for larger exports.
`scanned_count` on the indexed path counts deduplicated candidates before policy
filtering (the default bounded path counts source rows after universal policy); `matched_count` counts eligible matches in the materialized filtered
window.
`more_in_window` counts known matches already scanned; keyset pages additionally
return `more_in_window_known=false` when their continuation contains unexamined
candidates. `has_more` on that path means that a resumable candidate cursor exists,
not that another eligible match has already been proved.

`get_conversations_by_ids` accepts 1–20 IDs, shrinks transcript and structured
text budgets evenly, preserves request order, and returns `omitted_ids`,
`next_ids`, and `next_cursor` when metadata still cannot fit. Resume with the
same IDs/filters and cursor, or request `next_ids` directly. `not_found` contains
only missing IDs; short ID prefixes receive a `use the full id` hint. Prefix
lookup is not enabled. Each item keeps the released nested `conversation` and
adds the same flat card as list/search. Optional `fields` (array or comma-separated
names; `id` retained) selects card fields; `summary_only=true` on detail tools
omits transcripts. `truncated_fields` names clipped structured fields. Locked
items retain their existing paid-plan error and never expose transcript content.
Cards add nullable `source`, `is_call`, `call_platform`, `calendar_event_id` from
stored source/calendar context (including `external_data.calendar_meeting_context`).
Unknown call identity remains null. A linked calendar event alone does not prove
a remote call. Action items add stored provenance or `manual`, `chat`, `unknown`
when no conversation identity exists; no provenance is guessed from task prose.

Screen `group_by=app|hour|day` aggregates the window server-side, independently
of raw-page `limit`. A supplied group cursor is ignored with a `note`; groups have no next cursor. `coverage` reports a 5000-row
bound, scanned count, first/last observations and `complete_window`; truncation
is explicit. With no timezone, timestamp strings and `YYYY-MM-DD HH:00` hour labels retain the released format. Explicit `timezone` (including UTC) or `timestamp_format=iso_offset` opts into ISO offsets. Capture/sync completeness remains
unknown. These are observation counts and bounded observation seconds, not
proof of device usage duration. Raw mode remains cursor-paginated.

Daily summary reads expose `status` and `generated_at`. With **both** date bounds,
pagination counts calendar days, including stub rows: `no_recordings` (past day,
zero non-discarded recordings), `not_generated` (past day with recordings),
`failed` (persisted generation failure), or `pending` (generation marker or current/
future date). Stub `generated_at` is null. Failures before a generation marker was
persisted cannot be inferred historically and appear as `not_generated`.
Without both bounds, the released list still pages stored summaries only.
The generation schedule and automatic after-midnight regeneration are unchanged.

Newly generated recaps derive `action_items`, `action_items_count` and
`action_items_created` from **one created-in-window task read**. Historical recaps
expose `action_items_coverage=legacy_conversation_subset` and preserve the old
counter as `stored_action_items_created` when it differs; the payload counters
always equal the array length. Memories deliberately have two meanings:
`memories_created` counts stored creations (including rows ineligible for the
review card); `memories_learned` is the existing at-most-three review selection
from at most 600 newest-updated universal memories. `memories_learned_count` and
`memories_learned_coverage` expose the actual selection and its bound. An empty
review card is not evidence that no memories were stored. Legacy producers
without a recorded review payload are labeled `not_recorded_by_legacy_producer`;
existing legacy review selections have unknown coverage rather than a fabricated
scan bound.

`total_conversations` uses a Firestore aggregation over non-discarded recordings
whose `started_at` falls in the local day, with no list limit; existing recaps'
counts are corrected on read. `summarized_conversations` labels the producer's
bounded prompt subset. Duration/highlights/locations still describe that subset.
The count fallback scans at most 10000 projections and fails explicitly above
that bound while its index is unavailable.

New `watching_minutes` is the clipped union of consecutive capture intervals per
device, capped at five minutes per gap and 1440 minutes per local day. Its unit is
`minutes` and basis is `screen_observation_interval_union`; `watching_coverage`
exposes the 5000-observation bound and unknown unsynced capture coverage. It is
an **observation estimate**: stored desktop usage totals contain no intervals,
so actual elapsed watching time across devices cannot be recovered from them.
Their sum remains `reported_device_watching_minutes`. Historical values are
clamped and explicitly labeled `legacy_device_counter_sum_clamped; interval
union unavailable`, with unknown coverage; they are not claimed reconstructed.
No historical documents are rewritten by these reads.
