import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/env/backend_url_override.dart';
import 'package:omi/env/env.dart';

/// Hosts of Omi's own API. Omi credentials go only to these (see `shouldAttachOmiCredentials`),
/// and Omi's third-party services run only while the app talks to one of them.
const omiApiHosts = {'api.omi.me', 'api.omiapi.com'};

/// Whether the app may start the services that report to Omi's vendors: product analytics
/// (PostHog), crash reporting (Crashlytics), support chat (Intercom) and push (Firebase Messaging).
///
/// Those services belong to Omi and are keyed to Omi accounts. While the app talks to a backend
/// that is not Omi's -- a local backend, or a custom URL from Developer Settings -- they would
/// report activity on someone else's server to Omi, so they stay off.
abstract final class OutboundPolicy {
  static bool _thirdPartyServicesAllowed = true;

  static bool get thirdPartyServicesAllowed => _thirdPartyServicesAllowed;

  /// Decides the policy before any of those services start. Crash reporting starts right after
  /// Firebase, long before preferences load, so the persisted backend override is read here.
  static Future<void> resolve() async {
    final prefs = await SharedPreferences.getInstance();
    BackendUrlOverride.restore(prefs.getString('customBackendUrl') ?? '');
    _thirdPartyServicesAllowed = isOmiBackend(Env.apiBaseUrl);
  }

  /// True for an HTTPS URL on one of [omiApiHosts].
  static bool isOmiBackend(String? baseUrl) {
    final uri = baseUrl == null ? null : Uri.tryParse(baseUrl);
    return uri != null && uri.scheme.toLowerCase() == 'https' && omiApiHosts.contains(uri.host.toLowerCase());
  }

  @visibleForTesting
  static set debugThirdPartyServicesAllowed(bool value) => _thirdPartyServicesAllowed = value;
}
