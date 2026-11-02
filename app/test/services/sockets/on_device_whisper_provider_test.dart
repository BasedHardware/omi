import 'package:omi/services/on_device/on_device_engine.dart';
import 'dart:typed_data';

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

  group('pcmWavDurationSeconds', () {
    // Regression: transcribe() derived the segment duration from the whole
    // WAV buffer length divided by a hardcoded 32000 (16000 Hz * 2 bytes).
    // The buffer is a WAV container, so the 44-byte header was counted as
    // audio, and an 8 kHz WAV (the pcm8 codec path) was reported at half its
    // real length. Both corrupt the segment timeline that the conversation
    // is persisted from.
    Uint8List wav({required int sampleRate, required int pcmBytes}) {
      final header = ByteData(44);
      header.setUint32(24, sampleRate, Endian.little); // SampleRate
      header.setUint32(40, pcmBytes, Endian.little); // data chunk size
      final out = Uint8List(44 + pcmBytes);
      out.setRange(0, 44, header.buffer.asUint8List());
      return out;
    }

    test('uses the WAV sample rate and excludes the 44-byte header', () {
      // 16000 Hz, 16-bit mono => 32000 bytes per second.
      final bytes = wav(sampleRate: 16000, pcmBytes: 32000);
      expect(pcmWavDurationSeconds(bytes), closeTo(1.0, 0.001));
    });

    test('reports an 8 kHz WAV at its real length, not half', () {
      // 8000 Hz, 16-bit mono => 16000 bytes per second.
      final bytes = wav(sampleRate: 8000, pcmBytes: 16000);
      expect(pcmWavDurationSeconds(bytes), closeTo(1.0, 0.001));
    });

    test('falls back to 16 kHz for non-WAV input', () {
      final raw = Uint8List(32000);
      expect(pcmWavDurationSeconds(raw), closeTo(1.0, 0.001));
    });
  });
}
