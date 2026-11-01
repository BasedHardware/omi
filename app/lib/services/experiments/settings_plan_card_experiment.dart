import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// The arms of the Settings plan card A/B (`settings-plan-card`).
enum SettingsPlanCardArm {
  /// The Plan & Usage row with the minutes meter and a full-width Upgrade under it.
  control('control'),

  /// A plan card: the plan name large, the minutes meter, then a full-width Upgrade.
  card('card');

  const SettingsPlanCardArm(this.wire);

  final String wire;

  static SettingsPlanCardArm? fromWire(String? value) {
    for (final arm in values) {
      if (arm.wire == value) return arm;
    }
    return null;
  }
}

/// Which plan section Free and Plus readers see on the Settings sheet.
///
/// Lifecycle: experiment; owner: yinka; review-by: 2026-11-15; default control.
/// Pre-registration: product/experiments/settings-plan-card.md.
///
/// Fail-closed: no identity, a slow read or an unknown variant all mean control, and such a
/// fallback is never recorded as an exposure, so only readers PostHog actually assigned are counted.
abstract final class SettingsPlanCardExperiment {
  static const enabledFlag = 'settings-plan-card';

  /// Debug builds can force an arm: `--dart-define=OMI_SETTINGS_PLAN_CARD=card`.
  static const _debugArm = String.fromEnvironment('OMI_SETTINGS_PLAN_CARD');

  static SettingsPlanCardArm? _cached;
  static bool _cachedFromFlag = false;
  static String? _cachedIdentity;

  /// The arm cached for the current identity, if [resolve] already ran; lets the sheet draw the
  /// right section on its first frame after the first open.
  static SettingsPlanCardArm? get cached => _cachedIdentity == AnalyticsManager().settledDistinctId ? _cached : null;

  static Future<SettingsPlanCardArm> resolve({Future<String?> Function(String key)? readVariant}) async {
    if (kDebugMode && _debugArm.isNotEmpty) {
      return SettingsPlanCardArm.fromWire(_debugArm) ?? SettingsPlanCardArm.control;
    }
    final identity = AnalyticsManager().settledDistinctId;
    if (readVariant == null && _cached != null && _cachedIdentity == identity) return _cached!;
    SettingsPlanCardArm? arm;
    try {
      final variant = await (readVariant ?? AnalyticsManager().getFeatureFlagVariant)(enabledFlag)
          .timeout(const Duration(seconds: 2));
      arm = SettingsPlanCardArm.fromWire(variant);
    } catch (_) {
      arm = null;
    }
    _cachedFromFlag = arm != null;
    _cached = arm ?? SettingsPlanCardArm.control;
    _cachedIdentity = identity;
    return _cached!;
  }

  /// Records the exposure PostHog Experiments counts (`$feature_flag_called`, once per identity and
  /// arm) at the moment the section is drawn for a Free or Plus reader. Skipped for a fallback arm.
  static bool recordExposure(SettingsPlanCardArm arm, {bool Function(String key, String variant)? record}) {
    if (!_cachedFromFlag && record == null) return false;
    return (record ?? AnalyticsManager().recordFeatureFlagExposure)(enabledFlag, arm.wire);
  }

  @visibleForTesting
  static void resetForTesting() {
    _cached = null;
    _cachedFromFlag = false;
    _cachedIdentity = null;
  }
}
