import 'dart:convert';

import 'package:flutter_appauth/flutter_appauth.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/oidc_auth_service.dart';

/// Hermetic unit coverage for the additive OIDC login client (ADR-0038),
/// focused on its security-hardening logic: the cleartext-connection decision,
/// the refresh freshness fast-path (incl. forced 401-recovery), the one-time
/// migration of the refresh token out of plaintext prefs into secure storage,
/// and that the long-lived refresh token only ever lands in secure storage.
///
/// All external dependencies (AppAuth, secure storage, wall clock) are injected
/// through `OidcAuthService.forTest`; SharedPreferences uses the in-memory mock.

/// Minimal EnvFields returning an OIDC config with an https issuer so
/// `isConfigured` is true and `refresh`/`login` proceed past the config guard.
class _OidcEnvFields implements EnvFields {
  @override
  String? get authBackend => 'oidc';
  @override
  String? get oidcIssuer => 'https://keycloak.example.test/realms/omi';
  @override
  String? get oidcClientId => 'omi-app';
  @override
  String? get oidcRedirectScheme => 'omiauth';
  @override
  String? get notificationsBackend => 'fcm';

  @override
  String? get openAIAPIKey => null;
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => 'https://api.omi.me/';
  @override
  String? get googleMapsApiKey => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

/// In-memory FlutterAppAuth. Records call counts and the last TokenRequest,
/// and returns canned responses. Subclasses the concrete client (its methods
/// are plain instance methods, so overriding is a clean seam).
class _FakeAppAuth extends FlutterAppAuth {
  _FakeAppAuth({this.tokenResponse, this.tokenError});

  int tokenCalls = 0;
  int endSessionCalls = 0;
  TokenRequest? lastTokenRequest;
  TokenResponse? tokenResponse;
  Object? tokenError;

  @override
  Future<TokenResponse> token(TokenRequest request) async {
    tokenCalls++;
    lastTokenRequest = request;
    if (tokenError != null) throw tokenError!;
    return tokenResponse!;
  }

  @override
  Future<EndSessionResponse> endSession(EndSessionRequest request) async {
    endSessionCalls++;
    return EndSessionResponse(null);
  }
}

/// In-memory FlutterSecureStorage over a Map. Overrides only the three methods
/// the service touches; the full named-parameter signatures are reproduced so
/// the overrides are valid against the concrete superclass.
class _FakeSecureStorage extends FlutterSecureStorage {
  final Map<String, String> store = <String, String>{};

