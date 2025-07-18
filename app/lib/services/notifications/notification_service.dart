// Platform-aware notification service with conditional implementation
// FCM Implementation: Full Firebase Cloud Messaging support (iOS, Android, macOS, web, Linux)
// Basic Implementation: Local notifications only (Windows)

import 'dart:io' show Platform;
import 'package:omi/services/notifications/notification_interface.dart';
import 'package:omi/services/notifications/notification_service_fcm.dart' as fcm;
import 'package:omi/services/notifications/notification_service_basic.dart' as basic;

/// Factory function to create the appropriate notification service based on platform capabilities
NotificationInterface _createPlatformNotificationService() {
  if (Platform.isWindows) {
    // Windows: Basic local notifications only (Firebase Messaging not supported)
    return basic.createNotificationService();
  } else {
    // iOS, Android, macOS, web, Linux: Full FCM support
    return fcm.createNotificationService();
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
