import 'package:flutter_test/flutter_test.dart';
import 'package:omi_device/omi_device.dart';

void main() {
  test('deepgramWsUrl omits api key from query string', () {
    expect(
      deepgramWsUrl(),
      'wss://api.deepgram.com/v1/listen?punctuate=true&model=nova&language=en-US&encoding=linear16&sample_rate=16000&channels=1',
    );
    expect(deepgramWsUrl(sampleRate: 8000), contains('sample_rate=8000'));
    expect(deepgramWsUrl(), isNot(contains('token=')));
  });

  test('parakeetWsUrl', () {
    expect(parakeetWsUrl('https://parakeet.example/'), 'wss://parakeet.example/v3/stream?sample_rate=16000');
  });

  test('whisper requires runner', () {
    expect(() => createTranscriber(engine: SttEngine.whisper, onTranscript: (_) {}), throwsA(isA<ArgumentError>()));
  });
}
