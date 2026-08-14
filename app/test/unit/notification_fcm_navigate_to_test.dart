import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/notifications.dart';

void main() {
  group('NotificationUtil.navigateToFromFcmData (#5126)', () {
    test('returns navigate_to when it is a non-empty String', () {
      expect(NotificationUtil.navigateToFromFcmData(const {'navigate_to': '/chat/omi'}), '/chat/omi');
    });

    test('returns null when navigate_to is missing', () {
      expect(NotificationUtil.navigateToFromFcmData(const {'type': 'plugin'}), isNull);
    });

    test('returns null when navigate_to is empty', () {
      expect(NotificationUtil.navigateToFromFcmData(const {'navigate_to': ''}), isNull);
    });

    test('returns null when navigate_to is not a String', () {
      expect(NotificationUtil.navigateToFromFcmData(const {'navigate_to': 42}), isNull);
      expect(NotificationUtil.navigateToFromFcmData(const {'navigate_to': true}), isNull);
    });
  });

  group('NotificationUtil.waitUntilNonNull (#5126 cold-start)', () {
    test('returns immediately when value is already present', () async {
      final result = await NotificationUtil.waitUntilNonNull(
        () => 'ready',
        timeout: const Duration(milliseconds: 50),
        pollInterval: const Duration(milliseconds: 5),
      );
      expect(result, 'ready');
    });

    test('resolves once the value appears after a delay', () async {
      String? value;
      Future<void>.delayed(const Duration(milliseconds: 30), () => value = 'ready');

      final result = await NotificationUtil.waitUntilNonNull(
        () => value,
        timeout: const Duration(seconds: 1),
        pollInterval: const Duration(milliseconds: 5),
      );
      expect(result, 'ready');
    });

    test('returns null when the value never appears before timeout', () async {
      final result = await NotificationUtil.waitUntilNonNull<String>(
        () => null,
        timeout: const Duration(milliseconds: 40),
        pollInterval: const Duration(milliseconds: 5),
      );
      expect(result, isNull);
    });
  });
}
