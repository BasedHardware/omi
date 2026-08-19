import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/message.dart';

void main() {
  Map<String, dynamic> messageJson({required String text, Object? contentBlocks, String? metadata}) {
    return {
      'id': 'message-1',
      'created_at': '2026-08-18T12:00:00Z',
      'text': text,
      'sender': 'ai',
      'type': 'text',
      if (contentBlocks != null) 'content_blocks': contentBlocks,
      if (metadata != null) 'metadata': metadata,
    };
  }

  test('uses first-class conversation block fallback instead of a blank bubble', () {
    final message = ServerMessage.fromJson(
      messageJson(
        text: '',
        contentBlocks: [
          {'type': 'conversationLink', 'conversationId': 'conversation-1', 'summary': 'Founders explore AI memory'},
        ],
      ),
    );

    expect(message.text, 'Meeting notes ready - Founders explore AI memory');
    expect(message.contentBlocks.single['conversationId'], 'conversation-1');
  });

  test('keeps legacy metadata blocks readable during wire migration', () {
    final message = ServerMessage.fromJson(
      messageJson(
        text: '',
        metadata:
            '{"content_blocks":[{"type":"conversationLink","conversationId":"conversation-legacy","summary":"Legacy weekly planning"}]}',
      ),
    );

    expect(message.text, 'Meeting notes ready - Legacy weekly planning');
    expect(message.contentBlocks.single['conversationId'], 'conversation-legacy');
  });

  test('preserves canonical backend fallback text when the client knows the block', () {
    final message = ServerMessage.fromJson(
      messageJson(
        text: 'Meeting notes ready - Canonical title',
        contentBlocks: [
          {'type': 'conversationLink', 'summary': 'Different local rendering'},
        ],
      ),
    );

    expect(message.text, 'Meeting notes ready - Canonical title');
  });
}
