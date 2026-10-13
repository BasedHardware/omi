import 'package:flutter/foundation.dart';

import 'package:posthog_flutter/posthog_flutter.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

/// How first-run onboarding ends, after "Connect your Omi".
enum OnboardingEnding {
  /// Control: the guided voice introduction, then the flag-gated "Setting up your Omi" page and
  /// the "You're all set" screen, exactly as before the activation flow existed.
  voiceIntro('control'),

  /// Treatment: the activation flow (Omi at work, a first real conversation, its summary and
  /// to-dos, the paywall and the rating ask).
  activation('activation');

  const OnboardingEnding(this.wireName);

  /// The value persisted per account and accepted by the debug override.
  final String wireName;

  static OnboardingEnding? fromWire(String value) {
    for (final ending in values) {
      if (ending.wireName == value) return ending;
    }
    return null;
  }
}

/// A/B switch between the old onboarding ending (control) and the activation flow (treatment).
///
/// Evaluated on the client from the PostHog flag. Works with a plain boolean flag (on = treatment)
/// and with a PostHog experiment's multivariate flag (`test`, `treatment` or `activation` =
/// treatment; `control` and any other variant = control). The variant is read explicitly because
/// `isFeatureEnabled` is also true for the `control` variant.
///
/// Fail-closed: no analytics identity, a slow read, an unknown variant or any error all mean
/// control, so onboarding ends exactly as it did before.
///
/// The arm is remembered per account once the reader reaches the ending, so a reader who quits
/// mid-way and comes back finishes the same ending even if the flag read fails the second time.
abstract final class OnboardingActivationExperiment {
  /// PostHog flag key (project 302298). Registered in `config/feature-flags.yaml`.
  static const enabledFlag = 'onboarding-activation-flow';

  /// Pre-registration: `app/lib/services/experiments/onboarding_activation_flow.md`.
  static const prereg = 'app/lib/services/experiments/onboarding_activation_flow.md';

  /// Variants of a multivariate flag that mean treatment.
  static const treatmentVariants = {'test', 'treatment', 'activation'};

  /// Local override for debug builds only: `--dart-define=OMI_ONBOARDING_ENDING=activation` or
  /// `=control`. A dart-define cannot be flipped on a built artifact and `kDebugMode` excludes
  /// every store build, so this never reaches a user.
  static const _debugOverride = String.fromEnvironment('OMI_ONBOARDING_ENDING');

  static OnboardingEnding? get debugOverride => kDebugMode ? OnboardingEnding.fromWire(_debugOverride) : null;

  static const Duration _variantTimeout = Duration(seconds: 2);

  /// The arm for a flag value: `true` or a treatment variant is treatment, everything else
  /// (false, null, `control`, an unknown variant, a payload-only value) is control.
  static OnboardingEnding endingForFlagValue(Object? value) {
    if (value == true) return OnboardingEnding.activation;
    if (value is String && treatmentVariants.contains(value.trim().toLowerCase())) {
      return OnboardingEnding.activation;
    }
    return OnboardingEnding.voiceIntro;
  }

  /// Which ending to show. [readEnabled] defaults to the analytics manager's identity-checked
  /// flag read; [readValue] to the PostHog variant read. Both are injectable for tests.
  static Future<OnboardingEnding> resolve({
    Future<bool> Function(String key)? readEnabled,
    Future<Object?> Function(String key)? readValue,
  }) async {
    final override = debugOverride;
    if (override != null) return override;
    try {
      // The manager's read is the gate: it is false without a settled identity, with tracking
      // off, on unsupported platforms and after a timeout.
      final enabled = await (readEnabled ?? AnalyticsManager().isFeatureEnabled)(enabledFlag);
      if (!enabled) return OnboardingEnding.voiceIntro;
      final value = await (readValue ?? _readPosthogValue)(enabledFlag).timeout(_variantTimeout);
      return endingForFlagValue(value);
    } catch (_) {
      return OnboardingEnding.voiceIntro;
    }
  }

  static Future<Object?> _readPosthogValue(String key) => Posthog().getFeatureFlag(key);

  // ---- Per-account memory -------------------------------------------------------------------

  static String _key(String uid) => 'onboarding/ending/$uid';

  /// The ending this account already started, if any.
  static OnboardingEnding? remembered(String uid) {
    if (uid.isEmpty) return null;
    return OnboardingEnding.fromWire(SharedPreferencesUtil().getString(_key(uid)));
  }

  static void remember(String uid, OnboardingEnding ending) {
    if (uid.isEmpty) return;
    SharedPreferencesUtil().saveString(_key(uid), ending.wireName);
  }

  static void forget(String uid) {
    if (uid.isEmpty) return;
    SharedPreferencesUtil().remove(_key(uid));
  }
}
