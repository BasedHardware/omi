import 'package:flutter/material.dart';
import 'package:friend_private/services/web_notification_service.dart';

/// Web-compatible notification utilities that don't use dart:isolate
class WebNotificationUtil {
  static void initializeNotificationsEventListeners() {
    debugPrint('Initializing web notification event listeners');
    // Web implementation doesn't need isolate-based event listeners
  }
  
  static void handleNotificationAction(String? payload) {
    debugPrint('Web notification action: $payload');
    // Handle notification actions for web
  }
}
