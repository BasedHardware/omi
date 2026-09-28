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
}
