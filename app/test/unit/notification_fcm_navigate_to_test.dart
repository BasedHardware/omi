import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/notifications.dart';

void main() {
  group('NotificationUtil.navigateToFromFcmData (#5126)', () {
    test('returns navigate_to when it is a non-empty String', () {
      expect(NotificationUtil.navigateToFromFcmData({'navigate_to': '/chat/omi'}), '/chat/omi');
    });

    test('returns null when navigate_to is missing', () {
      expect(NotificationUtil.navigateToFromFcmData({'type': 'plugin'}), isNull);
    });

    test('returns null when navigate_to is empty', () {
      expect(NotificationUtil.navigateToFromFcmData({'navigate_to': ''}), isNull);
    });

    test('returns null when navigate_to is not a String', () {
      expect(NotificationUtil.navigateToFromFcmData({'navigate_to': 42}), isNull);
      expect(NotificationUtil.navigateToFromFcmData({'navigate_to': true}), isNull);
    });
  });
}
