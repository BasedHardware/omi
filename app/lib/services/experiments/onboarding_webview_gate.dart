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
  static int _warmedEpoch = -1;

  /// Starts resolving early (while the reader is still on the consent screen) with a long identity
  /// wait, so [resolve] at the tap usually finds the answer ready instead of starting the clock.
  /// The warm-up is fenced to the analytics identity epoch it started in: an account change
  /// ("use a different account") discards it, so one account never inherits another's decision.
  static void warm({
    Future<bool> Function(String key)? readFlag,
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
      readFlag: readFlag,
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

  static Future<Uri?> resolve({
    Future<bool> Function(String key)? readFlag,
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
      return warmed.timeout(identityWait + const Duration(seconds: 2), onTimeout: () => null);
    }
    return _resolve(
      readFlag: readFlag,
      readPayload: readPayload,
      settledIdentity: settledIdentity,
      reload: reload,
      identityEpoch: identityEpoch,
      identityWait: identityWait,
    );
  }

  static Future<Uri?> _resolve({
    Future<bool> Function(String key)? readFlag,
    Future<Object?> Function(String key)? readPayload,
    String? Function()? settledIdentity,
    Future<bool> Function()? reload,
    int Function()? identityEpoch,
    required Duration identityWait,
  }) async {
    if (debugOverrideActive) return parse(enabled: true, payload: {'url': _debugUrl});
    try {
      final epoch = (identityEpoch ?? _currentEpoch)();
      final identity = settledIdentity ?? () => AnalyticsManager().settledDistinctId;
      final deadline = DateTime.now().add(identityWait);
      while (identity() == null && DateTime.now().isBefore(deadline)) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
      }
      if (identity() == null) return null;
      // Stale flags must not decide: a reload that fails or times out is native onboarding.
      if (!await (reload ?? AnalyticsManager().reloadFeatureFlags)()) return null;
      final enabled = await (readFlag ?? AnalyticsManager().isFeatureEnabled)(enabledFlag);
      if (!enabled) return null;
      final payload = await (readPayload ?? AnalyticsManager().getFeatureFlagPayload)(enabledFlag);
      // The account changed while this was in flight: the answer belongs to someone else.
      if ((identityEpoch ?? _currentEpoch)() != epoch) return null;
      return parse(enabled: true, payload: payload);
    } catch (_) {
      return null;
    }
  }
}
