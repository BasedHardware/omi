import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/sockets/pure_streaming_stt.dart';

void main() {
  group('gptLiveSessionStartMessage', () {
    test('names the target language and omits a synthesized reply voice', () {
      final message = gptLiveSessionStartMessage(
        model: 'gpt-live-1',
        language: 'fr',
        sampleRate: 24000,
        eventId: 'evt-1',
      );

      expect(message['type'], 'session.start');
      expect(message['event_id'], 'evt-1');
      final session = message['session'] as Map<String, dynamic>;
      expect(session['model'], 'gpt-live-1');
      expect(session['instructions'], contains('French'));
      final audio = session['audio'] as Map<String, dynamic>;
      expect(audio['format'], {'type': 'audio/pcm', 'rate': 24000});
      // STT-only: the model must not be asked to synthesize a spoken reply.
      expect(audio.containsKey('output'), isFalse);
    });

    test('falls back to the raw code for an unrecognized language', () {
      final message = gptLiveSessionStartMessage(
        model: 'gpt-live-1',
        language: 'xx',
        sampleRate: 16000,
        eventId: 'evt-2',
      );

      final session = message['session'] as Map<String, dynamic>;
      expect(session['instructions'], contains('xx'));
    });
  });
}
