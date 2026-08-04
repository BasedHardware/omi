import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_appauth/flutter_appauth.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

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
  OidcAuthService._()
      : _appAuth = const FlutterAppAuth(),
        _secureStorage = const FlutterSecureStorage(
          aOptions: AndroidOptions(encryptedSharedPreferences: true),
        ),
        _clock = DateTime.now;

  /// Test-only constructor: injects the AppAuth client, secure storage, and a
  /// clock. Every argument defaults to the exact production instance used by
  /// [OidcAuthService._], so an unparameterized `OidcAuthService.forTest()`
  /// behaves identically to [instance] — this constructor adds seams only, it
  /// changes no behavior.
  @visibleForTesting
  OidcAuthService.forTest({
    FlutterAppAuth? appAuth,
    FlutterSecureStorage? secureStorage,
    DateTime Function()? clock,
  })  : _appAuth = appAuth ?? const FlutterAppAuth(),
        _secureStorage = secureStorage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            ),
        _clock = clock ?? DateTime.now;

  static final OidcAuthService instance = OidcAuthService._();

  static const List<String> _scopes = <String>['openid', 'profile', 'email', 'offline_access'];

  /// A stored access token counts as "fresh" only while it has at least this
  /// much validity left. Kept in lockstep with the 5-minute renewal window the
  /// HTTP layer enforces in `getAuthHeader` (backend/http/shared.dart): a token
  /// the caller already considers stale must actually be refreshed here, not
  /// returned unchanged. A forced refresh (401 recovery) bypasses this entirely.
  static const Duration tokenValidityFloor = Duration(minutes: 5);

  // Injected via the constructors above; production defaults to `const FlutterAppAuth()`.
  final FlutterAppAuth _appAuth;

  /// Monotonic wall-clock source (production: `DateTime.now`), injectable for tests.
  final DateTime Function() _clock;

  // The long-lived `offline_access` refresh token is a replay credential: it lives in
  // platform secure storage (iOS Keychain / Android Keystore-backed EncryptedSharedPreferences),
  // never in ordinary SharedPreferences. Only non-secret session state (uid, access token,
  // expiry) stays in prefs — `hasStoredSession()` reads those, so it stays synchronous.
  static const String _refreshTokenKey = 'oidcRefreshToken';
  // Injected via the constructors above; production defaults to the
  // EncryptedSharedPreferences-backed `const FlutterSecureStorage(...)`.
  final FlutterSecureStorage _secureStorage;

  Future<String> _readRefreshToken() async {
    final secure = await _secureStorage.read(key: _refreshTokenKey);
    if (secure != null && secure.isNotEmpty) return secure;
    // One-time migration: an existing session may still hold the token in plaintext prefs.
    final legacy = SharedPreferencesUtil().oidcRefreshToken;
    if (legacy.isNotEmpty) {
      await _secureStorage.write(key: _refreshTokenKey, value: legacy);
      SharedPreferencesUtil().oidcRefreshToken = '';
    }
    return legacy;
  }

  Future<void> _writeRefreshToken(String token) async {
    await _secureStorage.write(key: _refreshTokenKey, value: token);
    SharedPreferencesUtil().oidcRefreshToken = ''; // scrub any legacy plaintext copy
  }

  Future<void> _deleteRefreshToken() async {
    await _secureStorage.delete(key: _refreshTokenKey);
    SharedPreferencesUtil().oidcRefreshToken = '';
  }

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

  /// AppAuth refuses cleartext by default. A deployed issuer — including on-prem
  /// — must use HTTPS: sending auth traffic (codes, tokens, the long-lived
  /// refresh token) over http:// exposes it on the wire. Cleartext is permitted
  /// ONLY for a loopback issuer (localhost/127.0.0.1/::1) in a debug build, i.e.
  /// a developer running Keycloak on the same machine. A non-loopback http://
  /// issuer stays strict and the AppAuth request fails closed.
  bool get _allowInsecureConnections => allowInsecureFor(Env.oidcIssuer, debug: kDebugMode);

  /// Pure decision for [_allowInsecureConnections], extracted so the hardening
  /// rule can be unit-tested without touching `Env`/`kDebugMode`. Cleartext is
  /// permitted ONLY for a loopback issuer (localhost/127.0.0.1/::1) in a debug
  /// build; every other case fails closed.
  @visibleForTesting
  static bool allowInsecureFor(String? issuer, {required bool debug}) {
    final i = issuer ?? '';
    if (!i.startsWith('http://')) return false;
    final host = Uri.tryParse(i)?.host ?? '';
    final isLoopback = host == 'localhost' || host == '127.0.0.1' || host == '::1';
    return debug && isLoopback;
  }

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
        return await _persist(
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
  ///
  /// [forceRefresh] skips the "already fresh" fast-path and always hits the
  /// provider. The HTTP layer uses it for 401 recovery: the backend rejected a
  /// token that has not yet expired locally, so replaying the cached token would
  /// just 401 again — a new token must be minted.
  Future<OidcLoginOutcome> refresh({bool forceRefresh = false}) {
    if (!isConfigured) {
      return Future.value(const OidcLoginOutcome.failure('No OIDC refresh token available.'));
    }
    return _synchronized(() async {
      final prefs = SharedPreferencesUtil();
      // A concurrent login (e.g. during the redirect) may have already written a
      // fresh token — skip the redundant refresh instead of racing AppAuth. The
      // freshness bar matches getAuthHeader's renewal window (tokenValidityFloor)
      // so a token inside the 5-minute window is refreshed here, not returned
      // stale. A forced refresh (401 recovery) always bypasses the shortcut.
      final freshUntil = _clock().add(tokenValidityFloor).millisecondsSinceEpoch;
      if (!forceRefresh && prefs.authToken.isNotEmpty && prefs.tokenExpirationTime > freshUntil) {
        return OidcLoginOutcome.success(prefs.uid);
      }
      final refreshToken = await _readRefreshToken();
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
        return await _persist(
          accessToken: response.accessToken,
          idToken: response.idToken,
          refreshToken: response.refreshToken ?? refreshToken,
          expiration: response.accessTokenExpirationDateTime,
        );
      } catch (e, s) {
        debugPrint('OIDC refresh failed: $e\n$s');
        return OidcLoginOutcome.failure('OIDC refresh failed: $e', transient: _isTransientRefreshError(e));
      }
    });
  }

  /// Clears the OIDC session locally (best-effort provider end-session).
  ///
  /// Serialized through the same token lock as login/refresh so that clearing
  /// preferences is ordered AFTER any in-flight refresh. Without this a refresh
  /// that completes after logout could re-persist a token (via [_persist]) and
  /// leave the user signed in.
  Future<void> logout() {
    return _synchronized(() async {
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
      await _deleteRefreshToken();
      SharedPreferencesUtil().clearUserDisplayCache();
    });
  }

  String? _lastIdToken;

  Future<OidcLoginOutcome> _persist({
    required String? accessToken,
    required String? idToken,
    required String? refreshToken,
    required DateTime? expiration,
  }) async {
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
    await _writeRefreshToken(refreshToken ?? '');
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

  /// True when the failure is likely temporary (network/timeout) rather than a definitive
  /// invalid/expired refresh token. Callers use it to retry instead of forcing a re-login.
  final bool transient;

  const OidcLoginOutcome.success(this.uid)
      : ok = true,
        error = null,
        transient = false;

  const OidcLoginOutcome.failure(this.error, {this.transient = false})
      : ok = false,
        uid = null;
}

/// Classify a caught refresh error: network/timeout is transient (retry, keep session); a clear
/// OAuth grant rejection is definitive (drop the refresh token). Unknown errors default to transient
/// so an ambiguous blip never logs the user out.
bool _isTransientRefreshError(Object e) {
  final text = e.toString().toLowerCase();
  const definitive = [
    'invalid_grant',
    'invalid_token',
    'unauthorized_client',
    'invalid_client',
    'invalid_request',
    'token_expired',
    'invalid refresh',
  ];
  if (definitive.any(text.contains)) return false;
  return true;
}
