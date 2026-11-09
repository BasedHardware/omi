# Mobile memory deletion

`MemoriesProvider` owns the deletion lifecycle for every mobile memory entry
point. `memory_delete_undo.dart` presents the shared Undo and error feedback;
`memories_provider_deletion.dart` holds the per-ID operations. This applies to
memories, not conversation or recording-file deletion.

## Transitions

- Stage: capture the nonempty owner and session generation, hide the selected
  ID, and offer Undo. Replacing its toast commits the previous operation without
  losing that operation's suppression or failure callback.
- Undo: restore only a staged operation. A submitted DELETE cannot be undone.
- Commit: timer and toast completion join one request. All pending and in-flight
  IDs stay hidden in provisional pages, history continuations and cache fallback.
- Creation handoff: if the selected offline draft is already uploading, await
  its canonical ID and delete that server record. Undo restores the canonical
  row when its upload has finished. A staged draft is not newly uploaded by sync.
- Success: suppress both draft and canonical IDs. Owner-scoped confirmed-delete
  markers are written before cache eviction. A rejected cache write cannot undo
  a durable marker; a rejected marker write falls back to checked cache eviction.
  If both fail, surface failure rather than silently claiming local persistence.
- Refusal: restore only that operation's row and report failure once. HTTP 404
  means the requested row is already absent; 403 and server errors remain failures.
- Retirement: account clear/delete-all invalidates every captured generation.
  No late rollback, indexing, cache write or error callback reaches the replacement
  session. The same owner predicate reaches the real HTTP adapter and is checked
  again after authentication waits and before each retry. Disposal stops UI
  publication, while an already-submitted success may still retire the same
  owner's cache.

## Verification checklist

- Provider regressions: multiple deletes, refresh, single-flight commit, Undo,
  same-UID reauthentication, different account, disposal, refused requests,
  draft creation/sync and returned canonical IDs.
- Cache regressions: refused/throwing writes, process-style preferences reload,
  stale cache writers and identical IDs under another owner.
- Simulator integration: real `MemoryItem` swipe and Undo, loopback HTTP refusal,
  visible error, successful retry, offline reopen, 404 and 403. Paused-authentication
  create/delete scenarios prove that a retired operation dispatches no HTTP write.
- Run the existing progressive-load, ledger correction, visibility, delete-all,
  session-generation and nonblocking Spotlight tests, then repository preflight
  and current-commit CI before readiness.

The simulator uses synthetic records and a loopback fixture. Passing these checks
does not identify the root cause of a particular account's report or establish
mobile-store release availability. #24719 retains the broader trace investigation.
