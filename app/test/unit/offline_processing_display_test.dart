import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/sync/offline_processing_display.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';
import 'package:omi/models/sync_state.dart';

void main() {
  group('OfflineProcessingDisplay', () {
    test('completion grows 0 → 100 for processed/total', () {
      expect(OfflineProcessingDisplay.completionPercent(processed: 0, total: 100), 0);
      expect(OfflineProcessingDisplay.completionPercent(processed: 1, total: 100), 1);
      expect(OfflineProcessingDisplay.completionPercent(processed: 25, total: 100), 25);
      expect(OfflineProcessingDisplay.completionPercent(processed: 50, total: 100), 50);
      expect(OfflineProcessingDisplay.completionPercent(processed: 100, total: 100), 100);
    });

    test('legacy negative current is treated as remaining offset when total > 1', () {
      final counts = OfflineProcessingDisplay.normalizeCounts(current: -75, total: 100);
      expect(counts.processed, 25);
      expect(counts.total, 100);
      expect(OfflineProcessingDisplay.completionPercent(processed: counts.processed, total: counts.total), 25);
    });

    test('clamps overflow and zero total', () {
      expect(OfflineProcessingDisplay.normalizeCounts(current: 150, total: 100).processed, 100);
      expect(OfflineProcessingDisplay.normalizeCounts(current: 5, total: 0).total, 0);
    });

    test('serverJobCounts scopes to tracked upload batch', () {
      Wal wal(int timerStart, WalStatus status) =>
          Wal(timerStart: timerStart, codec: BleAudioCodec.pcm16, seconds: 1, status: status);

      final partialDrain = OfflineProcessingDisplay.serverJobCounts(
        trackedUploadedWalIds: {'phone_1', 'phone_2'},
        wals: [wal(1, WalStatus.uploaded), wal(2, WalStatus.uploaded), wal(3, WalStatus.miss), wal(4, WalStatus.miss)],
      );
      expect(partialDrain, (processed: 0, total: 2));

      final reconciled = OfflineProcessingDisplay.serverJobCounts(
        trackedUploadedWalIds: {'phone_1', 'phone_2', 'phone_3'},
        wals: [wal(1, WalStatus.synced), wal(2, WalStatus.uploaded), wal(3, WalStatus.uploaded)],
      );
      expect(reconciled, (processed: 1, total: 3));

      final laterSync = OfflineProcessingDisplay.serverJobCounts(
        trackedUploadedWalIds: {'phone_2'},
        wals: [wal(1, WalStatus.uploaded), wal(2, WalStatus.uploaded)],
      );
      expect(laterSync, (processed: 0, total: 1));
    });
  });

  group('serverJobSeconds', () {
    Wal wal(int timerStart, int seconds, WalStatus status) =>
        Wal(timerStart: timerStart, codec: BleAudioCodec.pcm16, seconds: seconds, status: status);

    test('weighs the tracked batch by audio length', () {
      final job = OfflineProcessingDisplay.serverJobSeconds(
        trackedUploadedWalIds: {'phone_1', 'phone_2', 'phone_3'},
        wals: [wal(1, 600, WalStatus.synced), wal(2, 60, WalStatus.uploaded), wal(3, 75, WalStatus.uploaded)],
      );
      expect(job, (doneSeconds: 600, totalSeconds: 735, tracked: true));
    });

    test('a device copy still on the card does not count its uploaded phone twin as done', () {
      final job = OfflineProcessingDisplay.serverJobSeconds(
        trackedUploadedWalIds: {'phone_1'},
        wals: [
          Wal(
              timerStart: 1,
              codec: BleAudioCodec.opus,
              seconds: 75,
              status: WalStatus.miss,
              storage: WalStorage.sdcard),
          Wal(
              timerStart: 1,
              codec: BleAudioCodec.opus,
              seconds: 75,
              status: WalStatus.uploaded,
              storage: WalStorage.disk),
        ],
      );
      expect(job, (doneSeconds: 0, totalSeconds: 75, tracked: true));
    });

    test('untracked backlog reports its length without claiming progress', () {
      final job = OfflineProcessingDisplay.serverJobSeconds(
        trackedUploadedWalIds: const {},
        wals: [wal(1, 75, WalStatus.uploaded), wal(2, 75, WalStatus.synced)],
      );
      expect(job, (doneSeconds: 0, totalSeconds: 75, tracked: false));
    });
  });

  group('SyncRunTracker', () {
    Wal wal(int timerStart, int seconds, WalStatus status, WalStorage storage) => Wal(
          timerStart: timerStart,
          codec: BleAudioCodec.opus,
          seconds: seconds,
          status: status,
          storage: storage,
        );

    test('upload progress is the seconds of the snapshot now uploaded, and the total holds still', () {
      final long = wal(1, 600, WalStatus.miss, WalStorage.disk);
      final short = wal(2, 75, WalStatus.miss, WalStorage.disk);
      final wals = [long, short];
      final tracker = SyncRunTracker();
      const uploading = SyncState(status: SyncStatus.syncing, phase: SyncPhase.uploadingToCloud);

      final start = tracker.update(uploading, wals)!;
      expect((start.step, start.doneSeconds, start.totalSeconds), (SyncStep.upload, 0, 675));
      expect(tracker.runSeconds, 675);

      long.status = WalStatus.uploaded;
      final mid = tracker.update(uploading, wals)!;
      expect((mid.doneSeconds, mid.totalSeconds), (600, 675));
      expect(tracker.runSeconds, 675, reason: 'the run total must not shrink as recordings finish');
    });

    test('device download applies the byte fraction to the on-device seconds', () {
      final wals = [
        wal(1, 1080, WalStatus.miss, WalStorage.sdcard),
        wal(2, 30, WalStatus.miss, WalStorage.disk),
      ];
      final tracker = SyncRunTracker();
      final step = tracker.update(
        const SyncState(status: SyncStatus.syncing, phase: SyncPhase.downloadingFromDevice, progress: 0.5),
        wals,
      )!;
      expect((step.step, step.doneSeconds, step.totalSeconds), (SyncStep.download, 540, 1080));
      expect(tracker.runSeconds, 1110);
    });

    test('live-capture uploads before the device drain keep the bar on the device step, and it never rewinds', () {
      final onDevice = wal(1, 600, WalStatus.miss, WalStorage.sdcard);
      final live = wal(2, 75, WalStatus.miss, WalStorage.disk);
      final wals = [onDevice, live];
      final tracker = SyncRunTracker();

      final preDrain =
          tracker.update(const SyncState(status: SyncStatus.syncing, phase: SyncPhase.uploadingToCloud), wals)!;
      expect((preDrain.step, preDrain.barStep), (SyncStep.upload, SyncStep.download));

      final drain = tracker.update(
        const SyncState(status: SyncStatus.syncing, phase: SyncPhase.downloadingFromDevice, progress: 0.5),
        wals,
      )!;
      expect((drain.barStep, drain.doneSeconds), (SyncStep.download, 300));

      // The device restarts its fraction for the next file; the count holds.
      final restarted = tracker.update(
        const SyncState(status: SyncStatus.syncing, phase: SyncPhase.downloadingFromDevice, progress: 0.1),
        wals,
      )!;
      expect(restarted.doneSeconds, 300);

      onDevice.status = WalStatus.synced;
      final upload =
          tracker.update(const SyncState(status: SyncStatus.syncing, phase: SyncPhase.uploadingToCloud), wals)!;
      expect(upload.barStep, SyncStep.upload);
    });

    test('idle resets, and terminal recordings never count as work', () {
      final tracker = SyncRunTracker();
      expect(tracker.update(const SyncState(), [wal(1, 60, WalStatus.miss, WalStorage.disk)]), isNull);
      expect(tracker.runSeconds, isNull);

      final tooOld = wal(2, 900, WalStatus.outsideRecoveryWindow, WalStorage.disk);
      tracker.update(const SyncState(status: SyncStatus.syncing, phase: SyncPhase.uploadingToCloud), [tooOld]);
      expect(tracker.runSeconds, 0);
    });
  });

  test('SyncPipelineAmounts sorts unsynced audio by where it sits', () {
    final onDevice = Wal(
      timerStart: 1,
      codec: BleAudioCodec.opus,
      seconds: 360,
      status: WalStatus.miss,
      storage: WalStorage.sdcard,
    )
      ..storageTotalBytes = 3000000
      ..storageOffset = 1000000;
    final amounts = SyncPipelineAmounts.of([
      onDevice,
      Wal(timerStart: 2, codec: BleAudioCodec.opus, seconds: 720, status: WalStatus.miss, storage: WalStorage.disk),
      Wal(timerStart: 3, codec: BleAudioCodec.opus, seconds: 2460, status: WalStatus.uploaded),
      Wal(timerStart: 4, codec: BleAudioCodec.opus, seconds: 99, status: WalStatus.synced),
    ]);
    expect(amounts.onDeviceSeconds, 360);
    expect(amounts.onDeviceBytes, 2000000);
    expect(amounts.onPhoneSeconds, 720);
    expect(amounts.processingSeconds, 2460);
  });
}
