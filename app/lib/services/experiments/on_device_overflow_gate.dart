import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// Client presentation gate for on-device transcription once live hours run out (the at-cap
/// choice sheet, model setup, schedule, queue banner, provenance and settings). Off leaves every
/// existing surface exactly as it is.
///
/// Evaluated from the PostHog flag `mobile-on-device-overflow`, registered in
/// `config/feature-flags.yaml`. Fail-closed: no analytics identity or a failed read means off.
/// Lifecycle: rollout; owner: dazheng; review-by: 2026-11-13; default off.
abstract final class OnDeviceOverflowGate {
  static const enabledFlag = 'mobile-on-device-overflow';

  /// Debug-build override: `--dart-define=OMI_ON_DEVICE_OVERFLOW=true`.
  static const _debugForce = bool.fromEnvironment('OMI_ON_DEVICE_OVERFLOW');

  static bool get debugOverrideActive => kDebugMode && _debugForce;

  static Future<bool> read({Future<bool> Function(String key)? readFlag}) async {
    if (debugOverrideActive) return true;
    try {
      return await (readFlag ?? AnalyticsManager().isFeatureEnabled)(enabledFlag);
    } catch (_) {
      return false;
    }
  }
}
