import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/http/api/phone_calls.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _LocalEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://auth-not-required.invalid/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

const _secret = 'omi_app_key_SECRET_must_not_be_logged';

/// Responses a secret-bearing endpoint returns on success, keyed by path.
final _responses = <String, Object>{
  '/v1/apps/app-1/keys:POST': {'id': 'key-1', 'label': 'sk_...ged', 'secret': _secret, 'created_at': null},
  '/v1/apps/app-1/keys:GET': [
    {'id': 'key-1', 'label': 'sk_...ged', 'secret': _secret},
  ],
  '/v1/apps/mcp:POST': {'app_id': 'mcp-1', 'requires_oauth': true, 'auth_url': 'https://idp.invalid/a?state=$_secret'},
  '/v1/phone/token:POST': {'access_token': _secret, 'identity': 'user-1', 'ttl': 3600},
  '/v1/apps/app-1:GET': {
    'id': 'app-1',
    'name': 'Backup',
    'author': 'Omi',
    'description': 'Backup fixture',
    'category': 'productivity',
    'image': '',
    'capabilities': ['external_integration'],
    'external_integration': {'auth_steps': [], 'app_home_url': 'https://plugin.invalid/setup?omi_token=$_secret'},
  },
  '/plugin/status:GET': {'is_setup_completed': true},
};

/// Runs [body] while capturing every channel a log line can leave through: the app's [Logger]
/// (talker history), `debugPrint`, and zone `print`.
Future<String> _captureLogs(Future<void> Function() body) async {
  final captured = StringBuffer();
  Logger.instance.talker.cleanHistory();
  final previousDebugPrint = debugPrint;
  debugPrint = (String? message, {int? wrapWidth}) => captured.writeln(message);
  try {
    await runZoned(body, zoneSpecification: ZoneSpecification(print: (_, __, ___, line) => captured.writeln(line)));
  } finally {
    debugPrint = previousDebugPrint;
  }
  for (final entry in Logger.instance.talker.history) {
    captured.writeln(entry.generateTextMessage());
  }
  return captured.toString();
}

void main() {
  late HttpServer server;

  setUpAll(() async {
    Env.init(_LocalEnv());
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
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((request) async {
      final payload = _responses['${request.uri.path}:${request.method}'];
      request.response.statusCode = payload == null ? HttpStatus.notFound : HttpStatus.ok;
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode(payload ?? {'detail': 'not found'}));
      await request.response.close();
    });
    // A runtime override is credential-free, so requests reach the local server unauthenticated.
    Env.overrideApiBaseUrl('http://${server.address.host}:${server.port}/');
  });

  tearDownAll(() async {
    Env.clearApiBaseUrlOverrideForTesting();
    await server.close(force: true);
  });

  test('a created app API key reaches the caller but never the logs', () async {
    Map<String, dynamic>? created;
    final logs = await _captureLogs(() async => created = await createApiKeyServer('app-1'));

    expect(created?['secret'], _secret);
    expect(logs, contains('createApiKeyServer: 200'), reason: 'The status is still logged');
    expect(logs, isNot(contains(_secret)));
  });

  test('listing app API keys never logs a returned secret', () async {
    final logs = await _captureLogs(() async => expect(await listApiKeysServer('app-1'), hasLength(1)));
    expect(logs, isNot(contains(_secret)));
  });

  test('adding an MCP server never logs its OAuth auth_url', () async {
    final logs =
        await _captureLogs(() async => expect((await addMcpServer('n', 'https://mcp.invalid'))?['app_id'], 'mcp-1'));
    expect(logs, isNot(contains(_secret)));
  });

  test('a minted phone call token never reaches the logs', () async {
    final logs = await _captureLogs(() async => expect((await getPhoneCallToken()).token, isNotNull));
    expect(logs, isNot(contains(_secret)));
  });

  test('fresh app details return the launch grant without logging it', () async {
    Map<String, dynamic>? detail;
    final logs = await _captureLogs(() async => detail = await getAppDetailsServer('app-1'));
    expect((detail?['external_integration'] as Map)['app_home_url'], contains(_secret));
    expect(logs, contains('getAppDetailsServer: 200'));
    expect(logs, isNot(contains(_secret)));
  });

  test('vendor completion uses the real HTTP pool without forwarding an Omi bearer or logging the grant', () async {
    final vendor = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    String? authorization;
    vendor.listen((request) async {
      authorization = request.headers.value(HttpHeaders.authorizationHeader);
      expect(request.uri.queryParameters['omi_token'], _secret);
      request.response.headers.contentType = ContentType.json;
      request.response.write('{"is_setup_completed":true}');
      await request.response.close();
    });
    try {
      final logs = await _captureLogs(() async => expect(
          await getAppSetupStatus('http://${vendor.address.host}:${vendor.port}/plugin/status?omi_token=$_secret'),
          isA<ApiSuccess<AppSetupStatus>>().having((result) => result.data, 'status', AppSetupStatus.completed)));
      expect(authorization, isNull);
      expect(logs, isNot(contains(_secret)));
    } finally {
      await vendor.close(force: true);
    }
  });
}
