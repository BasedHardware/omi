import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/debug_log_manager.dart';

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

  /// One summary per pass that actually polled, not per pending job or wake.
  /// The shared poller bounds these to at most 18 per minute. Local deferrals
  /// remain distinct from actual fetch results classified as transient.
  void reconcilePass({
    required int backlogJobs,
    required int polledJobs,
    required int transientJobs,
    required int throttledJobs,
  }) {
    if (polledJobs == 0) return;
    _safeEmit(WalReconcilePollSummary(
      backlogJobs: backlogJobs,
      polledJobs: polledJobs,
      transientJobs: transientJobs,
      throttledJobs: throttledJobs,
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
