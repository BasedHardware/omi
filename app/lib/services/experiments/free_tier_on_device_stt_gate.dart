import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// Operational kill switch for live on-device transcription past the cloud cap (S17).
/// A missing flag, or a read that errors or times out, keeps it on (ops_kill, owner
/// free-tier-on-device); true returns new sockets to today's Omi socket, where the server holds
/// the audio at the cap. A failed refresh keeps the last answer this app saw, so a kill that
/// reached the phone stays in force while it is offline.
///
/// Flag reads come from the analytics adapter's cached map, so the gate refreshes that map at
/// most every [refreshInterval] (bounded by one second) before reading: a flip reaches running
/// apps within minutes, not at the next unrelated refresh.
abstract final class FreeTierOnDeviceSttGate {
  static const killSwitchFlag = 'mobile-free-tier-on-device-stt-disabled';
  static const refreshInterval = Duration(minutes: 10);

  static DateTime? _lastRefresh;

  /// The last answer [killed] returned, for synchronous eligibility checks (false until one read).
  static bool get lastKnownKilled => _lastKnownKilled;
  static bool _lastKnownKilled = false;

  @visibleForTesting
  static set debugLastKnownKilled(bool value) => _lastKnownKilled = value;

  @visibleForTesting
  static void debugReset() {
    _lastRefresh = null;
    _lastKnownKilled = false;
  }

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
      return _lastKnownKilled =
          await (readFlag ?? AnalyticsManager().isFeatureEnabled)(killSwitchFlag).timeout(const Duration(seconds: 1));
    } catch (_) {
      return false;
    }
  }
}
