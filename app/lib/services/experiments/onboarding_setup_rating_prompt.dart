import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// Gate for the onboarding "Setting up your Omi" page and its store-rating pre-prompt.
///
/// Evaluated on the client from the PostHog flag so the page can be switched on from the
/// backend without a release and stays invisible until then (store review never sees it).
/// Fail-closed: no analytics identity, a slow read or any error all mean "off", and the
/// onboarding flow is exactly what it was before this page existed.
abstract final class OnboardingSetupRatingPromptGate {
  /// PostHog flag key (project 302298). Registered in `config/feature-flags.yaml`.
  static const enabledFlag = 'onboarding-setup-rating-prompt';

  /// Local override for debug builds only: `--dart-define=OMI_ONBOARDING_SETUP_RATING_PROMPT=1`.
  /// A dart-define cannot be flipped on a built artifact and `kDebugMode` excludes every
  /// store build, so this never reaches a user.
  static const _debugOverride = String.fromEnvironment('OMI_ONBOARDING_SETUP_RATING_PROMPT');

  static bool get debugOverrideActive => kDebugMode && _debugOverride == '1';

  /// Whether to show the page. [readFlag] defaults to the analytics manager's flag read and is
  /// injectable for tests.
  static Future<bool> isEnabled({Future<bool> Function(String key)? readFlag}) async {
    if (debugOverrideActive) return true;
    try {
      return await (readFlag ?? AnalyticsManager().isFeatureEnabled)(enabledFlag);
    } catch (_) {
      return false;
    }
  }
}
