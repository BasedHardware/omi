import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/action_items.dart' as action_items_api;
import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/platform/platform_manager.dart';

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

  group('expensive read retry policy', () {
    late HttpServer server;

    setUp(() async {
      server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      env.routeNextRequestTo(
        'http://${server.address.host}:${server.port}/',
      );
    });

    tearDown(() async {
      await server.close(force: true);
    });

    test('tryGetActionItems makes one request when the backend returns 504', () async {
      var attempts = 0;
      server.listen((request) async {
        attempts++;
        expect(request.uri.path, '/v1/action-items');
        request.response.statusCode = HttpStatus.gatewayTimeout;
        await request.response.close();
      });

      final response = await action_items_api.tryGetActionItems();

      expect(response, isNull);
      expect(attempts, 1);
    });

    test('getKnowledgeGraph makes one request when the backend returns 504', () async {
      var attempts = 0;
      server.listen((request) async {
        attempts++;
        expect(request.uri.path, '/v1/knowledge-graph');
        request.response.statusCode = HttpStatus.gatewayTimeout;
        await request.response.close();
      });

      await expectLater(
        KnowledgeGraphApi.getKnowledgeGraph(),
        throwsA(isA<Exception>()),
      );

      expect(attempts, 1);
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
    // The production API uses the first read to build the request URL and the
    // second to decide whether auth is required. Returning a distinct base on
    // the second read keeps this loopback test focused on retry behavior.
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
