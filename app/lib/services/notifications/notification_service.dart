// Notification service selection.
// FCM (default): full Firebase Cloud Messaging / APNs remote push (iOS, Android).
// Basic (NOTIFICATIONS_BACKEND=local): local-only notifications, no remote push, no FirebaseMessaging
// at runtime — for a Firebase-push-free on-prem deployment (ADR-0011).

import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/notifications/notification_interface.dart';
import 'package:omi/services/notifications/notification_service_fcm.dart' as fcm;
import 'package:omi/services/notifications/notification_service_basic.dart' as basic;
import 'package:omi/services/notifications/notification_service_unifiedpush.dart' as unifiedpush;
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Which notification delivery implementation to use.
enum NotificationBackend { fcm, local, unifiedpush }

/// Pure selection rule (kept pure so it is unit-testable without Env or platform channels):
/// - `unifiedpush` → self-hosted push where a distributor exists (Android); elsewhere → `local`.
/// - `fcm` (default) → FCM/APNs where supported; on a platform without FCM (Windows/desktop) → `local`.
/// - `local` / anything else → local-only notifications, no remote push (on-prem, ADR-0011).
@visibleForTesting
NotificationBackend selectNotificationBackend({
  required String backend,
  required bool fcmSupported,
  required bool unifiedPushSupported,
}) {
  if (backend == 'unifiedpush') {
    return unifiedPushSupported ? NotificationBackend.unifiedpush : NotificationBackend.local;
  }
  if (backend == 'fcm' && fcmSupported) {
    return NotificationBackend.fcm;
  }
  return NotificationBackend.local;
}

/// Factory function to create the notification service
NotificationInterface _createPlatformNotificationService() {
  final requested = Env.notificationsBackend;
  final selected = selectNotificationBackend(
    backend: requested,
    fcmSupported: PlatformManager().isFCMSupported,
    unifiedPushSupported: Platform.isAndroid,
  );
  // Make a silent capability downgrade observable: the operator chose the backend at build time, but
  // a platform without the transport (FCM SDK / a UnifiedPush distributor) falls back to local-only.
  // Log it so a missing remote push is diagnosable instead of silently degrading.
  if (selected == NotificationBackend.local && requested != 'local') {
    Logger.warning(
      'NotificationService: NOTIFICATIONS_BACKEND=$requested has no transport on this platform; '
      'falling back to local-only notifications (no remote push).',
    );
  }
  switch (selected) {
    case NotificationBackend.fcm:
      return fcm.createNotificationService();
    case NotificationBackend.unifiedpush:
      return unifiedpush.createNotificationService();
    case NotificationBackend.local:
      return basic.createNotificationService();
  }
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
