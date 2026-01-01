import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:flutter/material.dart';

/// Handler for daily reflection notifications
/// Schedules a notification every day at 9 PM local time
class DailyReflectionNotification {
  static final _awesomeNotifications = AwesomeNotifications();

  /// The reflection prompt message to send in chat
  static const String reflectionMessage = """It's time for a daily reflection:
- What did you do today that moved you closer to your goal?
- What did you learn today?
- What do you want to do tomorrow?""";

  /// Unique notification ID for daily reflection
  static const int notificationId = 9021; // 9 PM + 21 = 9021

  /// Schedule the daily reflection notification at 9 PM local time
  static Future<void> scheduleDailyNotification({
    required String channelKey,
  }) async {
    try {
      final allowed = await _awesomeNotifications.isNotificationAllowed();
      if (!allowed) {
        debugPrint('[DailyReflection] Notifications not allowed');
        return;
      }

      // Cancel any existing scheduled notification first
      await cancelNotification();

      // Schedule notification for 9 PM every day
      await _awesomeNotifications.createNotification(
        content: NotificationContent(
          id: notificationId,
          channelKey: channelKey,
          title: '🌙 Time for Daily Reflection',
          body: 'Tell me about your day',
          badge: 0,
          payload: {
            'navigate_to': '/chat/omi',
            'auto_message': 'daily_reflection',
          },
          notificationLayout: NotificationLayout.Default,
          wakeUpScreen: true,
          category: NotificationCategory.Reminder,
        ),
        schedule: NotificationCalendar(
          hour: 21, // 9 PM
          minute: 0,
          second: 0,
          millisecond: 0,
          repeats: true,
          allowWhileIdle: true,
          preciseAlarm: true,
        ),
      );

      debugPrint('[DailyReflection] Scheduled daily notification for 9 PM');
    } catch (e) {
      debugPrint('[DailyReflection] Error scheduling notification: $e');
    }
  }

  /// Cancel the scheduled notification
  static Future<void> cancelNotification() async {
    try {
      await _awesomeNotifications.cancel(notificationId);
      debugPrint('[DailyReflection] Cancelled notification');
    } catch (e) {
      debugPrint('[DailyReflection] Error cancelling notification: $e');
    }
  }

  /// Check if this payload is for daily reflection auto-message
  static bool isReflectionPayload(Map<String, dynamic> payload) {
    return payload['auto_message'] == 'daily_reflection';
  }
}
