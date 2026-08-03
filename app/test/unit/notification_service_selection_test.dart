import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/notifications/notification_service.dart';

// Hermetic tests for the pure notification-backend selection rule (ADR-0011 on-prem push flag).
// The factory itself needs Env + platform channels, so the selection logic is factored out as the
// pure `selectNotificationBackend` and tested here without any device/Firebase dependency.
void main() {
  group('selectNotificationBackend', () {
    test('fcm on an FCM-capable platform -> fcm (default behaviour)', () {
      expect(selectNotificationBackend(backend: 'fcm', fcmSupported: true), NotificationBackend.fcm);
    });

    test('local -> local even on an FCM-capable platform (on-prem, no remote push)', () {
      expect(selectNotificationBackend(backend: 'local', fcmSupported: true), NotificationBackend.local);
    });

    test('fcm on a platform without FCM support -> local (e.g. Windows/desktop)', () {
      expect(selectNotificationBackend(backend: 'fcm', fcmSupported: false), NotificationBackend.local);
    });

    test('any non-fcm value falls back to local (incl. future unifiedpush until its adapter lands)', () {
      expect(selectNotificationBackend(backend: 'unifiedpush', fcmSupported: true), NotificationBackend.local);
      expect(selectNotificationBackend(backend: '', fcmSupported: true), NotificationBackend.local);
      expect(selectNotificationBackend(backend: 'anything', fcmSupported: true), NotificationBackend.local);
    });
  });
}
