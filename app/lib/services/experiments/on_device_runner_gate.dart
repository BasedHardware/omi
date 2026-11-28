import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// Operational kill switch for the on-device runner: the queue that transcribes phone-only audio
/// (drained pendant audio for on-device STT users, and overflow audio for users who opted in),
/// its model setup, schedule, queue banner, provenance and settings, and the Apple SpeechAnalyzer
/// engine path. On for everyone unless PostHog `mobile-on-device-runner-disabled` is true
/// (ops_kill, owner free-tier-on-device; ruling David 2026-11-27, SCA-5264). A missing flag, or a
/// read that errors or times out, keeps it on. A failed refresh keeps the last answer this app
/// saw, so a kill that reached the phone stays in force while it is offline.
///
/// The at-cap choice sheet and the other storefront surfaces stay on [OnDeviceOverflowGate]
/// (`mobile-on-device-overflow`), which is held for the at-cap product call.
abstract final class OnDeviceRunnerGate {
  static const killSwitchFlag = 'mobile-on-device-runner-disabled';
  static const refreshInterval = Duration(minutes: 10);

  static DateTime? _lastRefresh;
  static bool _lastKnownKilled = false;

  /// Tests pin the answer instead of reading analytics (null reads the flag).
  @visibleForTesting
  static bool? debugForce;

  @visibleForTesting
  static void debugReset() {
    _lastRefresh = null;
    _lastKnownKilled = false;
    debugForce = null;
  }

  static Future<bool> enabled({
    Future<bool> Function(String key)? readFlag,
    Future<bool> Function()? reloadFlags,
    DateTime Function()? now,
  }) async {
    final forced = debugForce;
    if (forced != null) return forced;
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
      _lastKnownKilled =
          await (readFlag ?? AnalyticsManager().isFeatureEnabled)(killSwitchFlag).timeout(const Duration(seconds: 1));
    } catch (_) {
      // Keep the last answer: a kill that reached this phone stays in force offline.
    }
    return !_lastKnownKilled;
  }
}
