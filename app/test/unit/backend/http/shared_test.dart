import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/http/clock_skew_detector.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/auth/auth_token_result.dart';
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
  });

  group('streaming clock-skew detection', () {
    late HttpServer server;

    setUp(() async {
      server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      env.routeNextRequestTo('http://${server.address.host}:${server.port}/');
      server.listen((request) async {
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
      final url = '${env.apiBaseUrl!}clock-skew';
      final eventFuture = nextClockSkewEvent();

      final chunks = await makeStreamingApiCall(url: url).toList();
      final event = await eventFuture;

      expect(chunks, isEmpty);
      expect(event.skewMinutes, 15);
    });

    test('multipart streaming requests report clock skew before returning', () async {
      final file = File('${Directory.systemTemp.path}/omi-clock-skew-test.txt');
      await file.writeAsString('test');
      addTearDown(() => file.delete().ignore());
      final url = '${env.apiBaseUrl!}clock-skew';
      final eventFuture = nextClockSkewEvent();

      final chunks = await makeMultipartStreamingApiCall(url: url, files: [file]).toList();
      final event = await eventFuture;

      expect(chunks, isEmpty);
      expect(event.skewMinutes, 15);
    });
  });
}

class _TestEnvFields implements EnvFields {
  String _requestBaseUrl = '';
  var _apiBaseUrlReads = 0;

  void routeNextRequestTo(String baseUrl) {
    _requestBaseUrl = baseUrl;
    _apiBaseUrlReads = 0;
  }

  @override
  String? get apiBaseUrl {
    _apiBaseUrlReads++;
    // The first read builds the request URL; the second read in
    // _isRequiredAuthCheck intentionally returns a non-matching URL so these
    // loopback tests do not need Firebase credentials.
    return _apiBaseUrlReads.isOdd ? _requestBaseUrl : 'https://auth-not-required.invalid/';
  }

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get googleMapsApiKey => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get openAIAPIKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}
