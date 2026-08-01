import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_appauth/flutter_appauth.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';

/// Additive OIDC (Authorization Code + PKCE) login client — ADR-0038.
///
/// This does NOT replace Firebase. It is a second, compile-time-selected auth
/// path, active only when `AUTH_BACKEND=oidc`. Its single job is to obtain a
/// token from the configured OIDC issuer (e.g. Keycloak) and write it to the
/// same SharedPreferences seam the Firebase flow uses:
///   - `SharedPreferencesUtil().authToken` = access token (Bearer for the API)
///   - `SharedPreferencesUtil().uid`        = the `sub` claim
///   - `SharedPreferencesUtil().tokenExpirationTime`
/// From there the HTTP layer (`backend/http/shared.dart`) and the backend
/// (`AUTH_BACKEND=oidc`, JWKS verification — ADR-0034) work transparently.
class OidcAuthService {
  OidcAuthService._();

  static final OidcAuthService instance = OidcAuthService._();

  static const List<String> _scopes = <String>['openid', 'profile', 'email', 'offline_access'];

  final FlutterAppAuth _appAuth = const FlutterAppAuth();

  // flutter_appauth rejects concurrent token operations ("Concurrent operations
  // detected"). Serialize login/refresh so a getAuthHeader-triggered refresh
  // never collides with an in-flight login during the redirect.
  Future<void> _tokenLock = Future<void>.value();

  Future<T> _synchronized<T>(Future<T> Function() op) {
    final prev = _tokenLock;
    final completer = Completer<void>();
    _tokenLock = completer.future;
    return prev.then((_) => op()).whenComplete(completer.complete);
  }

  bool get isConfigured =>
      Env.useOidc &&
      (Env.oidcIssuer?.isNotEmpty ?? false) &&
      (Env.oidcClientId?.isNotEmpty ?? false) &&
      (Env.oidcRedirectScheme?.isNotEmpty ?? false);

  /// Redirect URI registered on the OIDC client, derived from the custom scheme.
  String get _redirectUrl => '${Env.oidcRedirectScheme}:/oidc-callback';

  /// AppAuth refuses cleartext by default. Permit it only when the issuer is
  /// explicitly http:// (on-prem LAN/dev); https issuers stay strict.
  bool get _allowInsecureConnections => (Env.oidcIssuer ?? '').startsWith('http://');

  /// Whether a usable OIDC session is currently stored. OIDC-aware replacement
  /// for the Firebase `currentUser` check, to be wired into `isSignedIn()` (S2).
  bool hasStoredSession() {
    final prefs = SharedPreferencesUtil();
    return prefs.authToken.isNotEmpty && prefs.uid.isNotEmpty;
  }

  /// Runs the interactive login and persists the resulting session.
  Future<OidcLoginOutcome> login() {
    if (!isConfigured) {
      return Future.value(
          const OidcLoginOutcome.failure('OIDC not configured (issuer/client_id/redirect scheme missing).'));
    }
    return _synchronized(() async {
      try {
        final response = await _appAuth.authorizeAndExchangeCode(
          AuthorizationTokenRequest(
            Env.oidcClientId!,
            _redirectUrl,
            issuer: Env.oidcIssuer,
            scopes: _scopes,
            promptValues: const <String>['login'],
            allowInsecureConnections: _allowInsecureConnections,
          ),
        );
        return _persist(
          accessToken: response.accessToken,
          idToken: response.idToken,
          refreshToken: response.refreshToken,
          expiration: response.accessTokenExpirationDateTime,
        );
      } catch (e, s) {
        debugPrint('OIDC login failed: $e\n$s');
        return OidcLoginOutcome.failure('OIDC login failed: $e');
      }
    });
  }

