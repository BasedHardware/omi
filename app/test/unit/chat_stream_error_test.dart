import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/schema/message.dart';

void main() {
  test('memory receipt event is decoded without changing reply text', () {
    final saved = parseMessageChunk('memory: saved', 'message-id');
    final updated = parseMessageChunk('memory: updated', 'message-id');
    expect(saved?.type, MessageChunkType.memory);
    expect(saved?.text, 'saved');
    expect(updated?.text, 'updated');
  });
  test('parses a bounded chat SSE failure frame', () {
    final chunk = parseMessageChunk('error: The response took too long. Please try again.', 'message-id');

    expect(chunk, isNotNull);
    expect(chunk!.messageId, 'message-id');
    expect(chunk.type, MessageChunkType.error);
    expect(chunk.text, 'The response took too long. Please try again.');
  });

  group('typed error frames', () {
    test('decodes a JSON error payload into its code', () {
      final chunk = parseMessageChunk('error: {"error":"provider_failed","message":"Broken pipe"}', 'id');

      expect(chunk, isNotNull);
      expect(chunk!.type, MessageChunkType.error);
      expect(chunk.text, 'Broken pipe');
      expect(chunk.errorCode, 'provider_failed');
    });

    test('maps the legacy timeout frame to the timeout code', () {
      final chunk = parseMessageChunk('error: $chatStreamTimeoutFrameText', 'id');

      expect(chunk, isNotNull);
      expect(chunk!.type, MessageChunkType.error);
      expect(chunk.errorCode, 'timeout');
    });

    test('decodes a typed quota error code', () {
      final chunk = parseMessageChunk('error: {"error":"quota_exceeded","message":"limit reached"}', 'id');

      expect(chunk, isNotNull);
      expect(chunk!.type, MessageChunkType.error);
      expect(chunk.errorCode, 'quota_exceeded');
      expect(chunk.text, 'limit reached');
    });

    test('a typed quota frame without a message keeps its code and payload', () {
      final chunk = parseMessageChunk('error: {"error":"quota_exceeded"}', 'id');

      expect(chunk, isNotNull);
      expect(chunk!.type, MessageChunkType.error);
      expect(chunk.errorCode, 'quota_exceeded');
      expect(chunk.text, contains('quota_exceeded'));
    });

    test('a malformed JSON error frame becomes the bounded failure, never raw text', () {
      // Syntactically invalid JSON: jsonDecode throws FormatException inside the parser.
      final chunk = parseVoiceMessageStreamChunk('error: {"error":', 'id');

      expect(chunk, isNotNull);
      expect(chunk!.type, MessageChunkType.error);
      expect(chunk.text, ServerMessageChunk.failedMessage().text);
    });
  });
}
