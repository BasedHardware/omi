import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/action_items.dart' as action_items_api;
import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
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
    AuthService.installLocalHarnessTokenGateway(_RetryTokenGateway());
  });

  group('expensive read retry policy', () {
    late HttpServer server;

    setUp(() async {
      server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      Env.overrideApiBaseUrl('http://${server.address.host}:${server.port}/');
    });

    tearDown(() async {
      await server.close(force: true);
      Env.clearApiBaseUrlOverride();
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

      await expectLater(KnowledgeGraphApi.getKnowledgeGraph(), throwsA(isA<Exception>()));

      expect(attempts, 1);
    });

    test('canonical recovery makes no retries when that read returns 504', () async {
      final paths = <String>[];
      server.listen((request) async {
        paths.add(request.uri.path);
        if (request.uri.path == '/v1/knowledge-graph') {
          request.response.write('{"nodes":[],"edges":[]}');
        } else {
          request.response.statusCode = HttpStatus.gatewayTimeout;
        }
        await request.response.close();
      });

      await expectLater(KnowledgeGraphApi.getKnowledgeGraph(), throwsA(isA<Exception>()));

      expect(paths, ['/v1/knowledge-graph', '/v1/knowledge-graph/canonical']);
    });
  });
}

class _RetryTokenGateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot get currentUser => const AuthUserSnapshot(uid: 'retry-test-user');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async =>
      RefreshedAuthToken(token: 'retry-test-token', expirationTime: DateTime.now().add(const Duration(hours: 1)));

  @override
  Future<void> signOut() async {}
}

class _TestEnvFields implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.test.invalid/';

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
