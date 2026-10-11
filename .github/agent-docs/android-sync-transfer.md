# Android recording-transfer keep-alive

Companion to [`app/AGENTS.md`](../../app/AGENTS.md) Native Bridge / permission matrix.

Keep BLE/cloud WAL file sync alive for the transfer lifetime when the screen turns
off (#5221). Battery-optimization guidance is not the fix.

## Contract

- Start a `dataSync` foreground service plus `PARTIAL_WAKE_LOCK` when a
  `RecordingTransferCoordinator` pass or `SyncProvider._performSync` begins.
- Stop it when that pass completes, `cancelSync()` runs, or the Flutter engine dies.
- New discovery/drain passes stay foreground-only. An in-flight pass must finish
  after `setForeground(false)`; background connectivity must not queue another
  whole-WAL drain, and a coalesced extra pass already queued is dropped.

## Surfaces

- Channel: `com.friend.ios/sync_transfer` (`start` / `stop`)
- Dart: `app/lib/services/wals/sync_transfer_keep_alive.dart` (refcount; iOS no-op)
- Android: `app/android/app/src/main/kotlin/com/friend/ios/sync/`
  (`SyncTransferForegroundService`, `SyncTransferPlugin`)
- Wired from coordinator pass start/finish and `SyncProvider._performSync` /
  `cancelSync` / `transferWalToPhone`

## Tests

- `app/test/services/wals/recording_transfer_coordinator_test.dart`
- `app/test/services/wals/sync_transfer_keep_alive_test.dart`
- `app/test/providers/sync_provider_sync_wal_wake_test.dart`
- `app/android/app/src/test/kotlin/com/friend/ios/sync/SyncTransferKeepAlivePolicyTest.kt`
