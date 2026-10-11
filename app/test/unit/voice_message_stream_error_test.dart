import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/schema/message.dart';

void main() {
  group('parseVoiceMessageStreamChunk', () {
    test('uses the public message from a typed transcription error frame', () {
      final chunk = parseVoiceMessageStreamChunk(
        'error: {"error":"stt_upstream_error","outcome":"upstream_error","provider":"deepgram",'
            '"retryable":true,"message":"Transcription is temporarily unavailable. Please try again."}',
        'voice-message-id',
      );

      expect(chunk, isNotNull);
      expect(chunk!.messageId, 'voice-message-id');
      expect(chunk.type, MessageChunkType.error);
      expect(chunk.text, 'Transcription is temporarily unavailable. Please try again.');
      expect(chunk.errorCode, 'stt_upstream_error');
    });

    test('retains the no-speech code for localized client recovery', () {
      final chunk = parseVoiceMessageStreamChunk(
        'error: {"error":"no_speech","outcome":"expected_silence","provider":"parakeet",'
            '"retryable":true,"message":"No speech was detected."}',
        'voice-message-id',
      );

      expect(chunk, isNotNull);
      expect(chunk!.type, MessageChunkType.error);
      expect(chunk.errorCode, 'no_speech');
      expect(chunk.text, 'No speech was detected.');
    });

    test('preserves the legacy quota error payload', () {
      final chunk = parseVoiceMessageStreamChunk('error:402:{"detail":{"error":"quota_exceeded"}}', 'voice-message-id');

      expect(chunk, isNotNull);
      expect(chunk!.messageId, 'voice-message-id');
      expect(chunk.type, MessageChunkType.error);
      expect(chunk.text, '{"detail":{"error":"quota_exceeded"}}');
    });

    test('uses the safe generic error for malformed or incomplete typed frames', () {
      final safeMessage = ServerMessageChunk.failedMessage().text;

      for (final line in ['error: not-json', 'error: []', 'error: {"message":42}', 'error: {"message":"   "}']) {
        final chunk = parseVoiceMessageStreamChunk(line, 'voice-message-id');

        expect(chunk, isNotNull, reason: line);
        expect(chunk!.type, MessageChunkType.error, reason: line);
        expect(chunk.text, safeMessage, reason: line);
      }
    });
  });
}
