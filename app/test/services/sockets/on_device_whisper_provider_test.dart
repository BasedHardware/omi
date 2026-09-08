import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/sockets/on_device_whisper_provider.dart';

void main() {
  group('OnDeviceWhisperProvider.buildTranscribeRequest', () {
    // Regression: transcribe()'s optional `language` parameter shadowed the
    // provider's `language` field, so the configured language was silently
    // dropped and whisper always ran with '' (auto-detect).
    test('falls back to the provider language when no per-call language is given', () {
      final provider = OnDeviceWhisperProvider(modelPath: '/models/ggml-tiny.bin', language: 'ru');

      final req = provider.buildTranscribeRequest('/tmp/audio.wav');

      expect(req.language, 'ru');
      expect(req.audio, '/tmp/audio.wav');
    });

    test('per-call language overrides the provider language', () {
      final provider = OnDeviceWhisperProvider(modelPath: '/models/ggml-tiny.bin', language: 'ru');

      final req = provider.buildTranscribeRequest('/tmp/audio.wav', language: 'de');

      expect(req.language, 'de');
    });

    test("maps 'multi' to an empty string so whisper auto-detects", () {
      final provider = OnDeviceWhisperProvider(modelPath: '/models/ggml-tiny.bin', language: 'multi');

      final req = provider.buildTranscribeRequest('/tmp/audio.wav');

      expect(req.language, '');
    });
  });
}
