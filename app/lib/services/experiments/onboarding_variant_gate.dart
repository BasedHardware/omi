import 'dart:convert';

import 'package:flutter/foundation.dart';

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

/// Which first-run onboarding a reader gets after sign-in and consent: always [OnboardingArm.pocket].
/// The other arms remain reachable only through the debug-build override. A later test goes through
/// the Omi flag store plus exposure events, not a PostHog flag read here.
abstract final class OnboardingVariantGate {
  /// The analytics property name dashboards break the funnel down by; released builds still read
  /// this PostHog flag (project 302298). Registered in `config/feature-flags.yaml`.
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

  /// The arm to show.
  static OnboardingArm get arm => debugOverride ?? OnboardingArm.pocket;
}
