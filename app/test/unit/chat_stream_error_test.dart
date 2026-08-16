import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/schema/message.dart';

void main() {
  test('parses a bounded chat SSE failure frame', () {
    final chunk = parseMessageChunk('error: The response took too long. Please try again.', 'message-id');

    expect(chunk, isNotNull);
    expect(chunk!.messageId, 'message-id');
    expect(chunk.type, MessageChunkType.error);
    expect(chunk.text, 'The response took too long. Please try again.');
  });
}
