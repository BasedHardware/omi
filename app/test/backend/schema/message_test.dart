import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/backend/schema/message.dart';

void main() {
  group('Message Schema Tests', () {
    test('Create failed message', () {
      final message = ServerMessage.failedMessage();
      expect(message.text, 'Looks like we are having issues with the server. Please try again later.');
    });

    test('Message JSON serialization', () {
      final now = DateTime.now().toIso8601String();
      final messageJson = {
        'text': 'Test message',
        'created_at': now,
        'sender': 'ai',
        'user_id': 'user123',
        'content': 'Test content',
        'updated_at': now,
        'type': 'text',
        'memories': [],
        'id': '123',
      };

      final message = ServerMessage.fromJson(messageJson);
      final json = message.toJson();

      expect(message.text, 'Test message');
      expect(json['text'], 'Test message');
      expect(json['sender'], 'ai');
      expect(json['id'], '123');
    });
  });
}
