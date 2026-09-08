import 'package:flutter/material.dart';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import 'package:omi/services/notifications/action_item_notification_handler.dart';
import 'package:omi/services/notifications/chat_answer_notification_handler.dart';
import 'package:omi/services/notifications/important_conversation_notification_handler.dart';
import 'package:omi/services/notifications/merge_notification_handler.dart';

/// Enhanced FCM background entrypoint including chat-answer BigText (#4375).
///
/// Registered from [_FCMNotificationService.initialize] via a post-frame
/// callback so it replaces the older handler wired in `main.dart` without
/// requiring a large `main.dart` rewrite on older forks.
@pragma('vm:entry-point')
Future<void> omiFirebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();

  await AwesomeNotifications().initialize(null, [
    NotificationChannel(
      channelKey: 'channel',
      channelName: 'Omi Notifications',
      channelDescription: 'Notification channel for Omi',
      defaultColor: const Color(0xFF9D50DD),
      ledColor: Colors.white,
    ),
  ]);

  final data = message.data;
  final messageType = data['type'];
  const channelKey = 'channel';

  if (messageType == 'action_item_reminder') {
    await ActionItemNotificationHandler.handleReminderMessage(data, channelKey);
  } else if (messageType == 'action_item_update') {
    await ActionItemNotificationHandler.handleUpdateMessage(data, channelKey);
  } else if (messageType == 'action_item_delete') {
    await ActionItemNotificationHandler.handleDeletionMessage(data);
  } else if (messageType == 'merge_completed') {
    await MergeNotificationHandler.handleMergeCompleted(data, channelKey, isAppInForeground: false);
  } else if (messageType == 'important_conversation') {
    await ImportantConversationNotificationHandler.handleImportantConversation(
      data,
      channelKey,
      isAppInForeground: false,
    );
  } else if (ChatAnswerNotificationHandler.isChatAnswerData(data)) {
    await ChatAnswerNotificationHandler.handle(
      data,
      channelKey,
      isAppInForeground: false,
    );
  }
}
