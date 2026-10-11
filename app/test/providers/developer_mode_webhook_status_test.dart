import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/developer_mode_provider.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  setUpAll(() => Env.init(_UnreachableApiEnv()));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('a failed status read keeps the webhooks the user has on', () async {
    SharedPreferencesUtil().conversationEventsToggled = true;
    SharedPreferencesUtil().transcriptsToggled = true;
    SharedPreferencesUtil().audioBytesToggled = true;
    SharedPreferencesUtil().daySummaryToggled = true;
    final provider = DeveloperModeProvider();
    addTearDown(provider.dispose);
    provider.conversationEventsToggled = true;
    provider.transcriptsToggled = true;
    provider.audioBytesToggled = true;
    provider.daySummaryToggled = true;

    await provider.getWebhooksStatus();

    expect(provider.conversationEventsToggled, isTrue);
    expect(provider.transcriptsToggled, isTrue);
    expect(provider.audioBytesToggled, isTrue);
    expect(provider.daySummaryToggled, isTrue);
    expect(SharedPreferencesUtil().conversationEventsToggled, isTrue);
    expect(SharedPreferencesUtil().transcriptsToggled, isTrue);
    expect(SharedPreferencesUtil().audioBytesToggled, isTrue);
    expect(SharedPreferencesUtil().daySummaryToggled, isTrue);
  });
}