  /// Refreshes the stored session using the OIDC refresh token.
  Future<OidcLoginOutcome> refresh() {
    if (!isConfigured) {
      return Future.value(const OidcLoginOutcome.failure('No OIDC refresh token available.'));
    }
    return _synchronized(() async {
      final prefs = SharedPreferencesUtil();
      // A concurrent login (e.g. during the redirect) may have already written a
      // fresh token — skip the redundant refresh instead of racing AppAuth.
      if (prefs.authToken.isNotEmpty && prefs.tokenExpirationTime > DateTime.now().millisecondsSinceEpoch + 5000) {
        return OidcLoginOutcome.success(prefs.uid);
      }
      final refreshToken = prefs.oidcRefreshToken;
      if (refreshToken.isEmpty) {
        return const OidcLoginOutcome.failure('No OIDC refresh token available.');
      }
      try {
        final response = await _appAuth.token(
          TokenRequest(
            Env.oidcClientId!,
            _redirectUrl,
            issuer: Env.oidcIssuer,
            refreshToken: refreshToken,
            scopes: _scopes,
            allowInsecureConnections: _allowInsecureConnections,
          ),
        );
        return _persist(
          accessToken: response.accessToken,
          idToken: response.idToken,
          refreshToken: response.refreshToken ?? refreshToken,
          expiration: response.accessTokenExpirationDateTime,
        );
      } catch (e, s) {
        debugPrint('OIDC refresh failed: $e\n$s');
        return OidcLoginOutcome.failure('OIDC refresh failed: $e');
      }
    });
  }

  /// Clears the OIDC session locally (best-effort provider end-session).
  Future<void> logout() async {
    final idToken = _lastIdToken;
    _lastIdToken = null;
    if (isConfigured && idToken != null) {
      try {
        await _appAuth.endSession(
          EndSessionRequest(
            idTokenHint: idToken,
            issuer: Env.oidcIssuer,
            postLogoutRedirectUrl: _redirectUrl,
            allowInsecureConnections: _allowInsecureConnections,
          ),
        );
      } catch (e) {
        debugPrint('OIDC endSession failed (ignored): $e');
      }
    }
    SharedPreferencesUtil().clearUserDisplayCache();
  }

  String? _lastIdToken;

  OidcLoginOutcome _persist({
    required String? accessToken,
    required String? idToken,
    required String? refreshToken,
    required DateTime? expiration,
  }) {
    if (accessToken == null || accessToken.isEmpty) {
      return const OidcLoginOutcome.failure('OIDC provider returned no access token.');
    }
    final claims = _decodeJwtClaims(idToken) ?? _decodeJwtClaims(accessToken) ?? const <String, dynamic>{};
    final sub = claims['sub']?.toString() ?? '';
    if (sub.isEmpty) {
      return const OidcLoginOutcome.failure('OIDC token has no `sub` claim.');
    }

    final prefs = SharedPreferencesUtil();
    prefs.uid = sub;
    prefs.authToken = accessToken;
    prefs.oidcRefreshToken = refreshToken ?? '';
    prefs.tokenExpirationTime = expiration?.millisecondsSinceEpoch ?? 0;
    if (prefs.email.isEmpty) {
      prefs.email = claims['email']?.toString() ?? '';
    }
    if (prefs.givenName.isEmpty) {
      final name = (claims['given_name'] ?? claims['name'])?.toString() ?? '';
      if (name.isNotEmpty) prefs.givenName = name.split(' ').first;
    }
    _lastIdToken = idToken;
    return OidcLoginOutcome.success(sub);
  }

  /// Decodes a JWT payload WITHOUT verifying the signature — the backend is the
  /// authority (JWKS, ADR-0034). Used only to read local display claims/`sub`.
  Map<String, dynamic>? _decodeJwtClaims(String? jwt) {
    if (jwt == null || jwt.isEmpty) return null;
    final parts = jwt.split('.');
    if (parts.length != 3) return null;
    try {
      final normalized = base64Url.normalize(parts[1]);
      final payload = utf8.decode(base64Url.decode(normalized));
      final decoded = jsonDecode(payload);
      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
  }
}

/// Result of an OIDC login/refresh attempt.
class OidcLoginOutcome {
  final bool ok;
  final String? uid;
  final String? error;

  const OidcLoginOutcome.success(this.uid)
      : ok = true,
        error = null;

  const OidcLoginOutcome.failure(this.error)
      : ok = false,
        uid = null;
}
