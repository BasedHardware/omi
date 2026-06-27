import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';

/// Pure mapping that the entire sync UI + provider classification depends on.
/// A not-yet-synced recording must never be visually identical to a failed
/// one, and an `uploaded` (processing) recording must read distinctly.
void main() {
  Wal makeWal({
    required WalStatus status,
    bool isSyncing = false,
    int retryCount = 0,
    String? jobId,
  }) {
    return Wal(
      timerStart: 1700000000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: status,
      retryCount: retryCount,
      jobId: jobId,
    )..isSyncing = isSyncing;
  }

  group('Wal.syncDisplayState', () {
    test('isSyncing wins over every status', () {
      for (final s in WalStatus.values) {
        final w = makeWal(status: s, isSyncing: true);
        expect(w.syncDisplayState, WalSyncDisplayState.syncing, reason: 'status=$s');
      }
    });

    test('uploaded -> uploaded (processing on server)', () {
      final w = makeWal(status: WalStatus.uploaded, jobId: 'job-1');
      expect(w.syncDisplayState, WalSyncDisplayState.uploaded);
    });

    test('synced -> synced', () {
      expect(makeWal(status: WalStatus.synced).syncDisplayState, WalSyncDisplayState.synced);
    });

    test('corrupted -> corrupted', () {
      expect(makeWal(status: WalStatus.corrupted).syncDisplayState, WalSyncDisplayState.corrupted);
    });

    test('miss with retryCount 0 -> waiting (never attempted)', () {
      expect(makeWal(status: WalStatus.miss, retryCount: 0).syncDisplayState, WalSyncDisplayState.waiting);
    });

    test('miss with 1..(max-1) retries -> retrying', () {
      for (var r = 1; r < walMaxAutoRetries; r++) {
        expect(makeWal(status: WalStatus.miss, retryCount: r).syncDisplayState, WalSyncDisplayState.retrying,
            reason: 'retryCount=$r');
      }
    });

    test('miss at/over max retries -> failed (needs manual retry)', () {
      expect(
          makeWal(status: WalStatus.miss, retryCount: walMaxAutoRetries).syncDisplayState, WalSyncDisplayState.failed);
      expect(makeWal(status: WalStatus.miss, retryCount: walMaxAutoRetries + 5).syncDisplayState,
          WalSyncDisplayState.failed);
    });

    test('inProgress -> waiting', () {
      expect(makeWal(status: WalStatus.inProgress).syncDisplayState, WalSyncDisplayState.waiting);
    });
  });

  group('Wal jobId/uploadedAt persistence', () {
    test('round-trips through toJson/fromJson', () {
      final w = makeWal(status: WalStatus.uploaded, jobId: 'job-xyz')..uploadedAt = 1700000123;
      final back = Wal.fromJson(w.toJson());
      expect(back.status, WalStatus.uploaded);
      expect(back.jobId, 'job-xyz');
      expect(back.uploadedAt, 1700000123);
    });

    test('legacy json without job fields defaults safely', () {
      final json = makeWal(status: WalStatus.miss).toJson()
        ..remove('job_id')
        ..remove('uploaded_at');
      final back = Wal.fromJson(json);
      expect(back.jobId, isNull);
      expect(back.uploadedAt, 0);
      expect(back.status, WalStatus.miss);
    });
  });
}
