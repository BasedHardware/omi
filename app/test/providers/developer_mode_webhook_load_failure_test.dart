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

/// Skips the webhook on/off read, which these tests do not cover, so the injected URL read and
/// write are the only API calls.
class _NoStatusReadProvider extends DeveloperModeProvider {
  _NoStatusReadProvider({super.fetchWebhookUrl, super.saveWebhookUrl});

  @override
  Future getWebhooksStatus() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() => Env.init(_UnreachableApiEnv()));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('a failed webhook URL read keeps the saved URLs instead of blanking them', () async {
    SharedPreferencesUtil().webhookAudioBytes = 'https://example.com/audio';
    SharedPreferencesUtil().webhookAudioBytesDelay = '10';
    SharedPreferencesUtil().webhookOnTranscriptReceived = 'https://example.com/transcript';
    SharedPreferencesUtil().webhookOnConversationCreated = 'https://example.com/conversation';
    SharedPreferencesUtil().webhookDaySummary = 'https://example.com/day-summary';
    final provider = DeveloperModeProvider();
    addTearDown(provider.dispose);

    // The API is unreachable, so every webhook URL read fails.
    await provider.initialize();

    expect(provider.webhookAudioBytes.text, 'https://example.com/audio');
    expect(provider.webhookAudioBytesDelay.text, '10');
    expect(provider.webhookOnTranscriptReceived.text, 'https://example.com/transcript');
    expect(provider.webhookOnConversationCreated.text, 'https://example.com/conversation');
    expect(provider.webhookDaySummary.text, 'https://example.com/day-summary');
    expect(SharedPreferencesUtil().webhookAudioBytes, 'https://example.com/audio');
    expect(SharedPreferencesUtil().webhookAudioBytesDelay, '10');
    expect(SharedPreferencesUtil().webhookOnTranscriptReceived, 'https://example.com/transcript');
    expect(SharedPreferencesUtil().webhookOnConversationCreated, 'https://example.com/conversation');
    expect(SharedPreferencesUtil().webhookDaySummary, 'https://example.com/day-summary');
  });

  test('Save does not send a webhook whose URL could not be read', () async {
    final sent = <String, String>{};
    final provider = _NoStatusReadProvider(
      fetchWebhookUrl: ({required String type}) async => type == 'memory_created' ? null : '',
      saveWebhookUrl: ({required String type, required String url}) async {
        sent[type] = url;
        return true;
      },
    );
    addTearDown(provider.dispose);
    await provider.initialize();

    provider.webhookOnTranscriptReceived.text = 'https://example.com/transcript';
    expect(await provider.saveSettings(), isTrue);

    // Sending its blank field would clear the conversation webhook on the server and turn it off.
    expect(sent.keys, unorderedEquals(['audio_bytes', 'realtime_transcript', 'day_summary']));
    expect(sent['realtime_transcript'], 'https://example.com/transcript');
  });

  test('a webhook whose URL could not be read is saved once you edit it', () async {
    SharedPreferencesUtil().webhookOnTranscriptReceived = 'https://example.com/old-transcript';
    final sent = <String, String>{};
    final provider = _NoStatusReadProvider(
      fetchWebhookUrl: ({required String type}) async => null,
      saveWebhookUrl: ({required String type, required String url}) async {
        sent[type] = url;
        return true;
      },
    );
    addTearDown(provider.dispose);
    await provider.initialize();

    provider.webhookOnConversationCreated.text = 'https://example.com/conversation';
    expect(await provider.saveSettings(), isTrue);

    // Only the edited webhook is written: the cached transcript URL may be stale, so it is not sent.
    expect(sent, {'memory_created': 'https://example.com/conversation'});
    expect(SharedPreferencesUtil().webhookOnConversationCreated, 'https://example.com/conversation');
  });
}
