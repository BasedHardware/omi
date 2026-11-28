import 'package:flutter_test/flutter_test.dart';

import 'package:omi/models/stt_provider.dart';

void main() {
  group('Gemini speech-to-text model', () {
    final gemini = SttProviderConfig.get(SttProvider.gemini);

    test('defaults to gemini-3.6-flash and suggests it first', () {
      expect(gemini.defaultModel, 'gemini-3.6-flash');
      expect(gemini.supportedModels.first, 'gemini-3.6-flash');
    });

    test('no longer names gemini-2.0-flash, which Google shut down on June 1, 2026', () {
      expect(gemini.defaultModel, isNot('gemini-2.0-flash'));
      expect(gemini.supportedModels, isNot(contains('gemini-2.0-flash')));
    });

    test('an empty model falls back to gemini-3.6-flash in the request URL', () {
      final config = gemini.buildRequestConfig(apiKey: 'test-key', language: 'en', model: '');
      expect(config['url'], contains('/models/gemini-3.6-flash:generateContent'));
    });
  });
}
