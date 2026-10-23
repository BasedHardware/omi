import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// The first-run onboarding arms of the `onboarding-variant` experiment.
enum OnboardingVariant {
  /// The native steps exactly as shipped.
  control('control'),

  /// Reid's device-first onboarding, rendered from a web page (OTA); the payload names it.
  reid('reid'),

  /// Yinka's onboarding ending in a first conversation (PR #21445), native.
  yinka('yinka'),

  /// Pocket's order: sign-up paywall with a 30-day upsell, permissions, pairing that starts by
  /// itself, the device walkthrough, then the remaining native steps.
  pocket('pocket');

  const OnboardingVariant(this.wireName);

  /// The PostHog variant key.
  final String wireName;

  static OnboardingVariant? fromWire(String? value) {
    for (final variant in values) {
      if (variant.wireName == value) return variant;
    }
    return null;
  }
}

/// One resolved arm: the variant and, for [OnboardingVariant.reid], the page to render.
class OnboardingArm {
  const OnboardingArm(this.variant, {this.webUrl});

  static const control = OnboardingArm(OnboardingVariant.control);
  static const yinka = OnboardingArm(OnboardingVariant.yinka);
  static const pocket = OnboardingArm(OnboardingVariant.pocket);

  final OnboardingVariant variant;

  /// Only for [OnboardingVariant.reid]: the https page.
  final Uri? webUrl;

  bool get isControl => variant == OnboardingVariant.control;

  @override
  bool operator ==(Object other) => other is OnboardingArm && other.variant == variant && other.webUrl == webUrl;

  @override
  int get hashCode => Object.hash(variant, webUrl);

  @override
  String toString() => 'OnboardingArm(${variant.wireName}${webUrl == null ? '' : ', $webUrl'})';
}

/// Gate for which first-run onboarding a reader gets after sign-in and consent: the native steps
/// (control), Reid's web page (`reid`) or Yinka's native flow (`yinka`).
///
/// Evaluated on the client from the PostHog multivariate flag `onboarding-variant`; the `reid`
/// payload names the page: `{"url": "https://…"}`. Fail-closed: no analytics identity, a slow read,
/// a disabled flag, an unknown variant or a `reid` payload without an https URL all mean control.
abstract final class OnboardingVariantGate {
  /// PostHog flag key (project 302298). Registered in `config/feature-flags.yaml`.
  static const enabledFlag = 'onboarding-variant';

  /// Debug-build override: `--dart-define=OMI_ONBOARDING_VARIANT=reid|yinka|pocket`
  /// (`reid` also needs `OMI_ONBOARDING_WEBVIEW_URL=https://…`).
  static const _debugVariant = String.fromEnvironment('OMI_ONBOARDING_VARIANT');
  static const _debugUrl = String.fromEnvironment('OMI_ONBOARDING_WEBVIEW_URL');

  static OnboardingArm? get debugOverride {
    if (!kDebugMode) return null;
    return switch (OnboardingVariant.fromWire(_debugVariant)) {
      OnboardingVariant.yinka => OnboardingArm.yinka,
      OnboardingVariant.pocket => OnboardingArm.pocket,
      OnboardingVariant.reid => parse(variant: 'reid', payload: {'url': _debugUrl}),
      _ => null,
    };
  }

  /// Parses one flag read (the variant and, for `reid`, a decoded map or JSON payload) into an arm.
  /// Anything unexpected collapses to control.
  static OnboardingArm parse({String? variant, Object? payload}) {
    switch (OnboardingVariant.fromWire(variant?.trim())) {
      case OnboardingVariant.yinka:
        return OnboardingArm.yinka;
      case OnboardingVariant.pocket:
        return OnboardingArm.pocket;
      case OnboardingVariant.reid:
        Object? value = payload;
        if (value is String) {
          try {
            value = jsonDecode(value);
          } on FormatException {
            value = null;
          }
        }
        final raw = value is Map ? value['url'] : null;
        final url = raw is String ? Uri.tryParse(raw.trim()) : null;
        if (url == null || url.scheme != 'https' || url.host.isEmpty) return OnboardingArm.control;
        return OnboardingArm(OnboardingVariant.reid, webUrl: url);
      case OnboardingVariant.control:
      case null:
        return OnboardingArm.control;
    }
  }

