import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/notifications/notification_service.dart';

// Hermetic tests for the pure notification-backend selection rule (ADR-0011 on-prem push flag).
// The factory itself needs Env + platform channels, so the selection logic is factored out as the
// pure `selectNotificationBackend` and tested here without any device/Firebase dependency.
void main() {
  group('selectNotificationBackend', () {
    test('fcm on an FCM-capable platform -> fcm (default behaviour)', () {
      expect(
        selectNotificationBackend(backend: 'fcm', fcmSupported: true, unifiedPushSupported: true),
        NotificationBackend.fcm,
      );
    });

    test('local -> local even on an FCM-capable platform (on-prem, no remote push)', () {
      expect(
        selectNotificationBackend(backend: 'local', fcmSupported: true, unifiedPushSupported: true),
        NotificationBackend.local,
      );
    });

    test('fcm on a platform without FCM support -> local (e.g. Windows/desktop)', () {
      expect(
        selectNotificationBackend(backend: 'fcm', fcmSupported: false, unifiedPushSupported: false),
        NotificationBackend.local,
      );
    });

    test('unifiedpush where a distributor exists (Android) -> unifiedpush', () {
      expect(
        selectNotificationBackend(backend: 'unifiedpush', fcmSupported: false, unifiedPushSupported: true),
        NotificationBackend.unifiedpush,
      );
    });

    test('unifiedpush where UnifiedPush is unsupported (iOS/desktop) -> local', () {
      expect(
        selectNotificationBackend(backend: 'unifiedpush', fcmSupported: true, unifiedPushSupported: false),
        NotificationBackend.local,
      );
    });

    test('any unknown value falls back to local', () {
      expect(
        selectNotificationBackend(backend: '', fcmSupported: true, unifiedPushSupported: true),
        NotificationBackend.local,
      );
      expect(
        selectNotificationBackend(backend: 'anything', fcmSupported: true, unifiedPushSupported: true),
        NotificationBackend.local,
      );
    });
  });
}