  @override
  Future<String?> read({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async =>
      store[key];

  @override
  Future<void> write({
    required String key,
    required String? value,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (value == null) {
      store.remove(key);
    } else {
      store[key] = value;
    }
  }

  @override
  Future<void> delete({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    store.remove(key);
  }
}

/// Builds an unsigned JWT (`header.payload.sig`) carrying [claims]. The service
/// only base64url-decodes the payload to read display claims/`sub` — it never
/// verifies the signature (JWKS is the backend's job, ADR-0034).
String _jwt(Map<String, dynamic> claims) {
  String seg(Map<String, dynamic> m) => base64Url.encode(utf8.encode(jsonEncode(m)));
  return '${seg(<String, dynamic>{'alg': 'none'})}.${seg(claims)}.sig';
}

const String _refreshTokenPrefKey = 'oidcRefreshToken';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    Env.init(_OidcEnvFields());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await SharedPreferencesUtil.init();
  });

  group('allowInsecureFor (cleartext decision)', () {
    test('https issuer is always strict', () {
      expect(OidcAuthService.allowInsecureFor('https://keycloak.local/realms/omi', debug: true), isFalse);
      expect(OidcAuthService.allowInsecureFor('https://localhost/realms/omi', debug: true), isFalse);
    });

    test('http loopback issuer is permitted only in debug builds', () {
      expect(OidcAuthService.allowInsecureFor('http://localhost:8080/realms/omi', debug: true), isTrue);
      expect(OidcAuthService.allowInsecureFor('http://localhost:8080/realms/omi', debug: false), isFalse);
      expect(OidcAuthService.allowInsecureFor('http://127.0.0.1:8080/realms/omi', debug: true), isTrue);
      expect(OidcAuthService.allowInsecureFor('http://[::1]:8080/realms/omi', debug: true), isTrue);
    });

    test('http non-loopback issuer stays strict even in debug', () {
      expect(OidcAuthService.allowInsecureFor('http://192.168.0.5:8080/realms/omi', debug: true), isFalse);
      expect(OidcAuthService.allowInsecureFor('http://keycloak.example.test/realms/omi', debug: true), isFalse);
    });

    test('null / empty issuer is strict', () {
      expect(OidcAuthService.allowInsecureFor(null, debug: true), isFalse);
      expect(OidcAuthService.allowInsecureFor('', debug: true), isFalse);
    });
  });

  group('refresh fast-path (freshness floor)', () {
    final DateTime now = DateTime.utc(2026, 1, 1, 12, 0, 0);

    test('a cached token valid beyond the 5-min floor short-circuits without hitting AppAuth', () async {
      final prefs = SharedPreferencesUtil();
      prefs.uid = 'user-fresh';
      prefs.authToken = 'access-fresh';
      prefs.tokenExpirationTime = now.add(const Duration(minutes: 10)).millisecondsSinceEpoch;

      final appAuth = _FakeAppAuth();
      final storage = _FakeSecureStorage()..store[_refreshTokenPrefKey] = 'rt-1';
      final service = OidcAuthService.forTest(appAuth: appAuth, secureStorage: storage, clock: () => now);

      final outcome = await service.refresh();

      expect(outcome.ok, isTrue);
      expect(outcome.uid, 'user-fresh');
      expect(appAuth.tokenCalls, 0, reason: 'fresh cached token must not hit the provider');
    });

    test('a token expiring within the 5-min floor forces a provider refresh', () async {
      final prefs = SharedPreferencesUtil();
      prefs.uid = 'user-stale';
      prefs.authToken = 'access-stale';
      prefs.tokenExpirationTime = now.add(const Duration(minutes: 2)).millisecondsSinceEpoch;

      final appAuth = _FakeAppAuth(
        tokenResponse: TokenResponse(
          'access-new',
          'rt-2',
          now.add(const Duration(hours: 1)),
          _jwt(<String, dynamic>{'sub': 'user-stale'}),
          'Bearer',
          null,
          null,
        ),
      );
      final storage = _FakeSecureStorage()..store[_refreshTokenPrefKey] = 'rt-1';
      final service = OidcAuthService.forTest(appAuth: appAuth, secureStorage: storage, clock: () => now);

      final outcome = await service.refresh();

      expect(outcome.ok, isTrue);
      expect(appAuth.tokenCalls, 1, reason: 'a token inside the renewal window must be refreshed');
    });

    test('forceRefresh always hits the provider even when the cached token is fresh (401 recovery)', () async {
      final prefs = SharedPreferencesUtil();
      prefs.uid = 'user-fresh';
      prefs.authToken = 'access-fresh';
      prefs.tokenExpirationTime = now.add(const Duration(minutes: 10)).millisecondsSinceEpoch;

      final appAuth = _FakeAppAuth(
        tokenResponse: TokenResponse(
          'access-new',
          'rt-2',
          now.add(const Duration(hours: 1)),
          _jwt(<String, dynamic>{'sub': 'user-fresh'}),
          'Bearer',
          null,
          null,
        ),
      );
      final storage = _FakeSecureStorage()..store[_refreshTokenPrefKey] = 'rt-1';
      final service = OidcAuthService.forTest(appAuth: appAuth, secureStorage: storage, clock: () => now);

      final outcome = await service.refresh(forceRefresh: true);

      expect(outcome.ok, isTrue);
      expect(appAuth.tokenCalls, 1, reason: 'forced refresh bypasses the fast-path');
    });
  });

  group('refresh failure classification (transient vs definitive)', () {
    final DateTime now = DateTime.utc(2026, 1, 1, 12, 0, 0);

    Future<OidcLoginOutcome> refreshWithError(Object error) async {
      final prefs = SharedPreferencesUtil();
      prefs.uid = 'user-fail';
      prefs.authToken = 'access-expired';
      prefs.tokenExpirationTime = now.subtract(const Duration(minutes: 1)).millisecondsSinceEpoch;
      final appAuth = _FakeAppAuth(tokenError: error);
      final storage = _FakeSecureStorage()..store[_refreshTokenPrefKey] = 'rt-1';
      final service = OidcAuthService.forTest(appAuth: appAuth, secureStorage: storage, clock: () => now);
      return service.refresh(forceRefresh: true);
    }

    test('a network-class failure is transient (retry, never a terminal logout)', () async {
      final outcome = await refreshWithError(Exception('Connection refused'));
      expect(outcome.ok, isFalse);
      expect(outcome.transient, isTrue);
    });

    test('an invalid_grant is definitive (drop the refresh token)', () async {
      final outcome = await refreshWithError(Exception('invalid_grant: refresh token revoked'));
      expect(outcome.ok, isFalse);
      expect(outcome.transient, isFalse);
    });
  });

  group('refresh-token migration (plaintext prefs -> secure storage)', () {
    final DateTime now = DateTime.utc(2026, 1, 1, 12, 0, 0);

    test('legacy plaintext token is read, moved to secure storage, and the pref is scrubbed', () async {
      final prefs = SharedPreferencesUtil();
      await prefs.saveString(_refreshTokenPrefKey, 'legacy-rt'); // pre-existing plaintext session

      // Response returns no refresh token, so _persist re-writes the one we
      // refreshed with — proving the migrated value reached secure storage.
      final appAuth = _FakeAppAuth(
        tokenResponse: TokenResponse(
          'access-new',
          null,
          now.add(const Duration(hours: 1)),
          _jwt(<String, dynamic>{'sub': 'user-legacy'}),
          'Bearer',
          null,
          null,
        ),
      );
      final storage = _FakeSecureStorage(); // starts empty
      final service = OidcAuthService.forTest(appAuth: appAuth, secureStorage: storage, clock: () => now);

      final outcome = await service.refresh(forceRefresh: true);

      expect(outcome.ok, isTrue);
      expect(appAuth.lastTokenRequest?.refreshToken, 'legacy-rt',
          reason: 'the refresh must use the token migrated from the legacy pref');
      expect(SharedPreferencesUtil().getString(_refreshTokenPrefKey), '', reason: 'the plaintext pref must be scrubbed');
      expect(storage.store[_refreshTokenPrefKey], 'legacy-rt', reason: 'the token must live in secure storage');
    });
  });

  group('_persist (via refresh success)', () {
    final DateTime now = DateTime.utc(2026, 1, 1, 12, 0, 0);

    test('refresh token lands in secure storage, prefs pref stays empty, session claims persisted', () async {
      final DateTime expiry = now.add(const Duration(minutes: 30));
      final appAuth = _FakeAppAuth(
        tokenResponse: TokenResponse(
          'access-42',
          'rt-2',
          expiry,
          _jwt(<String, dynamic>{'sub': 'user-42', 'email': 'u42@example.test', 'given_name': 'Ada Lovelace'}),
          'Bearer',
          null,
          null,
        ),
      );
      final storage = _FakeSecureStorage()..store[_refreshTokenPrefKey] = 'rt-1';
      final service = OidcAuthService.forTest(appAuth: appAuth, secureStorage: storage, clock: () => now);

      final outcome = await service.refresh(forceRefresh: true);
      final prefs = SharedPreferencesUtil();

      expect(outcome.ok, isTrue);
      expect(storage.store[_refreshTokenPrefKey], 'rt-2', reason: 'new refresh token stored in secure storage');
      expect(prefs.getString(_refreshTokenPrefKey), '', reason: 'refresh token must NEVER be written to plaintext prefs');
      expect(prefs.uid, 'user-42');
      expect(prefs.authToken, 'access-42');
      expect(prefs.tokenExpirationTime, expiry.millisecondsSinceEpoch);
      expect(prefs.email, 'u42@example.test');
      expect(prefs.givenName, 'Ada'); // first token of the display name
    });
  });

  group('logout', () {
    final DateTime now = DateTime.utc(2026, 1, 1, 12, 0, 0);

    test('deletes the refresh token from secure storage and clears the session', () async {
      // Establish a session first (also sets the id-token hint used by endSession).
      final appAuth = _FakeAppAuth(
        tokenResponse: TokenResponse(
          'access-99',
          'rt-9',
          now.add(const Duration(hours: 1)),
          _jwt(<String, dynamic>{'sub': 'user-99'}),
          'Bearer',
          null,
          null,
        ),
      );
      final storage = _FakeSecureStorage()..store[_refreshTokenPrefKey] = 'rt-old';
      final service = OidcAuthService.forTest(appAuth: appAuth, secureStorage: storage, clock: () => now);

      await service.refresh(forceRefresh: true);
      expect(storage.store.containsKey(_refreshTokenPrefKey), isTrue);
      expect(SharedPreferencesUtil().authToken, isNotEmpty);

      await service.logout();

      expect(storage.store.containsKey(_refreshTokenPrefKey), isFalse,
          reason: 'refresh token deleted from secure storage');
      expect(appAuth.endSessionCalls, 1, reason: 'best-effort provider end-session called with the id-token hint');
      final prefs = SharedPreferencesUtil();
      expect(prefs.authToken, isEmpty);
      expect(prefs.uid, isEmpty);
      expect(prefs.getString(_refreshTokenPrefKey), isEmpty);
    });
  });
}
