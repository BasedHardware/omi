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

  group('NotificationUtil.notificationOpenedProperties (#12645)', () {
    test('carries the campaign id straight off the FCM data map', () {
      expect(
        NotificationUtil.notificationOpenedProperties(const {
          'campaign_id': 'macos-push-2026-09-02',
          'navigate_to': '/chat/omi',
          'notification_type': 'campaign',
        }),
        {
          'campaign_id': 'macos-push-2026-09-02',
          'navigate_to': '/chat/omi',
          'notification_type': 'campaign',
        },
      );
    });

    test('omits campaign_id entirely when the notification is not a campaign', () {
      final properties = NotificationUtil.notificationOpenedProperties(const {'navigate_to': '/chat/omi'});

      // Absent rather than null: a query filtering on campaign_id must see only
      // real campaign traffic.
      expect(properties.containsKey('campaign_id'), isFalse);
      expect(properties['navigate_to'], '/chat/omi');
    });

    test('falls back to the legacy type key when notification_type is absent', () {
      expect(
        NotificationUtil.notificationOpenedProperties(const {'type': 'day_summary'})['notification_type'],
        'day_summary',
      );
    });

    test('prefers notification_type over the legacy type key', () {
      expect(
        NotificationUtil.notificationOpenedProperties(
          const {'notification_type': 'campaign', 'type': 'day_summary'},
        )['notification_type'],
        'campaign',
      );
    });

    test('drops empty and non-String values instead of reporting them', () {
      expect(
        NotificationUtil.notificationOpenedProperties(const {'campaign_id': '', 'navigate_to': 42}),
        isEmpty,
      );
    });

    test('a payload with no recognised keys yields no properties', () {
      expect(NotificationUtil.notificationOpenedProperties(const {}), isEmpty);
    });
  });

  group('NotificationUtil.externalTargetFor (#12645)', () {
    test('treats an absolute https campaign CTA as external', () {
      final target = NotificationUtil.externalTargetFor(
        'https://api.omi.me/v2/desktop/download/latest?campaign_id=macos-push-2026-09-02',
      );

      expect(target, isNotNull);
      expect(target!.host, 'api.omi.me');
      expect(target.queryParameters['campaign_id'], 'macos-push-2026-09-02');
    });

    test('treats http as external too', () {
      expect(NotificationUtil.externalTargetFor('http://omi.me/download')?.host, 'omi.me');
    });

    test('leaves an in-app route alone', () {
      // Must stay null, or every deep link would try to open in a browser.
      expect(NotificationUtil.externalTargetFor('/chat/omi'), isNull);
      expect(NotificationUtil.externalTargetFor('conversations'), isNull);
    });

    test('refuses schemes other than http and https', () {
      // A notification payload is attacker-influenced: handing an arbitrary
      // scheme to the platform launcher would address anything the OS can open.
      for (final hostile in const [
        'file:///etc/passwd',
        'javascript:alert(1)',
        'mailto:someone@example.com',
        'tel:+15551234567',
        'omi://settings',
      ]) {
        expect(NotificationUtil.externalTargetFor(hostile), isNull, reason: hostile);
      }
    });

    test('refuses a scheme with no authority', () {
      expect(NotificationUtil.externalTargetFor('https:'), isNull);
    });
  });
}
