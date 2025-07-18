import 'dart:async';
import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:omi/backend/schema/message.dart';

/// Common interface for notification services across all platforms
abstract class NotificationInterface {
  Future<void> initialize();

  void showNotification({
    required int id,
    required String title,
    required String body,
    Map<String, String?>? payload,
    bool wakeUpScreen = false,
    NotificationSchedule? schedule,
    NotificationLayout layout = NotificationLayout.Default,
  });

  Future<bool> requestNotificationPermissions();
  Future<void> register();
  Future<String> getTimeZone();
  Future<void> saveFcmToken(String? token);
  void saveNotificationToken();
  Future<bool> hasNotificationPermissions();

  Future<void> createNotification({
    String title = '',
    String body = '',
    int notificationId = 1,
    Map<String, String?>? payload,
  });

  void clearNotification(int id);
  Future<void> listenForMessages();

  Stream<ServerMessage> get listenForServerMessages;
}