  /// Right after sign-in the analytics identity is still settling and the SDK's cached flags belong
  /// to the anonymous id, where a per-user rollout never matches; so a read waits (at most
  /// [identityWait]) for the identity, re-fetches flags for it, and only then reads.
  static Future<OnboardingArm>? _warmed;
  static int _warmedEpoch = -1;

  /// Starts resolving early (while the reader is still on the consent screen) with a long identity
  /// wait, so [resolve] at the tap usually finds the answer ready instead of starting the clock.
  /// The warm-up is fenced to the analytics identity epoch it started in: an account change
  /// ("use a different account") discards it, so one account never inherits another's decision.
  static void warm({
    Future<String?> Function(String key)? readVariant,
    Future<Object?> Function(String key)? readPayload,
    String? Function()? settledIdentity,
    Future<bool> Function()? reload,
    int Function()? identityEpoch,
    Duration identityWait = const Duration(seconds: 20),
  }) {
    final epoch = (identityEpoch ?? _currentEpoch)();
    if (_warmed != null && _warmedEpoch == epoch) return;
    _warmedEpoch = epoch;
    _warmed = _resolve(
      readVariant: readVariant,
      readPayload: readPayload,
      settledIdentity: settledIdentity,
      reload: reload,
      identityEpoch: identityEpoch,
      identityWait: identityWait,
    );
  }

  /// Drops a pending warm-up (the account is changing).
  static void invalidate() {
    _warmed = null;
    _warmedEpoch = -1;
  }

  static int _currentEpoch() => AnalyticsManager.identityChanges.value;

  @visibleForTesting
  static void resetForTesting() => invalidate();

  /// The arm to show. [readVariant] and [readPayload] default to the analytics manager's flag reads
  /// and are injectable for tests.
  static Future<OnboardingArm> resolve({
    Future<String?> Function(String key)? readVariant,
    Future<Object?> Function(String key)? readPayload,
    String? Function()? settledIdentity,
    Future<bool> Function()? reload,
    int Function()? identityEpoch,
    Duration identityWait = const Duration(seconds: 3),
  }) async {
    final epoch = (identityEpoch ?? _currentEpoch)();
    final warmed = _warmed;
    final warmedEpoch = _warmedEpoch;
    invalidate();
    if (warmed != null && warmedEpoch == epoch) {
      // Give a warm-up that is still waiting the same bounded patience as a cold read.
      return warmed.timeout(identityWait + const Duration(seconds: 2), onTimeout: () => OnboardingArm.control);
    }
    return _resolve(
      readVariant: readVariant,
      readPayload: readPayload,
      settledIdentity: settledIdentity,
      reload: reload,
      identityEpoch: identityEpoch,
      identityWait: identityWait,
    );
  }

  static Future<OnboardingArm> _resolve({
    Future<String?> Function(String key)? readVariant,
    Future<Object?> Function(String key)? readPayload,
    String? Function()? settledIdentity,
    Future<bool> Function()? reload,
    int Function()? identityEpoch,
    required Duration identityWait,
  }) async {
    final override = debugOverride;
    if (override != null) return override;
    try {
      final epoch = (identityEpoch ?? _currentEpoch)();
      final identity = settledIdentity ?? () => AnalyticsManager().settledDistinctId;
      final deadline = DateTime.now().add(identityWait);
      while (identity() == null && DateTime.now().isBefore(deadline)) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
      }
      if (identity() == null) return OnboardingArm.control;
      // Stale flags must not decide: a reload that fails or times out is control.
      if (!await (reload ?? AnalyticsManager().reloadFeatureFlags)()) return OnboardingArm.control;
      final variant = await (readVariant ?? AnalyticsManager().getFeatureFlagVariant)(enabledFlag);
      final arm = OnboardingVariant.fromWire(variant?.trim());
      if (arm == null || arm == OnboardingVariant.control) return OnboardingArm.control;
      final payload = arm == OnboardingVariant.reid
          ? await (readPayload ?? AnalyticsManager().getFeatureFlagPayload)(enabledFlag)
          : null;
      // The account changed while this was in flight: the answer belongs to someone else.
      if ((identityEpoch ?? _currentEpoch)() != epoch) return OnboardingArm.control;
      return parse(variant: variant, payload: payload);
    } catch (_) {
      return OnboardingArm.control;
    }
  }
}
