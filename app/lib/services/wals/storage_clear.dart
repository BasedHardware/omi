// Manage Storage clear model: which recordings each clear removes, the hours
// of audio per storage row, and the verified outcome of a clear. Pure and
// synchronous; SyncProvider.clearStorage owns running a clear.
import 'package:omi/services/wals/wal.dart';

/// What a Manage Storage clear removes.
enum StorageClearScope {
  /// Phone copies of audio the server already turned into conversations.
  /// Loses nothing, so it never stops a transfer.
  uploaded,

  /// Audio not uploaded yet, on the phone or still on the pendant. Lost for good.
  notUploaded,

  /// Both, plus recordings that can no longer be uploaded.
  all,
}

enum StorageClearPhase { stopping, deleting, verifying }

class StorageClearProgress {
  const StorageClearProgress(this.phase, {this.done = 0, this.total = 0});

  final StorageClearPhase phase;
  final int done;
  final int total;
}

/// The verified result of a clear: what was asked for and what is still there
/// after the stores were re-read. Never reports success without that re-read.
class StorageClearOutcome {
  const StorageClearOutcome({
    required this.targetSeconds,
    required this.targetCount,
    required this.remainingSeconds,
    required this.remainingCount,
    required this.remainingOnDeviceSeconds,
    required this.failed,
  });

  final int targetSeconds;
  final int targetCount;
  final int remainingSeconds;
  final int remainingCount;

  /// Part of [remainingSeconds] still on the pendant (not connected, or it did
  /// not confirm the clear).
  final int remainingOnDeviceSeconds;

  /// A store threw, the account changed, or a transfer would not stop in time.
  final bool failed;

  int get deletedSeconds => targetSeconds > remainingSeconds ? targetSeconds - remainingSeconds : 0;
  bool get complete => !failed && remainingCount == 0;
}

/// Hours of audio per Manage Storage row, read from the same rows a clear targets.
class StorageAmounts {
  const StorageAmounts({
    required this.uploadedSeconds,
    required this.uploadedCount,
    required this.phonePendingSeconds,
    required this.devicePendingSeconds,
    required this.pendingCount,
    required this.allCount,
    required this.allSeconds,
  });

  factory StorageAmounts.of(Iterable<Wal> wals, {int? freshDeviceSeconds}) {
    var uploadedSeconds = 0, uploadedCount = 0;
    var phonePending = 0, devicePending = 0, pendingCount = 0, deviceRows = 0;
    var allCount = 0, allSeconds = 0;
    for (final wal in wals) {
      final scope = storageClearScopeOf(wal);
      if (scope == null) continue;
      final seconds = wal.seconds > 0 ? wal.seconds : 0;
      allCount++;
      allSeconds += seconds;
      if (scope == StorageClearScope.uploaded) {
        uploadedCount++;
        uploadedSeconds += seconds;
      } else if (scope == StorageClearScope.notUploaded) {
        pendingCount++;
        if (isDeviceStoredWal(wal)) {
          deviceRows++;
          devicePending += seconds;
        } else {
          phonePending += seconds;
        }
      }
    }
    // While the pendant is being read its virtual row can be unlisted; the
    // fresh INFO backlog is the same audio, so show it rather than nothing.
    final fresh = freshDeviceSeconds ?? 0;
    if (deviceRows == 0 && fresh > 0) {
      devicePending = fresh;
      pendingCount++;
      allCount++;
      allSeconds += fresh;
    }
    return StorageAmounts(
      uploadedSeconds: uploadedSeconds,
      uploadedCount: uploadedCount,
      phonePendingSeconds: phonePending,
      devicePendingSeconds: devicePending,
      pendingCount: pendingCount,
      allCount: allCount,
      allSeconds: allSeconds,
    );
  }

  final int uploadedSeconds;
  final int uploadedCount;
  final int phonePendingSeconds;
  final int devicePendingSeconds;
  final int pendingCount;
  final int allCount;
  final int allSeconds;

  int get pendingSeconds => phonePendingSeconds + devicePendingSeconds;
}

bool isDeviceStoredWal(Wal wal) => wal.storage == WalStorage.sdcard || wal.storage == WalStorage.flashPage;

/// The narrowest clear that removes [wal], or null when no clear touches it:
/// the live in-memory buffer, and audio the server accepted but has not
/// settled (it is neither safe to drop nor still waiting on the user).
StorageClearScope? storageClearScopeOf(Wal wal) {
  if (wal.storage == WalStorage.mem) return null;
  switch (wal.status) {
    case WalStatus.synced:
      // "Free up space" removes phone copies only; a synced row still listed
      // on a device store goes with Delete everything.
      return isDeviceStoredWal(wal) ? StorageClearScope.all : StorageClearScope.uploaded;
    case WalStatus.miss:
      return StorageClearScope.notUploaded;
    case WalStatus.corrupted:
    case WalStatus.outsideRecoveryWindow:
    case WalStatus.unsupportedAudio:
    case WalStatus.uploadRejected:
      return StorageClearScope.all;
    default:
      return null;
  }
}

/// Rows [scope] removes.
List<Wal> storageClearTargets(Iterable<Wal> wals, StorageClearScope scope) => wals.where((wal) {
      final own = storageClearScopeOf(wal);
      if (own == null) return false;
      return scope == StorageClearScope.all || own == scope;
    }).toList();

/// Identity that survives rediscovery. The pendant ring is one virtual row
/// rebuilt with a new id and display time on every read, so it is matched by
/// device; every other row by storage and id.
(WalStorage, String) storageClearIdentity(Wal wal) {
  final ring = wal.storage == WalStorage.sdcard && wal.fileNum == -1;
  return (wal.storage, ring ? 'ring:${wal.device}' : wal.id);
}

/// Compares [targets] with the re-read [current] rows.
///
/// A pendant ring that is still recording refills while it is cleared, so a
/// rebuilt ring row only counts as retained when it holds more audio than
/// could have been recorded during the clear itself ([elapsed] plus slack).
StorageClearOutcome verifyStorageClear({
  required List<Wal> targets,
  required Iterable<Wal> current,
  required Duration elapsed,
  required bool failed,
}) {
  final byIdentity = <(WalStorage, String), Wal>{};
  for (final wal in current) {
    if (storageClearScopeOf(wal) == null) continue;
    byIdentity[storageClearIdentity(wal)] = wal;
  }
  final refillAllowance = elapsed.inSeconds + 30;
  var targetSeconds = 0, remainingSeconds = 0, remainingCount = 0, remainingDevice = 0;
  for (final target in targets) {
    final seconds = target.seconds > 0 ? target.seconds : 0;
    targetSeconds += seconds;
    final match = byIdentity[storageClearIdentity(target)];
    if (match == null) continue;
    final ring = match.storage == WalStorage.sdcard && match.fileNum == -1;
    if (ring && match.seconds <= refillAllowance) continue;
    final left = ring ? (match.seconds < seconds ? match.seconds : seconds) : seconds;
    remainingCount++;
    remainingSeconds += left;
    if (isDeviceStoredWal(match)) remainingDevice += left;
  }
  return StorageClearOutcome(
    targetSeconds: targetSeconds,
    targetCount: targets.length,
    remainingSeconds: remainingSeconds,
    remainingCount: remainingCount,
    remainingOnDeviceSeconds: remainingDevice,
    failed: failed,
  );
}
