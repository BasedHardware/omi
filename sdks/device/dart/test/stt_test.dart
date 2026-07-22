import 'package:flutter_test/flutter_test.dart';
import 'package:omi_device/omi_device.dart';

void main() {
  test('deepgramWsUrl includes encoded token', () {
    expect(
      deepgramWsUrl('dg-123'),
      'wss://api.deepgram.com/v1/listen?punctuate=true&model=nova&language=en-US&encoding=linear16&sample_rate=16000&channels=1&token=dg-123',
    );
    expect(
      deepgramWsUrl('key with spaces=', sampleRate: 8000),
      contains('token=key%20with%20spaces%3D'),
    );
  });

  test('parakeetWsUrl', () {
    expect(parakeetWsUrl('https://parakeet.example/'), 'wss://parakeet.example/v3/stream?sample_rate=16000');
  });

  test('whisper requires runner', () {
    expect(() => createTranscriber(engine: SttEngine.whisper, onTranscript: (_) {}), throwsA(isA<ArgumentError>()));
  });
}
