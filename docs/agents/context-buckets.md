# Context Buckets

Context buckets are the durable, per-subject work memory built from what the user actually
does on screen. This document describes the system as it exists, the boundary between the
device and the backend, and the migration that moves the *readable* half of the system into
the backend so every consumer — chat, the Flutter app, Windows desktop, agents — can use it.

## The loop

A **visit** opens when the user dwells in a window. When they leave, one screenshot plus an
extraction prompt goes to the proactive lane; the model returns a narrative, a set of facts,
and an optional destination. Heuristics validate the facts, an immutable **bucket version**
is published, and a **director** decides whether the visit is worth a proactive notification
or a task.

```
dwell -> visit opens -> departure -> extraction (gpt-5-nano, 1 screenshot)
      -> heuristic validation -> bucket_version published
      -> director (gpt-5.6-luna) -> notification | task | nothing
```

Bucket identity is `sha256(app :: normalized window title)`, a durable work-history handle,
or a browser destination key such as `dest:x.com/feed`.

## Where the pieces live

The capture half is macOS-only, in Swift over SQLite/GRDB inside the Rewind database:

| Concern | Owner |
|---|---|
| Visit lifecycle, dwell, departure | `ContextVisitCoordinator.swift` |
| Extraction, validation, version publishing | `ContextBucketRollup.swift` |
| Local storage, GC, compaction | `ContextBucketStore.swift`, `ContextBucketSchema.swift` |
| Notification decisions | `ContextProactivityEngine.swift` |
| Rate limits and cooldowns | `ContextDeliveryAuthority.swift` |
| Workstream tagging, candidate arming | `ContextWorkstreamReconciler.swift` |
| Feature flags and kill switches | `ContextBucketsFeature.swift` |

The backend's role before this migration was a single metered LLM proxy lane,
`POST /v1/desktop/proactivity/completions` in `backend/routers/desktop_proactivity.py`.

## Why the readable half moves to the backend

Everything the extraction pipeline learns is trapped on one Mac. Chat cannot see it, the
Flutter app cannot see it, Windows has no implementation, and a user with two machines has
two disjoint memories. The facts are the valuable artifact and they are small; the
screenshots that produced them are large, private, and only needed at capture time.

So the split is: **capture stays local, facts sync.**

## The device/backend boundary

Synced to the backend:

- Bucket identity and counters: `bucket_id`, `subject_kind`, `workstream_id`,
  `notify_worthiness`, `visit_count`, `last_visited_at`.
- Validated facts only: `statement`, `confidence`, `notify_worthiness`,
  `disposition_state`, `expires_at`, `workstream_tag`.

`statement` is the only free text that crosses, and it is model-authored prose about the
work rather than anything copied from the screen.

Never synced:

- Screenshots, video chunks, and any image bytes.
- `evidence_text` — the quoted on-screen text a fact was extracted from.
- `narrative`, `bucket_entries`, and the frozen ranked segment.
- `raw_context_key` / `normalized_context_key` — window titles.
- `display_label` and `subject_id` — these hold the normalized window title, or for a
  durable handle the raw URL or file path. Nothing reads them on the backend, so they are
  not published; a bucket is identified by its id.
- `identifiers` — the extraction prompt asks for handles *copied from the quoted on-screen
  text*, so they are literal screen strings by construction.
- Visits, proactive deliveries, and subject bindings.
- Evidence references. The device has no id a consumer could resolve back to a screen
  frame, so publishing one would assert provenance the payload cannot support.

Facts that are not `validated` never leave the device. `proposed`, `needs_review`,
`rejected`, and `superseded` are working state for the local validator; publishing them
would export exactly the low-confidence content the validator exists to withhold.

The result is that the backend holds a set of short, model-authored statements about the
user's own work, in the user's own account, alongside the memories and conversations that
already live there — and holds no raw screen content at all.

## Backend shape

Firestore, under `users/{uid}`:

```
context_buckets/{bucket_id}
    subject_kind, workstream_id, notify_worthiness, visit_count, last_visited_at,
    device_id, device_updated_at, account_generation, created_at, updated_at

context_bucket_facts/{fact_id}
    bucket_id, statement, confidence, notify_worthiness,
    disposition_state, workstream_tag, expires_at,
    device_id, device_updated_at, account_generation, created_at, updated_at
```

Facts sit beside buckets rather than beneath them. A flat per-user collection makes every
fact read one owner-scoped query; a subcollection would force either a fan-out across
buckets or a collection-group query spanning every user in the database.

Routes in `backend/routers/context_buckets.py`:

| Route | Purpose |
|---|---|
| `POST /v1/context-buckets/sync` | Idempotent batch upsert from a device |
| `GET /v1/context-buckets/facts` | Flat validated-fact read for consumers |
| `POST /v1/context-buckets/purge` | Device-initiated deletion of synced copies |

**Write ordering** is enforced by `device_updated_at`: a write whose device timestamp is
older than the stored one is skipped, so retries and out-of-order delivery cannot regress
state. This governs which write wins, not how reads sort — reads order by the server's
`updated_at`, because a consumer wants the most recently *known* state, and a device clock
is not a source consumers should sort by. Each bucket and its facts commit in one
transaction that re-reads inside the transaction, so concurrent syncs cannot both observe
the same old row and both write.

