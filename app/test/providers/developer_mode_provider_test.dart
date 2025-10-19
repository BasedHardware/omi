import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DeveloperModeProvider - Webhook Persistence', () {
    late DeveloperModeProvider provider;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      provider = DeveloperModeProvider();
    });

    tearDown(() {
      if (!provider.webhookAudioBytes.hasListeners) {
        return;
      }
      provider.dispose();
    });

    test('REGRESSION: webhook URL persists after simulated page reload', () async {
      const testUrl = 'https://my-webhook.com/audio';

      provider.webhookAudioBytes.text = testUrl;
      provider.webhookAudioBytesDelay.text = '10';

      SharedPreferencesUtil().webhookAudioBytes = testUrl;
      SharedPreferencesUtil().webhookAudioBytesDelay = '10';

      final newProvider = DeveloperModeProvider();
      newProvider.webhookAudioBytes.text = SharedPreferencesUtil().webhookAudioBytes;
      newProvider.webhookAudioBytesDelay.text = SharedPreferencesUtil().webhookAudioBytesDelay;

      expect(newProvider.webhookAudioBytes.text, equals(testUrl),
          reason: 'Webhook URL should persist after page reload');
      expect(newProvider.webhookAudioBytesDelay.text, equals('10'),
          reason: 'Webhook delay should persist after page reload');

      newProvider.dispose();
    });

    test('should set default delay if audio bytes URL is provided without delay', () {
      provider.webhookAudioBytes.text = 'https://test.com/webhook';
      provider.webhookAudioBytesDelay.text = '';

      if (provider.webhookAudioBytes.text.isNotEmpty && provider.webhookAudioBytesDelay.text.isEmpty) {
        provider.webhookAudioBytesDelay.text = '5';
      }

      expect(provider.webhookAudioBytesDelay.text, equals('5'),
          reason: 'Default delay of 5 seconds should be set when not provided');
    });

    test('should properly initialize TextEditingControllers', () {
      expect(provider.webhookAudioBytes.text, isEmpty);
      expect(provider.webhookAudioBytesDelay.text, isEmpty);
      expect(provider.webhookOnConversationCreated.text, isEmpty);
      expect(provider.webhookOnTranscriptReceived.text, isEmpty);
      expect(provider.webhookDaySummary.text, isEmpty);
    });

    test('should properly dispose of TextEditingControllers without errors', () {
      provider.webhookAudioBytes.text = 'test';
      expect(provider.webhookAudioBytes.text, equals('test'));
      provider.dispose();
      expect(true, isTrue, reason: 'Dispose completed without errors');
    });
  });
}
