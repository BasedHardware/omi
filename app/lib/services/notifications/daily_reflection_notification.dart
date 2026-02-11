import 'package:flutter/material.dart';

import 'package:awesome_notifications/awesome_notifications.dart';

import 'package:omi/main.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

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

  /// Schedule the daily reflection notification at the specified hour (default: 9 PM)
  static Future<void> scheduleDailyNotification({
    required String channelKey,
    int hour = 21, // Default to 9 PM (21:00)
  }) async {
    try {
      final allowed = await _awesomeNotifications.isNotificationAllowed();
      if (!allowed) {
        Logger.debug('[DailyReflection] Notifications not allowed');
        return;
      }

      // Validate hour
      if (hour < 0 || hour > 23) {
        Logger.debug('[DailyReflection] Invalid hour: $hour, using default 21');
        hour = 21;
      }

      // Cancel any existing scheduled notification first
      await cancelNotification();

      // Schedule notification for specified hour every day
      final ctx = MyApp.navigatorKey.currentContext;
      await _awesomeNotifications.createNotification(
        content: NotificationContent(
          id: notificationId,
          channelKey: channelKey,
          title: '🌙 ${ctx?.l10n.dailyReflectionNotificationTitle ?? 'Time for Daily Reflection'}',
          body: ctx?.l10n.dailyReflectionNotificationBody ?? 'Tell me about your day',
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
          hour: hour,
          minute: 0,
          second: 0,
          millisecond: 0,
          repeats: true,
          allowWhileIdle: true,
          preciseAlarm: true,
        ),
      );

      Logger.debug('[DailyReflection] Scheduled daily notification for $hour:00');
    } catch (e) {
      Logger.debug('[DailyReflection] Error scheduling notification: $e');
    }
  }

  /// Cancel the scheduled notification
  static Future<void> cancelNotification() async {
    try {
      await _awesomeNotifications.cancel(notificationId);
      Logger.debug('[DailyReflection] Cancelled notification');
    } catch (e) {
      Logger.debug('[DailyReflection] Error cancelling notification: $e');
    }
  }

  /// Check if this payload is for daily reflection auto-message
  static bool isReflectionPayload(Map<String, dynamic> payload) {
    return payload['auto_message'] == 'daily_reflection';
  }
}
