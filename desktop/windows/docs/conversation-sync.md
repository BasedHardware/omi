# Conversation Sync (screen sessions → Omi cloud)

How the Windows app gets screen-session (mic + system audio) conversations into
the Omi cloud without touching backend code. Client-only; the design was settled
by live-prod experiments on 2026-07-10 — the "prod facts" below are verified
behavior, not assumptions.

## Why not /v4/listen for screen sessions

- Two same-uid `/v4/listen` sockets coalesce through a **racy user-global Redis
  pointer** — reproduced splitting one session into two conversations, with
  cross-device bleed risk. `client_conversation_id` is ignored (feature not
  deployed), and both app sockets send `source=desktop`, so the backend can't
  tell mic from system.
- Mic-only sessions keep `/v4/listen` (one socket — the pointer is safe, and the
  server-created conversation is correct today).

## The design

1. **During a screen session** both lanes stream via
   `wss://api.omi.me/v2/voice-message/transcribe-stream` (transcription-only,
   creates NO conversations) using listen mode `'transcribe'` — a distinct mode
   value so PTT's single-at-a-time supersede sweep never kills a screen lane
   (`src/main/ipc/omiListen.ts`). Zero conversations mid-session → the
   duplication race is structurally impossible.
2. **Raw segments are retained per lane** (`lib/sync/segmentRetention.ts`): the
   display path discards from-segments fields, so each lane keeps its raw
   `BackendSegment`s, stamped with **wall-clock session-relative offsets at
   arrival**. Stream timestamps track cumulative *audio* time (the VAD gate
   compresses silence out), so each batch is anchored to `Date.now() - start`
   and stream times only order segments *within* a burst. Re-emitted segment ids
   upsert in place, keeping their original wall-clock start.
3. **On stop** (`useRecorder.stop()`): both lanes get `finalize` (2.5s
   trailing-segment window), then `lib/sync/mergeLanes.ts` interleaves the lanes
   by wall-clock (system is never `is_user`; its speaker ids are offset past the
   mic lane's) and the row is saved locally with the merged segments and outbox
   state `pending` **before** any network call. Then
   `POST /v1/conversations/from-segments` with `source='desktop'` (the only
   provenance field that round-trips), `client_platform='windows'`, real
   `started_at`/`finished_at`, and `client_session_id` = the local conversation
   id (ignored by prod today; becomes idempotency when upstream deploys).

## Outbox semantics (`lib/sync/outbox.ts`)

**Prod does NOT honor `client_session_id` — a blind retry duplicates.** Retry
idempotency is therefore client-owned:

```
local_only ─▶ pending ─▶ posting ─▶ done
                 ▲          │  ╲
                 │          ▼   ▼
                 └────── failed  unconfirmed ─▶ (dedupe) ─▶ done │ posting
```

- The row is persisted **before** the first POST.
- `failed` = an HTTP error *response* arrived (server created nothing) → safe to
  re-post. `unconfirmed` = timeout / network drop after send (ambiguous).
  Unclassified errors default to ambiguous.
- A retry from `unconfirmed` **must** first check `GET /v1/conversations` for a
  conversation whose `started_at`/`finished_at` match ours (they round-trip from
  our own POST; segment count breaks ties — `findCloudMatch`). Match → adopt it
  as `done` without posting. No match → the earlier POST never landed → re-post.
- A row found `posting` with no in-flight request in this process is a crash
  mid-POST → recovered as `unconfirmed`.
- State lives in `local_conversation` (columns `sync_state`, `segments_json`,
  `cloud_id`, `sync_attempts`, `sync_error`) added by **versioned migration 1**
  (`src/main/ipc/dbMigrations.ts` — `PRAGMA user_version`, ordered, exactly-once,
  per-migration transactions; tested against a fixture db with the old schema).

## UI (`pages/Conversations.tsx`)

- Local recording rows badge their outbox state: **Sync pending** (queued /
  in-flight / unconfirmed), **Sync failed**, or the legacy **Not synced**.
- On each list load: awaiting-sync rows whose cloud twin appeared are adopted as
  `done` and hidden (the cloud row wins); a throttled retry pass (≥60s apart,
  ≤10 attempts/row) pushes stragglers.
- **Backfill**: when legacy `local_only` recordings exist, a quiet banner offers
  "Sync past recordings" (`lib/sync/backfill.ts`) — segments are synthesized
  from the saved display transcript, each row is queued (`pending`, segments
  persisted) before its POST so the run is resumable, paced at **≤25/hour**
  (sliding window in localStorage) under the 30/hour from-segments limit.

## Known prod quirks (relied upon / tolerated)

- from-segments conversations process asynchronously; **DELETE before
  `status=completed` can race and resurrect** — the app never deletes its own
  synced rows early, and the E2E harness deletes only after `completed`.
- The generated title stays the raw first-segment text (overview/category/action
  items are processed normally).
- `client_platform` is accepted but doesn't round-trip; rely on `source`.

## Testing

- Hermetic units: `npx vitest run src/renderer/src/lib/sync src/main/ipc/dbMigrations.test.ts`
  (retention/stamping, merge, outbox incl. the unconfirmed-dedupe path, reconcile,
  backfill planner/parser, migrations against an old-schema fixture db).
- Live-prod E2E: `pnpm test:e2e:conv-sync` — simulates a screen session at the
  lib level (two real transcribe-stream lanes → merge → POST → poll to
  completed → assert → DELETE → verify by re-list). Auth via
  `OMI_E2E_REFRESH_TOKEN` in `.env`, opt-in `OMI_E2E=1` (the runner sets it);
  never runs in plain `pnpm test`. All created content is labeled
  "Omi test fixture" and deleted, with an afterAll cleanup backstop.
