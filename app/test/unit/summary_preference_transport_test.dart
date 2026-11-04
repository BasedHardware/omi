import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_generation.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _TestEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.omi.me/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('built-in default is persisted with PUT; explicit Omi clears with DELETE', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    Env.init(_TestEnv());
    final previousOverrides = HttpOverrides.current;
    HttpOverrides.global = null;
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final requests = <String>[];
    server.listen((request) async {
      requests.add('${request.method} ${request.uri}');
      await request.drain<void>();
      request.response
        ..headers.contentType = ContentType.json
        ..write('{"status":"ok"}');
      await request.response.close();
    });
    Env.overrideApiBaseUrl('http://127.0.0.1:${server.port}/');
    try {
      expect(await writeServerPreferredSummaryApp('omi-default-summary'), isTrue);
      expect(await writeServerPreferredSummaryApp(null), isTrue);
      expect(requests, [
        'PUT /v1/users/preferences/app?app_id=omi-default-summary',
        'DELETE /v1/users/preferences/app',
      ]);
    } finally {
      Env.clearApiBaseUrlOverrideForTesting();
      HttpOverrides.global = previousOverrides;
      await server.close(force: true);
    }
  });
}
