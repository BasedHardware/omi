import 'package:flutter/material.dart';

import 'package:awesome_notifications/awesome_notifications.dart';

import 'package:omi/utils/logger.dart';

/// Shared handler for action item notifications
class ActionItemNotificationHandler {
  static final _awesomeNotifications = AwesomeNotifications();

  /// Schedule a local notification for an action item reminder
  /// Schedules notification 1 hour before the due time
  static Future<void> scheduleNotification({
    required String actionItemId,
    required String description,
    required String dueAtIso,
    required String channelKey,
  }) async {
    try {
      final allowed = await _awesomeNotifications.isNotificationAllowed();
      if (!allowed) {
        return;
      }

      final dueAt = DateTime.parse(dueAtIso).toLocal();
      // Schedule notification 1 hour before due time
      final reminderTime = dueAt.subtract(const Duration(hours: 1));

      // Only schedule if reminder time is in the future
      if (reminderTime.isBefore(DateTime.now())) {
        Logger.debug('[ActionItem] Reminder time is in the past, skipping: $actionItemId');
        return;
      }

      // Use action item ID hash as notification ID
      final notificationId = actionItemId.hashCode;

      await _awesomeNotifications.createNotification(
        content: NotificationContent(
          id: notificationId,
          channelKey: channelKey,
          title: '⏰ Omi Reminder',
          body: description,
          payload: {
            'action_item_id': actionItemId,
            'navigate_to': '/action-items',
          },
          notificationLayout: NotificationLayout.Default,
          wakeUpScreen: true,
          category: NotificationCategory.Reminder,
        ),
        schedule: NotificationCalendar.fromDate(date: reminderTime),
      );
    } catch (e) {
      Logger.debug('[ActionItem] Error scheduling notification: $e');
    }
  }

  /// Cancel a scheduled notification for an action item
  static Future<void> cancelNotification(String actionItemId) async {
    try {
      final notificationId = actionItemId.hashCode;
      await _awesomeNotifications.cancel(notificationId);
    } catch (e) {
      Logger.debug('[ActionItem] Error cancelling notification: $e');
    }
  }

  /// Handle action item reminder data message
  static Future<void> handleReminderMessage(
    Map<String, dynamic> data,
    String channelKey,
  ) async {
    final actionItemId = data['action_item_id'];
    final description = data['description'];
    final dueAt = data['due_at'];

    if (actionItemId == null || description == null || dueAt == null) {
      Logger.debug('[ActionItem] Invalid reminder data');
      return;
    }

    await scheduleNotification(
      actionItemId: actionItemId,
      description: description,
      dueAtIso: dueAt,
      channelKey: channelKey,
    );
  }

  /// Handle action item update data message
  static Future<void> handleUpdateMessage(
    Map<String, dynamic> data,
    String channelKey,
  ) async {
    final actionItemId = data['action_item_id'];
    final description = data['description'];
    final dueAt = data['due_at'];

    if (actionItemId == null || description == null || dueAt == null) {
      Logger.debug('[ActionItem] Invalid update data');
      return;
    }

    // Cancel existing notification and reschedule with new data
    await cancelNotification(actionItemId);
    await scheduleNotification(
      actionItemId: actionItemId,
      description: description,
      dueAtIso: dueAt,
      channelKey: channelKey,
    );
  }

  /// Handle action item deletion data message
  static Future<void> handleDeletionMessage(Map<String, dynamic> data) async {
    final actionItemId = data['action_item_id'];

    if (actionItemId == null) {
      Logger.debug('[ActionItem] Invalid deletion data');
      return;
    }

    await cancelNotification(actionItemId);
  }
}
