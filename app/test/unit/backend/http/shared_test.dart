import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/http/clock_skew_detector.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';

Future<String> simulateGetAuthHeader({required bool isSignedIn, required String token}) async {
  if (token.isEmpty && isSignedIn) {
    throw AuthTokenUnavailableException(const AuthTokenMissingToken());
  }
  return 'Bearer $token';
}

Future<Map<String, String>> simulateBuildHeaders({required Future<String> Function() getAuthHeader}) async {
  final headers = <String, String>{};
  // Mirrors buildHeaders(): auth failure aborts header construction so no
  // authenticated request can degrade into anonymous traffic.
  headers['Authorization'] = await getAuthHeader();
  return headers;
}

void main() {
  final env = _TestEnvFields();

  setUpAll(() async {
    Env.init(env);
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
    await PlatformManager.initializeServices();
  });

  group('auth header guards', () {
    test('throws AuthTokenUnavailableException when signed in and token missing', () async {
      expect(() => simulateGetAuthHeader(isSignedIn: true, token: ''), throwsA(isA<AuthTokenUnavailableException>()));
    });

    test('header construction propagates AuthTokenUnavailableException instead of omitting auth', () async {
      expect(
        () => simulateBuildHeaders(getAuthHeader: () => simulateGetAuthHeader(isSignedIn: true, token: '')),
        throwsA(isA<AuthTokenUnavailableException>()),
      );
    });

    test('includes Authorization header on happy path', () async {
      final headers = await simulateBuildHeaders(
        getAuthHeader: () => simulateGetAuthHeader(isSignedIn: true, token: 'fresh-token'),
      );

      expect(headers['Authorization'], equals('Bearer fresh-token'));
    });

    test('_drainStreamedResponse suppresses exceptions from aborted streams before replaying', () async {
      var replayCount = 0;
      final service = AuthService.forTesting(tokenGateway: _TestAuthTokenGateway(), refreshDelay: (_) async {});

      final response = await refreshAndReplayAfter401(
        firstResponse: http.StreamedResponse(_abortedResponseBody(), HttpStatus.unauthorized),
        statusCode: (value) => value.statusCode,
        disposeUnauthorizedResponse: drainStreamedResponseForTesting,
        replay: () async {
          replayCount++;
          return http.StreamedResponse(const Stream<List<int>>.empty(), HttpStatus.ok);
        },
        expireTerminalSession: true,
        authService: service,
      );

      expect(response.statusCode, HttpStatus.ok);
      expect(replayCount, 1);
    });
  });

  group('streaming clock-skew detection', () {
    late HttpServer server;
    var requestCount = 0;

    setUp(() async {
      requestCount = 0;
      server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      env.routeNextRequestTo('http://${server.address.host}:${server.port}/');
      server.listen((request) async {
        requestCount++;
        request.response.statusCode = HttpStatus.requestTimeout;
        request.response.headers.contentType = ContentType.json;
        request.response.write(
          jsonEncode({
            'error': 'clock_skew',
            'skew_seconds': 900,
            'server_time': '2026-07-31T02:30:45Z',
            'client_time': '2026-07-30T02:15:45Z',
          }),
        );
        await request.response.close();
      });
    });

    tearDown(() async {
      await server.close(force: true);
    });

    Future<ClockSkewEvent> nextClockSkewEvent() {
      ClockSkewDetector.instance.resetForTesting();
      return ClockSkewDetector.instance.onClockSkew.first.timeout(const Duration(seconds: 2));
    }

    test('typed streaming requests report clock skew before returning', () async {
      final url = '${env.requestBaseUrl}clock-skew';
      final eventFuture = nextClockSkewEvent();

      final chunks = await makeStreamingApiCall(url: url).toList();
      final event = await eventFuture;

      expect(chunks, isEmpty);
      expect(event.skewMinutes, 15);
      expect(requestCount, 1);
    });

    test('multipart streaming requests report clock skew before returning', () async {
      final file = File('${Directory.systemTemp.path}/omi-clock-skew-test.txt');
      await file.writeAsString('test');
      addTearDown(() => file.delete().ignore());
      final url = '${env.requestBaseUrl}clock-skew';
      final eventFuture = nextClockSkewEvent();

      final chunks = await makeMultipartStreamingApiCall(url: url, files: [file]).toList();
      final event = await eventFuture;

      expect(chunks, isEmpty);
      expect(event.skewMinutes, 15);
      expect(requestCount, 1);
    });
  });
}

Stream<List<int>> _abortedResponseBody() async* {
  yield [1, 2, 3];
  throw StateError('aborted response');
}

final class _TestAuthTokenGateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'test-user');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async =>
      RefreshedAuthToken(token: 'fresh-token', expirationTime: DateTime.now().add(const Duration(hours: 1)));

  @override
  Future<void> signOut() async {}
}

class _TestEnvFields implements EnvFields {
  String _requestBaseUrl = '';

  void routeNextRequestTo(String baseUrl) {
    _requestBaseUrl = baseUrl;
  }

  String get requestBaseUrl => _requestBaseUrl;

  @override
  String? get apiBaseUrl => 'https://auth-not-required.invalid/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
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
