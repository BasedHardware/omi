import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/services/wals/sync_job_poller.dart';

/// Count-only observations. No identifiers, paths, content, or client sampling.
/// The PostHog ingestion keep-list is a separate operator-owned requirement.
class WalBacklogTelemetry {
  WalBacklogTelemetry({void Function(RegisteredEvent)? emit}) : _emit = emit ?? const TypedEvents().emit;

  final void Function(RegisteredEvent) _emit;
  final Map<PendantFramesDroppedReason, int> _drops = {};
  int _totalDrops = 0;

  void pendantFrameDropped({required String? retentionReason, required bool storageWriteBlocked}) {
    final reason = switch (retentionReason) {
      'disk_reserve' => PendantFramesDroppedReason.diskReserve,
      'disk_space_unknown' => PendantFramesDroppedReason.diskSpaceUnknown,
      'count_cap' when !storageWriteBlocked => PendantFramesDroppedReason.countCap,
      _ => PendantFramesDroppedReason.storageWriteFailed,
    };
    _drops.update(reason, (n) => n + 1, ifAbsent: () => 1);
    _totalDrops++;
    DebugLogManager.logWarning('LocalWalSync: pendant frame dropped, storage admission blocked', {
      'dropped_count': _totalDrops,
    });
  }

  /// Called synchronously at the start of a flush: arrivals during its I/O
  /// belong to the next window. Empty windows emit nothing.
  void flushPendantDrops() {
    final window = Map.of(_drops);
    _drops.clear();
    for (final entry in window.entries) {
      _safeEmit(PendantFramesDropped(count: entry.value, reason: entry.key));
    }
  }

  void clearUserData() {
    _drops.clear();
    _totalDrops = 0;
  }

  /// Only anomalous passes emit: backlog beyond one minute's poll budget,
  /// transient/throttle results, or missing jobs awaiting confirmation.
  /// Routine success, nonterminal status and budget-only wakes stay silent.
  void reconcilePass({
    required int backlogJobs,
    required int polledJobs,
    required int transientJobs,
    required int throttledJobs,
    int missingConfirmationJobs = 0,
  }) {
    if (polledJobs == 0) return;
    if (backlogJobs <= SyncJobPoller.maxRequestsPerMinute &&
        transientJobs == 0 &&
        throttledJobs == 0 &&
        missingConfirmationJobs == 0) return;
    _safeEmit(WalReconcilePollSummary(
      backlogJobs: backlogJobs,
      polledJobs: polledJobs,
      transientJobs: transientJobs,
      throttledJobs: throttledJobs,
      missingConfirmationJobs: missingConfirmationJobs,
      locallyDeferredJobs: backlogJobs - polledJobs,
    ));
  }

  void _safeEmit(RegisteredEvent event) {
    try {
      _emit(event);
    } catch (_) {
      // Observability must never change capture, custody, or polling.
    }
  }
}
