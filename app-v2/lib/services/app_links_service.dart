import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/foundation.dart';

/// Sealed hierarchy for parsed `nooto://` deep-links.
sealed class NootoDeepLink {
  const NootoDeepLink();
}

/// Plugin OAuth completion: `nooto://app-setup-complete?app_id=X&status=Y`.
class AppSetupComplete extends NootoDeepLink {
  const AppSetupComplete({required this.appId, required this.status});
  final String appId;
  final String status; // 'success' or error text
}

/// Anything we don't recognize. Logged at debug, not surfaced to users.
class UnknownDeepLink extends NootoDeepLink {
  const UnknownDeepLink(this.uri);
  final Uri uri;
}

/// Routes incoming `nooto://` URIs into typed events.
///
/// Cold-start handoff: when the user taps "Continue to Nooto" while the app is
/// killed, iOS launches it and `getInitialLink()` returns the pending URI. We
/// stash it in [coldStartLink] so `AppsProvider` can drain it after first
/// successful apps load (avoids the race where the deep-link fires before the
/// apps list is hydrated).
///
/// Warm path: subsequent links arrive via [linkStream] for the lifetime of the
/// app process.
class AppLinksService {
  AppLinksService({AppLinks? appLinks}) : _appLinks = appLinks ?? AppLinks();

  final AppLinks _appLinks;
  NootoDeepLink? _coldStartLink;
  bool _coldStartLoaded = false;

  /// Captured cold-start link, parsed. Null if there was no pending URI on
  /// launch OR if [drainColdStartLink] has already been called once.
  NootoDeepLink? get coldStartLink => _coldStartLink;

  /// Loads the initial (cold-start) URI exactly once. Idempotent — subsequent
  /// calls return without re-fetching. Returns the parsed link (or null).
  Future<NootoDeepLink?> loadColdStartLink() async {
    if (_coldStartLoaded) return _coldStartLink;
    _coldStartLoaded = true;
    try {
      final uri = await _appLinks.getInitialLink();
      if (uri == null) return null;
      _coldStartLink = parseLink(uri);
      return _coldStartLink;
    } catch (e, st) {
      debugPrint('[AppLinksService] getInitialLink failed: $e\n$st');
      return null;
    }
  }

  /// Consumes the cold-start link. After this, [coldStartLink] returns null —
  /// callers must check the return of this method, not the getter.
  NootoDeepLink? drainColdStartLink() {
    final link = _coldStartLink;
    _coldStartLink = null;
    return link;
  }

  /// Stream of typed deep-links arriving while the app is running. Every URI
  /// becomes either an [AppSetupComplete] or [UnknownDeepLink] event.
  Stream<NootoDeepLink> get linkStream =>
      _appLinks.uriLinkStream.map(parseLink);

  /// Parse a `nooto://...` URI into the typed event hierarchy. Public for
  /// tests; production callers should use the streams above.
  static NootoDeepLink parseLink(Uri uri) {
    // Match `nooto://app-setup-complete?app_id=X&status=Y`. The host part of
    // a custom-scheme URI may land in `host` OR `path` depending on how iOS
    // / Android parse it; handle both.
    final isAppSetupComplete = uri.scheme == 'nooto' &&
        (uri.host == 'app-setup-complete' ||
            uri.path == '/app-setup-complete' ||
            uri.path == 'app-setup-complete');
    if (!isAppSetupComplete) return UnknownDeepLink(uri);
    final appId = uri.queryParameters['app_id'] ?? '';
    final status = uri.queryParameters['status'] ?? 'success';
    if (appId.isEmpty) return UnknownDeepLink(uri);
    return AppSetupComplete(appId: appId, status: status);
  }
}
