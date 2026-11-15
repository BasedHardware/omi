import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

enum SyncHealthStatus { noDevice, healthy, stalled }

class SyncHealthEvaluation {
  const SyncHealthEvaluation({
    required this.status,
    this.timeSinceLastSync,
    this.alertDispatched = false,
  });

  final SyncHealthStatus status;
  final Duration? timeSinceLastSync;
  final bool alertDispatched;

  bool get isStalled => status == SyncHealthStatus.stalled;
}

/// Watches the paired pendant's sync pipeline to prevent silent multi-day
/// recording loss (#15501).
///
/// "Sync activity" is any proof that recordings are moving: BLE audio bytes
/// arriving from the pendant, a batch recording finalized on the phone, a WAL
/// accepted by the server, or the pendant (re)connecting. While any of those
/// flow, audio is either already safe on the phone or on the server, so the
/// upload drains (oldest-first, Retry-After, quiet refusals) own recovery.
/// Only a long silence across every signal is a stall the user must hear
/// about, because that is when a worn pendant's audio stops arriving with no
/// in-app surface to say so.
///
/// The threshold is a full day, not hours: the wedge monitor already surfaces
/// acute link stalls (minutes) and slow-burn upload stalls (2h with a backlog)
/// in-app; this alert is the out-of-app last resort. Anything shorter would
/// fire for the longest normal daily gap — a pendant charging overnight — and
/// a disconnect push is ruled out entirely (#3328). A day of total silence is
/// also far inside the multi-day losses users reported before noticing.
class SyncHealthWatchdog {
  SyncHealthWatchdog._() : _nowOverride = null;
  SyncHealthWatchdog.forTesting({DateTime Function()? now}) : _nowOverride = now;
  static final SyncHealthWatchdog instance = SyncHealthWatchdog._();

  /// Total silence across every activity signal before a stall is declared.
  /// Longer than an overnight charge gap (~8–12h); shorter than the reported
  /// multi-day silent losses.
  static const Duration stallThreshold = Duration(hours: 24);

  /// At most one reminder per day while a stall persists.
  static const Duration alertCooldown = Duration(hours: 24);

  /// No shade notifications at night (22:00–08:00 local). A suppressed alert
  /// does not advance the cooldown stamp, so it fires once quiet hours end.
  static const int quietHoursStart = 22;
  static const int quietHoursEnd = 8;

  /// The watchdog only evaluates while the app process runs (the capture
  /// foreground service keeps it alive on Android); 30 minutes is soon
  /// enough against a 24h threshold and cheap against a stopped process.
  static const Duration defaultCheckInterval = Duration(minutes: 30);

  /// In-memory activity throttle: BLE audio arrives many times a second, and
  /// the persisted timestamp only needs minute resolution.
  static const Duration activityThrottle = Duration(minutes: 1);

  static const String syncStallAlertType = 'sync_stalled_alert';
  static const int syncStallNotificationId = 15501;

  final DateTime Function()? _nowOverride;
  Timer? _timer;
  DateTime? _lastRecordedActivityAt;
  SyncHealthEvaluation? _lastEvaluation;

  /// Wired by the owner (DeviceProvider): every evaluation passes through, so
  /// it can mirror the stall into the capture wedge monitor's Needs attention
  /// row and rebuild listeners. Called only from the watchdog's own turns.
  void Function(SyncHealthEvaluation evaluation)? onEvaluation;

  /// The latest evaluation, null before the first one.
  SyncHealthEvaluation? get lastEvaluation => _lastEvaluation;

  /// Records that recordings just moved through some part of the pipeline.
  /// Throttled in memory to at most one persist per [activityThrottle].
  void recordSyncActivity({String source = 'unknown', DateTime? timestamp}) {
    final now = timestamp ?? _now();
    final last = _lastRecordedActivityAt;
    // A negative difference (a stale source) is also inside the window, so the
    // persisted timestamp can never move backwards.
    if (last != null && now.difference(last) < activityThrottle) return;
    _lastRecordedActivityAt = now;
    SharedPreferencesUtil().lastSyncTimestamp = now.millisecondsSinceEpoch;
    Logger.debug('SyncHealthWatchdog: activity from $source');
  }

  /// Evaluates the paired pendant's sync health. A stall past the cooldown
  /// during daytime dispatches the local notification ([onTriggerNotification]
  /// lets tests capture it; production leaves it null).
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
    final currentTime = now ?? _now();
    final paired = SharedPreferencesUtil().btDevice;

