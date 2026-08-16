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

- Bucket identity and label: `bucket_id`, `subject_kind`, `subject_id`, `workstream_id`,
  `display_label`, `notify_worthiness`, `visit_count`, `last_visited_at`.
- Validated facts only: `statement`, `identifiers`, `confidence`, `notify_worthiness`,
  `disposition_state`, `expires_at`, `workstream_tag`.
- `EvidenceRef` pointers with `scope=device_local`, `kind=local_screen`, and a `device_id`.
  These name the evidence without carrying it.

Never synced:

- Screenshots, video chunks, and any image bytes.
- `evidence_text` — the quoted on-screen text a fact was extracted from.
- `narrative`, `bucket_entries`, and the frozen ranked segment.
- `raw_context_key` / `normalized_context_key` — window titles.
- Visits, proactive deliveries, and subject bindings.

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
    subject_kind, subject_id, workstream_id, display_label,
    notify_worthiness, visit_count, last_visited_at,
    device_id, device_updated_at, account_generation, created_at, updated_at

context_bucket_facts/{fact_id}
    bucket_id, statement, identifiers[], confidence, notify_worthiness,
    disposition_state, workstream_tag, expires_at, evidence_refs[],
    device_id, device_updated_at, account_generation, created_at, updated_at
```

Facts sit beside buckets rather than beneath them. A flat per-user collection makes every
fact read one owner-scoped query; a subcollection would force either a fan-out across
buckets or a collection-group query spanning every user in the database.

Routes in `backend/routers/context_buckets.py`:

| Route | Purpose |
|---|---|
| `POST /v1/context-buckets/sync` | Idempotent batch upsert from a device |
| `GET /v1/context-buckets` | List buckets for the user |
| `GET /v1/context-buckets/facts` | Flat validated-fact read for consumers |
| `POST /v1/context-buckets/purge` | Device-initiated deletion of synced copies |

Ordering is enforced by `device_updated_at`: a write whose device timestamp is older than
the stored one is skipped, so retries and out-of-order delivery cannot regress state. A
device may only overwrite rows it owns unless the incoming write is strictly newer, which
keeps two Macs syncing the same bucket from flapping.

`account_generation` comes from the `X-Account-Generation` header, is stored on every
document, and filters every read. Data from a superseded generation becomes invisible
rather than requiring a migration.

Expired facts are filtered on read as well as deleted by GC, so a lagging GC never serves
stale context.

## Local tuning constants

These stay on the device because they govern capture, not readability.

| Constant | Value | Source |
|---|---|---|
| Dwell before a visit settles | 2 s | `ContextProactivityEngine.swift` |
| Cold-start gate | 1 prior completed visit within 7 d | `ContextBucketStore.swift` |
| Injection token budget | 7,500 | `ContextBucketRollup.swift` |
| Departure worthiness threshold | 0.6 | `ContextProactivityEngine.swift` |
| Bucket GC | 30 d unvisited, newest 250 kept | `ContextBucketStore.swift` |
| Reconciler cadence | 15 min | `ContextWorkstreamReconciler.swift` |
| Delivery budget | 24 h rolling, per-level cooldown | `ContextDeliveryAuthority.swift` |

## Known weaknesses

- **Cold start.** A bucket needs a prior completed visit within 7 days before it resolves,
  so genuinely new work never accumulates context on its first day.
- **One frame per visit.** The whole evidence base for a visit is its last screenshot, so a
  long session is summarized by whatever happened to be on screen at the end.
- **Constants are scattered.** Roughly 25 thresholds are hardcoded across seven files with
  no shared configuration surface and no way to tune them without a release.
- **macOS only.** Windows has no implementation; the Flutter app has none either.
- **No chat consumption.** Even after this migration, chat prompt assembly does not yet read
  the synced facts.

## Migration sequence

1. Backend schema, sync/read/purge API, tests, this document. *(this change)*
2. Swift sync client: publish validated facts on version publish, purge on app exclusion.
3. Chat prompt assembly reads validated facts.
4. Flutter and Windows consumers.
