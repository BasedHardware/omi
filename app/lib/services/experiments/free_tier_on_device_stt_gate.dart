import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// Operational kill switch for live on-device transcription past the cloud cap (S17).
/// False/missing/offline/error keeps it on (ops_kill, owner free-tier-on-device); true returns
/// new sockets to today's Omi socket, where the server holds the audio at the cap.
///
/// Flag reads come from the analytics adapter's cached map, so the gate refreshes that map at
/// most every [refreshInterval] (bounded by one second) before reading: a flip reaches running
/// apps within minutes, not at the next unrelated refresh.
abstract final class FreeTierOnDeviceSttGate {
  static const killSwitchFlag = 'mobile-free-tier-on-device-stt-disabled';
  static const refreshInterval = Duration(minutes: 10);

  static DateTime? _lastRefresh;

  @visibleForTesting
  static void debugReset() => _lastRefresh = null;

  static Future<bool> killed({
    Future<bool> Function(String key)? readFlag,
    Future<bool> Function()? reloadFlags,
    DateTime Function()? now,
  }) async {
    final at = (now ?? DateTime.now)();
    final last = _lastRefresh;
    if (last == null || at.difference(last) >= refreshInterval) {
      _lastRefresh = at;
      try {
        await (reloadFlags ?? AnalyticsManager().reloadFeatureFlags)().timeout(const Duration(seconds: 1));
      } catch (_) {
        // Keep the cached answer.
      }
    }
    try {
      return await (readFlag ?? AnalyticsManager().isFeatureEnabled)(killSwitchFlag)
          .timeout(const Duration(seconds: 1));
    } catch (_) {
      return false;
    }
  }
}
