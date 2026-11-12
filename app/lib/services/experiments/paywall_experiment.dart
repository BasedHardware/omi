import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// The paywall designs. Free users get [trial]; the others are reachable only through the
/// debug-build override. A later test goes through the Omi flag store plus exposure events.
enum PaywallVariant {
  /// The shipped `PlansSheet`, exactly as before the experiment existed.
  control('control'),

  /// The native port of the soft paywall from PR #21412 ("Outline" design).
  outline('outline'),

  /// A web page rendered in a webview; the page itself is the variant (`url` in the payload).
  web('web'),

  /// Native free-trial paywall (timeline + feature carousel), shown once right after sign-up
  /// and consent when the payload asks for the onboarding placement.
  trial('trial');

  const PaywallVariant(this.wireName);

  final String wireName;

  static PaywallVariant? fromWire(String? value) {
    for (final variant in values) {
      if (variant.wireName == value) return variant;
    }
    return null;
  }
}

/// The arm plus its placement.
@immutable
class PaywallExperimentConfig {
  const PaywallExperimentConfig({required this.variant, this.webUrl, this.onboardingPaywall = false});

  static const control = PaywallExperimentConfig(variant: PaywallVariant.control);
  static const trial = PaywallExperimentConfig(variant: PaywallVariant.trial, onboardingPaywall: true);

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

/// Which paywall a free reader gets: always [PaywallExperimentConfig.trial]. Readers the backend says
/// cannot get a trial see the shipped sheet instead ([PaywallRouter]).
///
/// Debug payload (JSON object): `{"url": "https://…", "onboarding_paywall": true}` — `url` is required
/// for `web` and must be https; `onboarding_paywall` is optional and defaults to false.
abstract final class PaywallExperiment {
  /// The exposure's flag name dashboards break metrics down by; released builds still read this
  /// PostHog flag. Registered in `config/feature-flags.yaml`.
  static const enabledFlag = 'paywall-variant';

  /// Debug-build override: `--dart-define=OMI_PAYWALL_VARIANT=outline|web|trial` (and optionally
  /// `OMI_PAYWALL_WEB_URL=https://…`). `kDebugMode` excludes every store build.
  static const _debugVariant = String.fromEnvironment('OMI_PAYWALL_VARIANT');
  static const _debugWebUrl = String.fromEnvironment('OMI_PAYWALL_WEB_URL');

  /// Default web page when the override names `web` without a URL.
  static const defaultWebUrl = 'https://omi-paywall.vercel.app/';

  static bool get debugOverrideActive => kDebugMode && _debugVariant.isNotEmpty;

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
      case PaywallVariant.trial:
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

  /// The arm to show.
  static PaywallExperimentConfig get current {
    if (!debugOverrideActive) return PaywallExperimentConfig.trial;
    return parse(
      variant: _debugVariant,
      payload: {'url': _debugWebUrl.isEmpty ? defaultWebUrl : _debugWebUrl, 'onboarding_paywall': true},
    );
  }

  /// Records the exposure (`$feature_flag_called`), once per identity and arm, and tags every later
  /// event with `$feature/paywall-variant`. True when an exposure was sent.
  static bool recordExposure(PaywallExperimentConfig config, {bool Function(String key, String variant)? record}) =>
      (record ?? AnalyticsManager().recordFeatureFlagExposure)(enabledFlag, config.variant.wireName);
}
