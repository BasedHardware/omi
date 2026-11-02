import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _TestEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  late HttpServer server;
  late List<String> requests;
  late Future<void> answer;

  setUpAll(() {
    Env.init(_TestEnv());
    PlatformManager.initializeForLocalHarness();
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    requests = [];
    answer = Future<void>.value();
    // Answers like the backend's webhook enable/disable routes: 200 {"status": "ok"}.
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((request) async {
      requests.add('${request.method} ${request.uri.path}');
      await request.drain<void>();
      await answer;
      request.response
        ..statusCode = 200
        ..headers.contentType = ContentType.json
        ..write(jsonEncode({'status': 'ok'}));
      await request.response.close();
    });
    Env.overrideApiBaseUrl('http://127.0.0.1:${server.port}/');
  });

  tearDown(() async {
    Env.clearApiBaseUrlOverrideForTesting();
    await server.close(force: true);
  });

  test('a webhook switch the server confirmed stays where it was flipped', () async {
    final provider = DeveloperModeProvider();
    addTearDown(provider.dispose);
    provider.transcriptsToggled = true;
    provider.daySummaryToggled = true;

    await provider.onConversationEventsToggled(true);
    await provider.onTranscriptsToggled(false);
    await provider.onAudioBytesToggled(true);
    await provider.onDaySummaryToggled(false);

    expect(provider.conversationEventsToggled, isTrue);
    expect(provider.transcriptsToggled, isFalse);
    expect(provider.audioBytesToggled, isTrue);
    expect(provider.daySummaryToggled, isFalse);
    expect(requests, [
      'POST /v1/users/developer/webhook/memory_created/enable',
      'POST /v1/users/developer/webhook/realtime_transcript/disable',
      'POST /v1/users/developer/webhook/audio_bytes/enable',
      'POST /v1/users/developer/webhook/day_summary/disable',
    ]);
  });

  test('a second tap while that webhook is still switching is ignored', () async {
    final release = Completer<void>();
    answer = release.future;
    final provider = DeveloperModeProvider();
    addTearDown(provider.dispose);

    final turningOn = provider.onConversationEventsToggled(true);
    final turningOff = provider.onConversationEventsToggled(false);
    expect(provider.conversationEventsToggled, isTrue);
    release.complete();
    await Future.wait([turningOn, turningOff]);

    expect(provider.conversationEventsToggled, isTrue);
    expect(requests, ['POST /v1/users/developer/webhook/memory_created/enable']);
  });
}
