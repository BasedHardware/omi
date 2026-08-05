import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/sync_continuation_policy.dart';

void main() {
  group('decideScreenLockedSyncContinuation (#7221)', () {
    test('defers when there is no cloud work', () {
      expect(
        decideScreenLockedSyncContinuation(autoUploadEnabled: true, hasMissLocalWals: false, hasUploadedWals: false),
        SyncContinuationAction.deferToForeground,
      );
    });

    test('runs grace when miss WALs are ready and auto-upload is on', () {
      expect(
        decideScreenLockedSyncContinuation(autoUploadEnabled: true, hasMissLocalWals: true, hasUploadedWals: false),
        SyncContinuationAction.runCloudGracePass,
      );
    });

    test('does not upload miss WALs when auto-upload is off', () {
      expect(
        decideScreenLockedSyncContinuation(autoUploadEnabled: false, hasMissLocalWals: true, hasUploadedWals: false),
        SyncContinuationAction.deferToForeground,
      );
    });

    test('always reconciles uploaded WALs even when auto-upload is off', () {
      expect(
        decideScreenLockedSyncContinuation(autoUploadEnabled: false, hasMissLocalWals: false, hasUploadedWals: true),
        SyncContinuationAction.runCloudGracePass,
      );
    });

    test('grace max batches stays bounded for iOS background time', () {
      expect(kScreenLockedCloudGraceMaxBatches, greaterThan(0));
      expect(kScreenLockedCloudGraceMaxBatches, lessThanOrEqualTo(5));
    });
  });
}
