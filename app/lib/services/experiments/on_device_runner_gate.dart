import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

/// Operational kill switch for the on-device runner: the queue that transcribes phone-only audio
/// (drained pendant audio for on-device STT users, and overflow audio for users who opted in),
/// its model setup, schedule, queue banner, provenance and settings, and the Apple SpeechAnalyzer
/// engine path. On for everyone unless PostHog `mobile-on-device-runner-disabled` is true
/// (ops_kill, owner free-tier-on-device; ruling David 2026-11-27, SCA-5264).
///
/// Only an authoritative flag answer changes the state. A missing answer (no settled identity,
/// tracking off, offline, timeout) keeps the last answer this phone saw, which is persisted so a
/// kill that reached the phone also holds in the Android background worker and across launches.
///
/// The at-cap choice sheet and the other storefront surfaces stay on [OnDeviceOverflowGate]
/// (`mobile-on-device-overflow`), which is held for the at-cap product call.
abstract final class OnDeviceRunnerGate {
  static const killSwitchFlag = 'mobile-on-device-runner-disabled';
  static const refreshInterval = Duration(minutes: 10);
  static const _killedPref = 'onDeviceRunnerKilled';

  static DateTime? _lastRefresh;
  static bool? _lastKnownKilled;

  /// Tests pin the answer instead of reading analytics (null reads the flag).
  @visibleForTesting
  static bool? debugForce;

  @visibleForTesting
  static void debugReset() {
    _lastRefresh = null;
    _lastKnownKilled = null;
    debugForce = null;
  }

  static bool _storedKilled() {
    try {
      return SharedPreferencesUtil().getBool(_killedPref);
    } catch (_) {
      return false;
    }
  }

  static Future<bool> enabled({
    Future<bool?> Function(String key)? readFlag,
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
    bool? answer;
    try {
      answer = await (readFlag ??
              (key) => AnalyticsManager().resolvedBooleanFeatureFlag(key, refresh: false))(killSwitchFlag)
          .timeout(const Duration(seconds: 1));
    } catch (_) {
      answer = null;
    }
    if (answer != null && answer != _lastKnownKilled) {
      try {
        await SharedPreferencesUtil().saveBool(_killedPref, answer);
      } catch (_) {
        // The in-memory answer still applies to this process.
      }
    }
    final killed = answer ?? _lastKnownKilled ?? _storedKilled();
    _lastKnownKilled = killed;
    return !killed;
  }
}
