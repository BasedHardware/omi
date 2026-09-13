import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/sync/offline_processing_display.dart';
import 'package:omi/utils/sync/sync_card_progress_line.dart';
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
      Wal wal(int timerStart, WalStatus status) => Wal(
            timerStart: timerStart,
            codec: BleAudioCodec.pcm16,
            seconds: 1,
            status: status,
          );

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

  group('SyncCardProgressLine', () {
    test('upload phase shows processed/total and completion percent', () {
      final line = SyncCardProgressLine.subtitle(
        phase: SyncPhase.uploadingToCloud,
        currentFile: 25,
        totalFiles: 100,
        counterLabel: (p, t) => '$p/$t',
      );
      expect(line, '25/100 · 25%');
    });

    test('does not invert percent at start of batch', () {
      final line = SyncCardProgressLine.subtitle(
        phase: SyncPhase.uploadingToCloud,
        currentFile: 0,
        totalFiles: 100,
        counterLabel: (p, t) => '$p/$t',
      );
      expect(line, '0/100 · 0%');
    });

    test('device download uses 1-based active index as in-progress count', () {
      final line = SyncCardProgressLine.subtitle(
        phase: SyncPhase.downloadingFromDevice,
        currentFile: 1,
        totalFiles: 10,
        counterLabel: (p, t) => '$p/$t',
      );
      expect(line, '0/10 · 0%');
    });
  });
}
