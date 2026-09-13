import 'package:omi/models/sync_state.dart';
import 'package:omi/utils/sync/offline_processing_display.dart';

/// Builds the secondary line under the offline sync status card.
class SyncCardProgressLine {
  const SyncCardProgressLine._();

  static String? subtitle({
    required SyncPhase phase,
    required int? currentFile,
    required int? totalFiles,
    required String Function(int processed, int total) counterLabel,
    String? speedSuffix,
  }) {
    if (phase != SyncPhase.downloadingFromDevice && phase != SyncPhase.uploadingToCloud) {
      return speedSuffix;
    }

    final normalized = OfflineProcessingDisplay.normalizeCounts(
      current: currentFile ?? 0,
      total: totalFiles ?? 0,
    );
    if (normalized.total <= 0) {
      return speedSuffix;
    }

    final percent = OfflineProcessingDisplay.completionPercent(
      processed: normalized.processed,
      total: normalized.total,
    );
    final counter = counterLabel(normalized.processed, normalized.total);
    final parts = <String>['$counter · $percent%'];
    if (speedSuffix != null && speedSuffix.isNotEmpty) {
      parts.add(speedSuffix);
    }
    return parts.join(' · ');
  }

  static String? serverProcessingSubtitle({
    required int processed,
    required int total,
    required String Function(int processed, int total) counterLabel,
  }) {
    final normalized = OfflineProcessingDisplay.normalizeCounts(current: processed, total: total);
    if (normalized.total <= 0) {
      return null;
    }
    final percent = OfflineProcessingDisplay.completionPercent(
      processed: normalized.processed,
      total: normalized.total,
    );
    return '${counterLabel(normalized.processed, normalized.total)} · $percent%';
  }
}
