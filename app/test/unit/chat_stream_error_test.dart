import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/schema/message.dart';

void main() {
  test('backend citation SSE capture settles to stripped text and owned cards', () {
    final bytes = jsonDecode(File('../backend/tests/fixtures/chat_app_citations_pre_21240.sse.json').readAsStringSync())
        as String;
    var streamedText = '';
    ServerMessage? finalMessage;
    for (final line in bytes.split('\n')) {
      final chunk = parseMessageChunk(line, 'fixture-client');
      if (chunk?.type == MessageChunkType.data) streamedText += chunk!.text;
      if (chunk?.type == MessageChunkType.done) finalMessage = chunk!.message;
    }
    expect(streamedText, 'I can name them.[1][2][4][6][7]');
    expect(finalMessage, isNotNull);
    expect(finalMessage!.text, 'I can name them.');
    expect(finalMessage.memories.map((card) => card.id), [
      'conversation-1',
      'conversation-2',
      'conversation-4',
      'conversation-6',
      'conversation-7',
    ]);
    expect(finalMessage.contentBlocks, isEmpty);
    expect(finalMessage.typedContentBlocks, isEmpty);
  });

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
