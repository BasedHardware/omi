import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/backend/schema/message.dart';

void main() {
  group('Message Schema Tests', () {
    test('Message creation and serialization', () {
      final now = DateTime.now();
      final message = ServerMessage(
        'Test message',
        now,
        'user1',
        'user1',
        'Test content',
        now,
        MessageType.text,
        '1',
      );

      expect(message.text, 'Test message');
      expect(message.timestamp, now);
      expect(message.userId, 'user1');
      expect(message.type, MessageType.text);
    });

    test('Message from/to JSON', () {
      final now = DateTime.now();
      final message = ServerMessage(
        'Test message',
        now,
        'user1',
        'user1',
        'Test content',
        now,
        MessageType.text,
        '1',
      );

      final json = message.toJson();
      final fromJson = ServerMessage.fromJson(json);

      expect(fromJson.text, message.text);
      expect(fromJson.userId, message.userId);
      expect(fromJson.type, message.type);
    });
  });
}
