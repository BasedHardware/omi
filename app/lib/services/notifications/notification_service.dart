// Notification service selection.
// FCM (default): full Firebase Cloud Messaging / APNs remote push (iOS, Android).
// Basic (NOTIFICATIONS_BACKEND=local): local-only notifications, no remote push, no FirebaseMessaging
// at runtime — for a Firebase-push-free on-prem deployment (ADR-0011).

import 'package:flutter/foundation.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/notifications/notification_interface.dart';
import 'package:omi/services/notifications/notification_service_fcm.dart' as fcm;
import 'package:omi/services/notifications/notification_service_basic.dart' as basic;
import 'package:omi/utils/platform/platform_manager.dart';

/// Which notification delivery implementation to use.
enum NotificationBackend { fcm, local }

/// Pure selection rule: local-only notifications when remote push is disabled
/// (NOTIFICATIONS_BACKEND=local, on-prem) or the platform has no FCM support (e.g. Windows/desktop);
/// FCM/APNs otherwise. Kept pure so it is unit-testable without Env or platform channels.
/// (A future `unifiedpush` value falls back to `local` until its adapter lands — phase 2.)
@visibleForTesting
NotificationBackend selectNotificationBackend({required String backend, required bool fcmSupported}) {
  if (backend != 'fcm' || !fcmSupported) return NotificationBackend.local;
  return NotificationBackend.fcm;
}

/// Factory function to create the notification service
NotificationInterface _createPlatformNotificationService() {
  final selected = selectNotificationBackend(
    backend: Env.notificationsBackend,
    fcmSupported: PlatformManager().isFCMSupported,
  );
  return selected == NotificationBackend.fcm ? fcm.createNotificationService() : basic.createNotificationService();
}

/// Singleton notification service instance
/// Automatically selects the correct platform-specific implementation
class NotificationService {
  static NotificationInterface? _instance;

  /// Get the singleton notification service instance
  static NotificationInterface get instance {
    _instance ??= _createPlatformNotificationService();
    return _instance!;
  }

  /// Clear the instance (useful for testing)
  static void reset() {
    _instance = null;
  }
}
