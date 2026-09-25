import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';

void main() {
  group('BleAudioCodec.encodedBytesPerSecond', () {
    test('uses the canonical encoded rates for both Opus codecs', () {
      expect(BleAudioCodec.opus.encodedBytesPerSecond, 8000);
      expect(BleAudioCodec.opusFS320.encodedBytesPerSecond, 16000);
    });

    test('derives PCM and mu-law rates from stream metadata', () {
      expect(BleAudioCodec.pcm16.estimatedBytesPerSecond(sampleRate: 16000, channels: 2), 64000);
      expect(BleAudioCodec.pcm8.estimatedBytesPerSecond(sampleRate: 16000, channels: 1), 16000);
      expect(BleAudioCodec.mulaw16.estimatedBytesPerSecond(sampleRate: 16000, channels: 1), 16000);
    });

    test('uses the established Opus fallback for variable or unknown codecs', () {
      expect(BleAudioCodec.aac.estimatedBytesPerSecond(sampleRate: 48000, channels: 2), 8000);
      expect(BleAudioCodec.unknown.estimatedBytesPerSecond(sampleRate: 0, channels: 0), 8000);
    });

    test('estimates FS320 recordings at 16000 bytes per second', () {
      expect(
        BleAudioCodec.opusFS320.estimatedRecordingBytes(seconds: 60, sampleRate: 16000, channels: 1),
        960000,
      );
    });
  });
}
