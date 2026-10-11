import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// The backend fences every request of an account whose deletion wipe is
/// pending or failed with `403 {"detail": {"code": "account_deletion_in_progress"}}`
/// (`enforce_account_deletion_http_access`). Before this guard the app parsed
/// that body as "no language set", forced the un-dismissable language sheet,
/// and every save failed: a signed-in dead account with no way out.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const fenceBody = '{"detail": {"code": "account_deletion_in_progress", "status": "failed", "retryable": false}}';

  setUpAll(() async {
    Env.init(_TestEnvFields());
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
    await PlatformManager.initializeServices();
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('accountDeletionStatusOf', () {
    test('reads the wipe status out of the fence body', () {
      expect(accountDeletionStatusOf(fenceBody), 'failed');
      expect(accountDeletionStatusOf('{"detail": {"code": "account_deletion_in_progress"}}'), '');
    });

    test('is null for every other 403 shape', () {
      expect(accountDeletionStatusOf(''), isNull);
      expect(accountDeletionStatusOf('not json'), isNull);
      expect(accountDeletionStatusOf('{"detail": "Forbidden"}'), isNull);
      expect(accountDeletionStatusOf('{"detail": {"code": "ownership"}}'), isNull);
      expect(accountDeletionStatusOf('[1, 2]'), isNull);
    });
  });

  group('sendUncaughtApiCall', () {
    test('403 account_deletion_in_progress expires the session once with reason accountDeleted', () async {
      final gateway = _Gateway();
      final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
      final events = <AuthSessionExpiredEvent>[];
      service.sessionExpiredEvents.listen(events.add);
      final seams = _seams(service, statusCode: HttpStatus.forbidden, body: fenceBody);

      final first = await sendUncaughtApiCall(
          url: 'https://api.omi.me/v1/users/language', headers: {}, body: '', method: 'GET', execution: seams);
      final second = await sendUncaughtApiCall(
          url: 'https://api.omi.me/v1/users/language', headers: {}, body: '{}', method: 'PATCH', execution: seams);

      // The caller still sees the 403 it would have seen before the guard.
      expect(first.statusCode, HttpStatus.forbidden);
      expect(second.statusCode, HttpStatus.forbidden);
      expect(events, hasLength(1), reason: 'expireSession is idempotent: one sign-out per session');
      expect(events.single.reason, AuthSessionExpirationReason.accountDeleted);
      expect(events.single.code, 'failed');
      expect(gateway.signOutCalls, 1);
    });

    test('a plain 403 leaves the session alone', () async {
      final gateway = _Gateway();
      final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
      final events = <AuthSessionExpiredEvent>[];
      service.sessionExpiredEvents.listen(events.add);
      final seams = _seams(service, statusCode: HttpStatus.forbidden, body: '{"detail": "Not your conversation"}');

      final response = await sendUncaughtApiCall(
          url: 'https://api.omi.me/v1/conversations/x', headers: {}, body: '', method: 'GET', execution: seams);

      expect(response.statusCode, HttpStatus.forbidden);
      expect(events, isEmpty);
      expect(gateway.signOutCalls, 0);
    });
  });

  group('makeRawApiCall (streamed)', () {
    test('403 account_deletion_in_progress expires the session and hands back the same body', () async {
      final gateway = _Gateway();
      final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
      final events = <AuthSessionExpiredEvent>[];
      service.sessionExpiredEvents.listen(events.add);
      final snapshot = service.captureSessionSnapshot()!;
      SharedPreferencesUtil().authToken = _tokenWithExpiry(DateTime.now().add(const Duration(hours: 1)));

      final response = await makeRawApiCall(
        url: 'https://api.omi.me/v2/messages',
        method: 'POST',
        body: '{}',
        sessionSnapshot: snapshot,
        authService: service,
        sendStreaming: (request) async => http.StreamedResponse(
          Stream<List<int>>.value(utf8.encode(fenceBody)),
          HttpStatus.forbidden,
          headers: const {'content-type': 'application/json'},
        ),
      );

      expect(response.statusCode, HttpStatus.forbidden);
      expect(await response.stream.bytesToString(), fenceBody);
      expect(response.headers['content-type'], 'application/json');
      expect(events.single.reason, AuthSessionExpirationReason.accountDeleted);
    });

    test('a plain streamed 403 is passed through untouched', () async {
      final gateway = _Gateway();
      final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
      final events = <AuthSessionExpiredEvent>[];
      service.sessionExpiredEvents.listen(events.add);
      final snapshot = service.captureSessionSnapshot()!;
      SharedPreferencesUtil().authToken = _tokenWithExpiry(DateTime.now().add(const Duration(hours: 1)));

      final response = await makeRawApiCall(
        url: 'https://api.omi.me/v2/messages',
        method: 'POST',
        body: '{}',
        sessionSnapshot: snapshot,
        authService: service,
        sendStreaming: (request) async => http.StreamedResponse(
          Stream<List<int>>.value(utf8.encode('{"detail": "Forbidden"}')),
          HttpStatus.forbidden,
        ),
      );

      expect(response.statusCode, HttpStatus.forbidden);
      expect(await response.stream.bytesToString(), '{"detail": "Forbidden"}');
      expect(events, isEmpty);
    });
  });
}

ApiExecutionSeams _seams(AuthService auth, {required int statusCode, required String body}) => ApiExecutionSeams(
      transport: (request) async => http.Response(body, statusCode),
      headers: (request) async => {'Authorization': 'Bearer t', ...request.headers},
      auth: auth,
    );

String _tokenWithExpiry(DateTime expiry) {
  final payload = base64Url.encode(utf8.encode(jsonEncode({'exp': expiry.millisecondsSinceEpoch ~/ 1000})));
  return 'header.${base64Url.normalize(payload)}.signature';
}

final class _Gateway implements AuthTokenGateway {
  int signOutCalls = 0;

  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'fence-user');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async =>
      RefreshedAuthToken(token: 'fresh-token', expirationTime: DateTime.now().add(const Duration(hours: 1)));

  @override
  Future<void> signOut() async {
    signOutCalls++;
  }
}

class _TestEnvFields implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://auth-not-required.invalid/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}
