// Platform-aware notification service with FCM implementation
// FCM Implementation: Full Firebase Cloud Messaging support (iOS, Android)

import 'package:omi/services/notifications/notification_interface.dart';
import 'package:omi/services/notifications/notification_service_fcm.dart' as fcm;

/// Factory function to create the notification service
NotificationInterface _createPlatformNotificationService() {
  return fcm.createNotificationService();
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