Device times are clamped to one hour ahead of the server. Ordering trusts a clock the
server does not control, so without a bound a device running fast could stamp a far-future
timestamp and lock every other device out of that row. Clamping rather than rejecting keeps
a mildly skewed clock syncing normally, instead of failing closed on something the user
cannot see or fix.

A row from a different `account_generation` is never stale. Generation fences every read,
so a row left behind at the old generation is already invisible; treating its republish as
redundant would strand it forever, because the device has no reason to bump a device clock
that did not change.

**Purge is account-wide by design.** It deletes every synced copy of a bucket, not only the
rows the calling device published. Excluding an app is a privacy action: the user is saying
this app's activity should not be retained, and honoring that on one device while leaving
the same content readable by chat and every other device would defeat the point. Bucket ids
are locally-minted UUIDs, so in practice two devices do not share one, but the account-wide
semantics are the intended contract either way.

`account_generation` is validated against the account's own cutover record before it is
used, and a mismatch is a 409. The header states which generation the caller believes it
is on; it is not itself the fence, because a client that could choose its generation could
read a superseded incarnation's context back or pin writes into a generation nothing
reads. It is stored on every document and filters every read, so data from a superseded
generation becomes invisible rather than requiring a migration.

Expired facts are filtered on read as well as deleted by GC, so a lagging GC never serves
stale context.

## Consumers

Chat is the first reader. `_get_work_context_section` in `backend/utils/llm/chat.py` renders
validated facts above a 0.6 confidence floor, capped at 20, into a `<work_context>` block in
the agentic system prompt.

Three constraints apply to any consumer added later. Chat must never fail because this
optional context is unavailable, so every read error degrades to an empty section. Fact text is model-authored but originates from whatever was on screen, including pages an
attacker controls, so it is collapsed to a single line and escaped before entering the
prompt — escaping alone would still let a multi-line statement impersonate an instruction. And the block is additive, so it does not shift the cacheable static
prompt prefix.

The prompt tells the model this is background awareness and not to recite it back — a user
told what they were doing on screen experiences surveillance rather than help.

## Device publisher

`ContextBucketSyncClient` posts to the sync and purge routes, mirroring
`ProactiveLaneClient` for auth, owner fencing, and bounded errors. Its payload logic is pure
statics so it is testable without a URLProtocol stub.

`ContextBucketSyncSelection` chooses what to publish. It selects only `validated`, unexpired
facts, and the payload has no field for `evidenceText`, `narrative`, or context keys — quoted
screen text cannot be published by adding a caller, only by changing the payload shape.

`ContextBucketSyncScheduler` runs every 30 minutes from a persisted keyset cursor on
`(updatedAt, id)`. A bare "newest N" window would leave bucket N+1 permanently
unpublishable, and a timestamp-only cursor would step past all but the first N buckets
written in the same batch. The cursor advances only past rows the server accepted.

Excluding an app retracts published copies as well as deleting local rows. Exclusion is a
privacy action, so it must reach every copy; the local delete stays authoritative, and a
failed retraction retries rather than blocking exclusion.

Sync is gated by `ContextBucketsFeature.isBackendSyncEnabled` — dogfood-only, off in
production and beta, with the inverted `OMI_FORCE_BUCKET_SYNC=0` override.

## Local tuning constants

These stay on the device because they govern capture, not readability.

| Constant | Value | Source |
|---|---|---|
| Dwell before a visit settles | 2 s | `ContextProactivityEngine.swift` |
| Cold-start gate | 1 prior completed visit within 7 d | `ContextBucketStore.swift` |
| Backend sync cadence | 30 min | `ContextBucketSyncScheduler.swift` |
| Injection token budget | 7,500 | `ContextBucketRollup.swift` |
| Departure worthiness threshold | 0.6 | `ContextProactivityEngine.swift` |
| Bucket GC | 30 d unvisited, newest 250 kept | `ContextBucketStore.swift` |
| Reconciler cadence | 15 min | `ContextWorkstreamReconciler.swift` |
| Delivery budget | 24 h rolling, per-level cooldown | `ContextDeliveryAuthority.swift` |

## Known weaknesses

- **Cold start.** A bucket needs a prior completed visit within 7 days before it is minted.
  The gate is a deliberate noise filter — most windows are seen once — but work on a cadence
  slower than the window never accumulates context, because every visit looks like the first.
  Widening it admits slower work at the cost of more buckets; the constant is now named and
  documented at its use site, but the value is unchanged pending that product call.
- **One frame per visit.** The whole evidence base for a visit is its last screenshot, so a
  long session is summarized by whatever happened to be on screen at the end.
- **Constants are only partly gathered.** Delivery budget, pooling, and reconciler values
  already live in named enums, and the cold-start gate now does too. What remains is that none
  of them are remotely tunable — changing any threshold still needs a release.
- **macOS only.** Windows has no implementation; the Flutter app has none either.
- **Sync is dogfood-only.** `isBackendSyncEnabled` is off in production and beta, so no
  production user's facts reach the backend yet.

## Migration sequence

1. Backend schema, sync/read/purge API, tests, this document. *(done)*
2. Chat prompt assembly reads validated facts. *(done)*
3. Device publisher, scheduler, and purge retraction. *(done)*
4. Flutter and Windows consumers. *(not started)*
