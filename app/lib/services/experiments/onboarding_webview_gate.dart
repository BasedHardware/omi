import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// Gate for rendering first-run onboarding from a web page instead of the native steps, so the
/// flow can change over the air. Off (the default) leaves the native onboarding exactly as it is.
///
/// Evaluated on the client from the PostHog flag `onboarding-webview`; the payload names the page:
/// `{"url": "https://…"}`. Fail-closed: no analytics identity, a slow read, a disabled flag or a
/// payload without an https URL all mean native onboarding.
abstract final class OnboardingWebviewGate {
  /// PostHog flag key (project 302298). Registered in `config/feature-flags.yaml`.
  static const enabledFlag = 'onboarding-webview';

  /// Debug-build override: `--dart-define=OMI_ONBOARDING_WEBVIEW_URL=https://…`.
  static const _debugUrl = String.fromEnvironment('OMI_ONBOARDING_WEBVIEW_URL');

  static bool get debugOverrideActive => kDebugMode && _debugUrl.isNotEmpty;

  /// Parses a flag payload (a decoded map or a JSON string) into the page URL, or null.
  static Uri? parse({required bool enabled, Object? payload}) {
    if (!enabled) return null;
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
    if (url == null || url.scheme != 'https' || url.host.isEmpty) return null;
    return url;
  }

  /// The page to render, or null for native onboarding. [readFlag] and [readPayload] default to
  /// the analytics manager's flag reads and are injectable for tests.
  ///
  /// Right after sign-in the analytics identity is still settling and the SDK's cached flags belong
  /// to the anonymous id, where a per-user rollout never matches; so this waits (at most
  /// [identityWait]) for the identity, re-fetches flags for it, and only then reads.
  static Future<Uri?>? _warmed;

  /// Starts resolving early (while the reader is still on the consent screen) with a long identity
  /// wait, so [resolve] at the tap usually finds the answer ready instead of starting the clock.
  static void warm({
    Future<bool> Function(String key)? readFlag,
    Future<Object?> Function(String key)? readPayload,
    String? Function()? settledIdentity,
    Future<void> Function()? reload,
    Duration identityWait = const Duration(seconds: 20),
  }) {
    _warmed ??= _resolve(
      readFlag: readFlag,
      readPayload: readPayload,
      settledIdentity: settledIdentity,
      reload: reload,
      identityWait: identityWait,
    );
  }

  @visibleForTesting
  static void resetForTesting() => _warmed = null;

  static Future<Uri?> resolve({
    Future<bool> Function(String key)? readFlag,
    Future<Object?> Function(String key)? readPayload,
    String? Function()? settledIdentity,
    Future<void> Function()? reload,
    Duration identityWait = const Duration(seconds: 3),
  }) async {
    final warmed = _warmed;
    if (warmed != null) {
      _warmed = null;
      // Give a warm-up that is still waiting the same bounded patience as a cold read.
      return warmed.timeout(identityWait + const Duration(seconds: 2), onTimeout: () => null);
    }
    return _resolve(
      readFlag: readFlag,
      readPayload: readPayload,
      settledIdentity: settledIdentity,
      reload: reload,
      identityWait: identityWait,
    );
  }

  static Future<Uri?> _resolve({
    Future<bool> Function(String key)? readFlag,
    Future<Object?> Function(String key)? readPayload,
    String? Function()? settledIdentity,
    Future<void> Function()? reload,
    required Duration identityWait,
  }) async {
    if (debugOverrideActive) return parse(enabled: true, payload: {'url': _debugUrl});
    try {
      final identity = settledIdentity ?? () => AnalyticsManager().settledDistinctId;
      final deadline = DateTime.now().add(identityWait);
      while (identity() == null && DateTime.now().isBefore(deadline)) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
      }
      if (identity() == null) return null;
      await (reload ?? AnalyticsManager().reloadFeatureFlags)();
      final enabled = await (readFlag ?? AnalyticsManager().isFeatureEnabled)(enabledFlag);
      if (!enabled) return null;
      final payload = await (readPayload ?? AnalyticsManager().getFeatureFlagPayload)(enabledFlag);
      return parse(enabled: true, payload: payload);
    } catch (_) {
      return null;
    }
  }
}
