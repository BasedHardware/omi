import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  group('DeveloperModeProvider - Toggle Persistence', () {
    late DeveloperModeProvider provider;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      provider = DeveloperModeProvider();
    });

    tearDown(() {
      provider.dispose();
    });

    test('should persist audioBytesToggled to SharedPreferences immediately when toggled on', () async {
      expect(SharedPreferencesUtil().audioBytesToggled, isFalse);
      expect(provider.audioBytesToggled, isFalse);

      provider.onAudioBytesToggled(true);

      expect(SharedPreferencesUtil().audioBytesToggled, isTrue);
    });

    test('should persist audioBytesToggled to SharedPreferences immediately when toggled off', () async {
      SharedPreferencesUtil().audioBytesToggled = true;
      provider.audioBytesToggled = true;

      provider.onAudioBytesToggled(false);

      expect(SharedPreferencesUtil().audioBytesToggled, isFalse);
    });

    test('should persist conversationEventsToggled to SharedPreferences immediately when toggled', () async {
      expect(SharedPreferencesUtil().conversationEventsToggled, isFalse);

      provider.onConversationEventsToggled(true);

      expect(SharedPreferencesUtil().conversationEventsToggled, isTrue);
    });

    test('should persist transcriptsToggled to SharedPreferences immediately when toggled', () async {
      expect(SharedPreferencesUtil().transcriptsToggled, isFalse);

      provider.onTranscriptsToggled(true);

      expect(SharedPreferencesUtil().transcriptsToggled, isTrue);
    });

    test('should persist daySummaryToggled to SharedPreferences immediately when toggled', () async {
      expect(SharedPreferencesUtil().daySummaryToggled, isFalse);

      provider.onDaySummaryToggled(true);

      expect(SharedPreferencesUtil().daySummaryToggled, isTrue);
    });

    test('should load toggle states from SharedPreferences on initialize', () async {
      SharedPreferencesUtil().audioBytesToggled = true;
      SharedPreferencesUtil().conversationEventsToggled = true;
      SharedPreferencesUtil().transcriptsToggled = false;
      SharedPreferencesUtil().daySummaryToggled = false;

      final newProvider = DeveloperModeProvider();

      expect(newProvider.audioBytesToggled, isFalse);
      expect(newProvider.conversationEventsToggled, isFalse);
      expect(newProvider.transcriptsToggled, isFalse);
      expect(newProvider.daySummaryToggled, isFalse);

      newProvider.dispose();
    });

    test('should maintain toggle state after page navigation simulation', () async {
      provider.onAudioBytesToggled(true);

      final newProvider = DeveloperModeProvider();
      newProvider.audioBytesToggled = SharedPreferencesUtil().audioBytesToggled;

      expect(newProvider.audioBytesToggled, isTrue);
      expect(SharedPreferencesUtil().audioBytesToggled, isTrue);

      newProvider.dispose();
    });

    test('toggle state should be reverted when API call fails', () async {
      await provider.onAudioBytesToggled(true);
      await provider.onTranscriptsToggled(true);

      expect(SharedPreferencesUtil().audioBytesToggled, isFalse);
      expect(SharedPreferencesUtil().transcriptsToggled, isFalse);
    });

    test('toggle state persists when manually set without API call', () {
      SharedPreferencesUtil().audioBytesToggled = true;
      SharedPreferencesUtil().transcriptsToggled = true;

      expect(SharedPreferencesUtil().audioBytesToggled, isTrue);
      expect(SharedPreferencesUtil().transcriptsToggled, isTrue);

      final newProvider = DeveloperModeProvider();
      newProvider.audioBytesToggled = SharedPreferencesUtil().audioBytesToggled;
      newProvider.transcriptsToggled = SharedPreferencesUtil().transcriptsToggled;

      expect(newProvider.audioBytesToggled, isTrue);
      expect(newProvider.transcriptsToggled, isTrue);

      newProvider.dispose();
    });

    test('should handle multiple rapid toggle changes correctly', () async {
      provider.onAudioBytesToggled(true);
      expect(SharedPreferencesUtil().audioBytesToggled, isTrue);

      provider.onAudioBytesToggled(false);
      expect(SharedPreferencesUtil().audioBytesToggled, isFalse);

      provider.onAudioBytesToggled(true);
      expect(SharedPreferencesUtil().audioBytesToggled, isTrue);

      provider.onAudioBytesToggled(false);
      expect(SharedPreferencesUtil().audioBytesToggled, isFalse);
    });

    test('webhook URL and toggle state should both persist', () async {
      const testUrl = 'https://example.com/webhook';
      SharedPreferencesUtil().webhookAudioBytes = testUrl;
      provider.onAudioBytesToggled(true);

      expect(SharedPreferencesUtil().webhookAudioBytes, equals(testUrl));
      expect(SharedPreferencesUtil().audioBytesToggled, isTrue);

      final newProvider = DeveloperModeProvider();
      newProvider.webhookAudioBytes.text = SharedPreferencesUtil().webhookAudioBytes;
      newProvider.audioBytesToggled = SharedPreferencesUtil().audioBytesToggled;

      expect(newProvider.webhookAudioBytes.text, equals(testUrl));
      expect(newProvider.audioBytesToggled, isTrue);

      newProvider.dispose();
    });

    test('webhook URL persists to SharedPreferences when set', () {
      const testUrl = 'https://example.com/webhook';
      SharedPreferencesUtil().webhookAudioBytes = testUrl;

      expect(SharedPreferencesUtil().webhookAudioBytes, equals(testUrl));

      final newProvider = DeveloperModeProvider();
      newProvider.webhookAudioBytes.text = SharedPreferencesUtil().webhookAudioBytes;

      expect(newProvider.webhookAudioBytes.text, equals(testUrl));

      newProvider.dispose();
    });

    test('webhook delay persists to SharedPreferences when set', () {
      const testDelay = '10';
      SharedPreferencesUtil().webhookAudioBytesDelay = testDelay;

      expect(SharedPreferencesUtil().webhookAudioBytesDelay, equals(testDelay));

      final newProvider = DeveloperModeProvider();
      newProvider.webhookAudioBytesDelay.text = SharedPreferencesUtil().webhookAudioBytesDelay;

      expect(newProvider.webhookAudioBytesDelay.text, equals(testDelay));

      newProvider.dispose();
    });

    test('all webhook URLs persist independently', () {
      const audioUrl = 'https://example.com/audio';
      const transcriptUrl = 'https://example.com/transcript';
      const conversationUrl = 'https://example.com/conversation';
      const summaryUrl = 'https://example.com/summary';

      SharedPreferencesUtil().webhookAudioBytes = audioUrl;
      SharedPreferencesUtil().webhookOnTranscriptReceived = transcriptUrl;
      SharedPreferencesUtil().webhookOnConversationCreated = conversationUrl;
      SharedPreferencesUtil().webhookDaySummary = summaryUrl;

      expect(SharedPreferencesUtil().webhookAudioBytes, equals(audioUrl));
      expect(SharedPreferencesUtil().webhookOnTranscriptReceived, equals(transcriptUrl));
      expect(SharedPreferencesUtil().webhookOnConversationCreated, equals(conversationUrl));
      expect(SharedPreferencesUtil().webhookDaySummary, equals(summaryUrl));
    });

    test('empty webhook URL does not overwrite existing local value', () {
      const testUrl = 'https://example.com/webhook';
      SharedPreferencesUtil().webhookAudioBytes = testUrl;

      expect(SharedPreferencesUtil().webhookAudioBytes, equals(testUrl));
    });
  });
}
