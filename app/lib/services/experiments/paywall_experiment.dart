import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// Which paywall a free user sees. New variants are added here and in the PostHog flag; the
/// split, the kill switch and the per-variant payload live in PostHog so they change over the air.
enum PaywallVariant {
  /// The shipped `PlansSheet`, exactly as before the experiment existed.
  control('control'),

  /// The native port of the soft paywall from PR #21412 ("Outline" design).
  outline('outline'),

  /// A web page rendered in a webview; the page itself is the variant (`url` in the payload).
  web('web');

  const PaywallVariant(this.wireName);

  final String wireName;

  static PaywallVariant? fromWire(String? value) {
    for (final variant in values) {
      if (variant.wireName == value) return variant;
    }
    return null;
  }
}

/// The resolved arm plus its payload. Immutable for the session so a reader never flips between
/// paywalls mid-session; PostHog's experience continuity keeps the arm stable across sessions.
@immutable
class PaywallExperimentConfig {
  const PaywallExperimentConfig({required this.variant, this.webUrl, this.onboardingPaywall = false});

  static const control = PaywallExperimentConfig(variant: PaywallVariant.control);

  final PaywallVariant variant;

  /// Only for [PaywallVariant.web]: the https page to render.
  final Uri? webUrl;

  /// Whether this arm also shows its paywall once at the end of first-run onboarding (a placement
  /// the control arm does not have).
  final bool onboardingPaywall;

  bool get isControl => variant == PaywallVariant.control;

  @override
  bool operator ==(Object other) =>
      other is PaywallExperimentConfig &&
      other.variant == variant &&
      other.webUrl == webUrl &&
      other.onboardingPaywall == onboardingPaywall;

  @override
  int get hashCode => Object.hash(variant, webUrl, onboardingPaywall);

  @override
  String toString() => 'PaywallExperimentConfig(${variant.wireName}, url: $webUrl, onboarding: $onboardingPaywall)';
}

/// Client gate for the mobile paywall A/B test.
///
/// Evaluated from the PostHog multivariate flag `paywall-variant` (project 302298). Fail-closed:
/// no analytics identity, a slow read, an unknown variant or a malformed payload all mean
/// [PaywallVariant.control], and the app behaves exactly as it did before the experiment.
///
/// Payload per variant (JSON object):
/// `{"url": "https://…", "onboarding_paywall": true}` — `url` is required for `web` and must be
/// https; `onboarding_paywall` is optional and defaults to false.
abstract final class PaywallExperiment {
  /// PostHog flag key. Registered in `config/feature-flags.yaml`.
  static const flagKey = 'paywall-variant';

  /// Debug-build override: `--dart-define=OMI_PAYWALL_VARIANT=outline|web` (and optionally
  /// `OMI_PAYWALL_WEB_URL=https://…`). `kDebugMode` excludes every store build.
  static const _debugVariant = String.fromEnvironment('OMI_PAYWALL_VARIANT');
  static const _debugWebUrl = String.fromEnvironment('OMI_PAYWALL_WEB_URL');

  /// Default web page when the override names `web` without a URL.
  static const defaultWebUrl = 'https://omi-paywall.vercel.app/';

  static bool get debugOverrideActive => kDebugMode && _debugVariant.isNotEmpty;

  static PaywallExperimentConfig? _session;

  /// Parses one flag read into a config. Anything unexpected collapses to control.
  static PaywallExperimentConfig parse({String? variant, Object? payload}) {
    final arm = PaywallVariant.fromWire(variant);
    if (arm == null || arm == PaywallVariant.control) return PaywallExperimentConfig.control;

    Object? value = payload;
    if (value is String) {
      try {
        value = jsonDecode(value);
      } on FormatException {
        value = null;
      }
    }
    final map = value is Map ? value : const <Object?, Object?>{};
    final onboardingPaywall = map['onboarding_paywall'] == true;

    switch (arm) {
      case PaywallVariant.outline:
        return PaywallExperimentConfig(variant: arm, onboardingPaywall: onboardingPaywall);
      case PaywallVariant.web:
        final raw = map['url'];
        final url = raw is String ? Uri.tryParse(raw.trim()) : null;
        if (url == null || url.scheme != 'https' || url.host.isEmpty) return PaywallExperimentConfig.control;
        return PaywallExperimentConfig(variant: arm, webUrl: url, onboardingPaywall: onboardingPaywall);
      case PaywallVariant.control:
        return PaywallExperimentConfig.control;
    }
  }

  /// The arm for this session. [readVariant] and [readPayload] default to the analytics manager's
  /// flag reads and are injectable for tests. The first non-null read is cached for the process.
  static Future<PaywallExperimentConfig> resolve({
    Future<String?> Function(String key)? readVariant,
    Future<Object?> Function(String key)? readPayload,
    bool refresh = false,
  }) async {
    if (debugOverrideActive) {
      return parse(
        variant: _debugVariant,
        payload: {'url': _debugWebUrl.isEmpty ? defaultWebUrl : _debugWebUrl, 'onboarding_paywall': true},
      );
    }
    final cached = _session;
    if (cached != null && !refresh) return cached;
    try {
      final variant = await (readVariant ?? AnalyticsManager().getFeatureFlagVariant)(flagKey);
      if (variant == null) return PaywallExperimentConfig.control; // unresolved: try again next time
      final payload = variant == PaywallVariant.control.wireName
          ? null
          : await (readPayload ?? AnalyticsManager().getFeatureFlagPayload)(flagKey);
      final config = parse(variant: variant, payload: payload);
      _session = config;
      return config;
    } catch (_) {
      return PaywallExperimentConfig.control;
    }
  }

  /// Records the exposure PostHog Experiments attribute metrics to (`$feature_flag_called`), once
  /// per arm per process, and tags every later event with `$feature/paywall-variant`.
  static void recordExposure(PaywallExperimentConfig config, {void Function(String key, String variant)? record}) {
    (record ?? AnalyticsManager().recordFeatureFlagExposure)(flagKey, config.variant.wireName);
  }

  @visibleForTesting
  static void resetForTesting() {
    _session = null;
  }
}
