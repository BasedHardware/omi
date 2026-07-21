import 'package:omi_device/omi_device.dart';
import 'package:test/test.dart';

void main() {
  test('parakeetWsUrl', () {
    expect(
      parakeetWsUrl('https://parakeet.example/'),
      'wss://parakeet.example/v3/stream?sample_rate=16000',
    );
  });

  test('whisper requires runner', () {
    expect(
      () => createTranscriber(engine: SttEngine.whisper, onTranscript: (_) {}),
      throwsA(isA<ArgumentError>()),
    );
  });
}
