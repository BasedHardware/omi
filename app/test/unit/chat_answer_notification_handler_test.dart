import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/notifications/chat_answer_notification_handler.dart';

void main() {
  group('ChatAnswerNotificationHandler.isChatAnswerData (#4375)', () {
    test('true when push_type is chat_answer', () {
      expect(
        ChatAnswerNotificationHandler.isChatAnswerData(const {'push_type': 'chat_answer', 'body': 'Hello from omi'}),
        isTrue,
      );
    });

    test('true for plugin notification targeting /chat/', () {
      expect(
        ChatAnswerNotificationHandler.isChatAnswerData(const {
          'notification_type': 'plugin',
          'navigate_to': '/chat/omi',
          'text': 'Full answer text',
        }),
        isTrue,
      );
    });

    test('false for unrelated plugin payloads without chat route', () {
      expect(
        ChatAnswerNotificationHandler.isChatAnswerData(const {
          'notification_type': 'plugin',
          'navigate_to': '/apps/foo',
        }),
        isFalse,
      );
    });

    test('false for action item reminders', () {
      expect(
        ChatAnswerNotificationHandler.isChatAnswerData(const {'type': 'action_item_reminder', 'action_item_id': 'abc'}),
        isFalse,
      );
    });
  });
}
