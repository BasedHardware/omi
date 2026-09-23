import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/notifications/notification_service.dart';
import 'package:omi/utils/logger.dart';

enum SyncHealthStatus {
  noDevice,
  healthy,
  stalled,
}

class SyncHealthEvaluation {
  final SyncHealthStatus status;
  final Duration? timeSinceLastSync;
  final bool alertDispatched;

  const SyncHealthEvaluation({
    required this.status,
    this.timeSinceLastSync,
    this.alertDispatched = false,
  });

  bool get isStalled => status == SyncHealthStatus.stalled;
}

/// Watches device synchronization health to prevent silent multi-day data loss (#15501).
///
/// Tracks the elapsed time since the last successful sync or audio ingestion.
/// If a paired device has not synced for over [defaultStallThreshold] (default 4 hours),
/// it triggers a user notification and flags the sync status as stalled so in-app
/// UI surfaces can prompt the user to check their device connection.
class SyncHealthWatchdog {
  SyncHealthWatchdog._();
  static final SyncHealthWatchdog instance = SyncHealthWatchdog._();

  static const Duration defaultStallThreshold = Duration(hours: 4);
  static const Duration alertCooldown = Duration(hours: 6);

  Timer? _timer;
  DateTime? _lastThrottledRecordTime;

  /// Records that sync or audio ingestion just succeeded.
  /// Throttled in-memory to at most once per minute to avoid hammering SharedPreferences.
  void recordSyncActivity({String source = 'unknown', DateTime? timestamp}) {
    final now = timestamp ?? DateTime.now();
    if (_lastThrottledRecordTime != null && now.difference(_lastThrottledRecordTime!) < const Duration(minutes: 1)) {
      return;
    }
    _lastThrottledRecordTime = now;
    SharedPreferencesUtil().lastSyncTimestamp = now.millisecondsSinceEpoch;
    Logger.debug('SyncHealthWatchdog: recorded sync activity from $source at $now');
  }

  /// Evaluates sync health for the current paired device.
  /// If [triggerNotification] is true and sync is stalled past the cooldown,
  /// fires a local notification alerting the user to prevent multi-day loss (#15501).
  SyncHealthEvaluation evaluateSyncHealth({
    DateTime? now,
    bool triggerNotification = true,
    Future<void> Function({
      required String title,
      required String body,
      int? notificationId,
      Map<String, String?>? payload,
    })? onTriggerNotification,
  }) {
    final currentTime = now ?? DateTime.now();
    final pairedDeviceId = SharedPreferencesUtil().btDevice.id;

    if (pairedDeviceId.isEmpty) {
      return const SyncHealthEvaluation(status: SyncHealthStatus.noDevice);
    }

    final lastSyncMillis = SharedPreferencesUtil().lastSyncTimestamp;
    if (lastSyncMillis == 0) {
      // First run or newly paired — seed with current timestamp to avoid false alarms.
      SharedPreferencesUtil().lastSyncTimestamp = currentTime.millisecondsSinceEpoch;
      return const SyncHealthEvaluation(
        status: SyncHealthStatus.healthy,
        timeSinceLastSync: Duration.zero,
      );
    }

    final lastSync = DateTime.fromMillisecondsSinceEpoch(lastSyncMillis);
    final elapsed = currentTime.difference(lastSync);

    if (elapsed < defaultStallThreshold) {
      return SyncHealthEvaluation(
        status: SyncHealthStatus.healthy,
        timeSinceLastSync: elapsed,
      );
    }

    // Stalled condition: elapsed exceeds stall threshold.
    bool alertSent = false;
    final syncAlertsEnabled = SharedPreferencesUtil().syncAlertsEnabled;

    if (syncAlertsEnabled && triggerNotification) {
      // Suppress audible shade notifications during quiet night hours (10 PM to 8 AM)
      final isQuietHours = currentTime.hour >= 22 || currentTime.hour < 8;
      if (!isQuietHours) {
        final lastAlertMillis = SharedPreferencesUtil().lastSyncAlertTimestamp;
        final elapsedSinceLastAlert = lastAlertMillis == 0
            ? const Duration(days: 999)
            : currentTime.difference(DateTime.fromMillisecondsSinceEpoch(lastAlertMillis));

        if (elapsedSinceLastAlert >= alertCooldown) {
          final hours = elapsed.inHours;
          const title = 'Omi Not Syncing';
          final body =
              'No recordings have synced from your Omi in over $hours hours. Open Omi to check device connection.';
          const payload = {'navigate_to': '/home', 'type': 'sync_stalled_alert'};

          if (onTriggerNotification != null) {
            onTriggerNotification(
              title: title,
              body: body,
              notificationId: 15501,
              payload: payload,
            );
          } else {
            NotificationService.instance.createNotification(
              title: title,
              body: body,
              notificationId: 15501,
              payload: payload,
            );
          }
          SharedPreferencesUtil().lastSyncAlertTimestamp = currentTime.millisecondsSinceEpoch;
          alertSent = true;
          Logger.warning('SyncHealthWatchdog: dispatched sync stall alert (elapsed: ${elapsed.inHours}h)');
        }
      }
    }

    return SyncHealthEvaluation(
      status: SyncHealthStatus.stalled,
      timeSinceLastSync: elapsed,
      alertDispatched: alertSent,
    );
  }

  /// Starts periodic health checks (e.g. every 30 minutes).
  void startWatchdog({Duration interval = const Duration(minutes: 30)}) {
    _timer?.cancel();
    evaluateSyncHealth();
    _timer = Timer.periodic(interval, (_) => evaluateSyncHealth());
  }

  void stopWatchdog() {
    _timer?.cancel();
    _timer = null;
  }

  @visibleForTesting
  bool get isRunning => _timer?.isActive ?? false;

  @visibleForTesting
  void resetForTesting() {
    _timer?.cancel();
    _timer = null;
    _lastThrottledRecordTime = null;
  }
}
