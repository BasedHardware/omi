import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/stt_response_schema.dart';

void main() {
  group('OpenAI GPT-Live live provider', () {
    test('is offered as the live OpenAI provider', () {
      final config = SttProviderConfig.get(SttProvider.gptLive);

      expect(config.isLive, isTrue);
      expect(config.displayName, 'OpenAI GPT-Live');
      expect(config.requestType, SttRequestType.streaming);
      expect(config.defaultModel, 'gpt-live-1');
      expect(config.supportedModels, contains('gpt-live-1'));
      expect(config.defaultLanguage, 'en');
      expect(config.supportedLanguages, containsAll(['en', 'es', 'ja', 'zh']));
    });

    test('builds the GPT-Live websocket request config', () {
      final request = SttProviderConfig.get(
        SttProvider.gptLive,
      ).buildRequestConfig(apiKey: 'sk-test', language: 'fr', model: 'gpt-live-1');

      expect(request['url'], 'wss://api.openai.com/v1/live/sessions');
      expect(request['headers'], {'Authorization': 'Bearer sk-test'});
      expect(request['params'], {'model': 'gpt-live-1', 'language': 'fr'});
    });

    test('is the visible streaming provider while geminiLive is retired', () {
      final providers = SttProviderConfig.allProviders.map((config) => config.provider).toList();

      expect(providers, contains(SttProvider.gptLive));
      expect(providers, isNot(contains(SttProvider.geminiLive)));
      expect(SttProviderConfig.liveRequestTemplates, contains('OpenAI GPT-Live'));
      expect(SttProviderConfig.liveRequestTemplates, isNot(contains('Google Gemini')));
    });

    test('exposes matching request and response template names', () {
      expect(SttResponseSchema.liveTemplates, contains('OpenAI GPT-Live'));
      expect(SttResponseSchema.templates['OpenAI GPT-Live'], same(SttResponseSchema.gptLive));
      expect(SttProviderConfig.requestTemplates, contains('OpenAI GPT-Live'));
    });
  });
}