    // Only pendant capture devices are under contract: their audio must keep
    // flowing while worn. Other device types (watch, glasses) sync on their
    // own cadence, so silence there is not a stall this alert owns.
    final isPendant =
        paired.id.isNotEmpty && (paired.type == DeviceType.omi || paired.type == DeviceType.friendPendant);
    if (!isPendant) {
      return _publish(const SyncHealthEvaluation(status: SyncHealthStatus.noDevice));
    }

    final lastSyncMillis = SharedPreferencesUtil().lastSyncTimestamp;
    if (lastSyncMillis == 0) {
      // First run or freshly paired: seed with now so the app update itself
      // cannot raise a false alarm.
      SharedPreferencesUtil().lastSyncTimestamp = currentTime.millisecondsSinceEpoch;
      return _publish(
        const SyncHealthEvaluation(status: SyncHealthStatus.healthy, timeSinceLastSync: Duration.zero),
      );
    }

    final elapsed = currentTime.difference(DateTime.fromMillisecondsSinceEpoch(lastSyncMillis));
    if (elapsed < stallThreshold) {
      return _publish(SyncHealthEvaluation(status: SyncHealthStatus.healthy, timeSinceLastSync: elapsed));
    }

    bool alertSent = false;
    if (triggerNotification && SharedPreferencesUtil().syncAlertsEnabled && !_isQuietHours(currentTime)) {
      final lastAlertMillis = SharedPreferencesUtil().lastSyncAlertTimestamp;
      final sinceAlert = lastAlertMillis == 0
          ? const Duration(days: 999)
          : currentTime.difference(DateTime.fromMillisecondsSinceEpoch(lastAlertMillis));
      if (sinceAlert >= alertCooldown) {
        final hours = elapsed.inHours;
        final title = _alertTitle();
        final body = _alertBody(hours);
        const payload = {'navigate_to': '/settings/device', 'type': syncStallAlertType};
        if (onTriggerNotification != null) {
          onTriggerNotification(title: title, body: body, notificationId: syncStallNotificationId, payload: payload);
        } else {
          unawaited(
            NotificationService.instance.createNotification(
              title: title,
              body: body,
              notificationId: syncStallNotificationId,
              payload: payload,
            ),
          );
        }
        SharedPreferencesUtil().lastSyncAlertTimestamp = currentTime.millisecondsSinceEpoch;
        alertSent = true;
        Logger.warning('SyncHealthWatchdog: stall alert dispatched (${elapsed.inHours}h since last activity)');
      }
    }

    return _publish(
      SyncHealthEvaluation(status: SyncHealthStatus.stalled, timeSinceLastSync: elapsed, alertDispatched: alertSent),
    );
  }

  /// Starts the periodic checks and evaluates immediately. Re-starting is
  /// idempotent.
  void startWatchdog({Duration interval = defaultCheckInterval}) {
    _timer?.cancel();
    evaluateSyncHealth();
    _timer = Timer.periodic(interval, (_) => evaluateSyncHealth());
  }

  void stopWatchdog() {
    _timer?.cancel();
    _timer = null;
  }

  SyncHealthEvaluation _publish(SyncHealthEvaluation evaluation) {
    _lastEvaluation = evaluation;
    onEvaluation?.call(evaluation);
    return evaluation;
  }

  bool _isQuietHours(DateTime at) => at.hour >= quietHoursStart || at.hour < quietHoursEnd;

  DateTime _now() => _nowOverride?.call() ?? DateTime.now();

  // Localized when a context is mounted (the app is running), English
  // fallbacks otherwise — same shape as the fall notification.
  String _alertTitle() => globalNavigatorKey.currentContext?.l10n.syncStallAlertTitle ?? 'Omi Not Syncing';

  String _alertBody(int hours) =>
      globalNavigatorKey.currentContext?.l10n.syncStallAlertBody(hours) ??
      'No recordings have synced from your Omi in over $hours hours. '
          'Open Omi to check your device connection.';

  @visibleForTesting
  bool get isRunning => _timer?.isActive ?? false;

  @visibleForTesting
  void resetForTesting() {
    _timer?.cancel();
    _timer = null;
    _lastRecordedActivityAt = null;
    _lastEvaluation = null;
  }
}
