
import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:flutter/material.dart';

// TODO: could install the latest version due to podfile issues, so installed 0.8.3
// https://pub.dev/packages/awesome_notifications/versions/0.8.3

Future<void> initializeNotifications() async {
  bool initialized = await AwesomeNotifications().initialize(
      // set the icon to null if you want to use the default app icon
      'resource://drawable/icon',
      [
        NotificationChannel(
            channelGroupKey: 'channel_group_key',
            channelKey: 'channel',
            channelName: 'Friend Notifications',
            channelDescription: 'Notification channel for Friend',
            defaultColor: const Color(0xFF9D50DD),
            ledColor: Colors.white)
      ],
      // Channel groups are only visual and are not required
      channelGroups: [
        NotificationChannelGroup(channelGroupKey: 'channel_group_key', channelGroupName: 'Friend Notifications')
      ],
      debug: false);
  debugPrint('initializeNotifications: $initialized');
}

Future<void> requestNotificationPermissions() async {
  bool isAllowed = await AwesomeNotifications().isNotificationAllowed();
  if (!isAllowed) {
    // This is just a basic example. For real apps, you must show some
    // friendly dialog box before call the request method.
    // This is very important to not harm the user experience
    AwesomeNotifications().requestPermissionToSendNotifications();
  }
}

void createNotification({String title = '', String body = '', int notificationId = 1, int? delayMinutes}) async {
  var allowed = await AwesomeNotifications().isNotificationAllowed();
  if (!allowed) return;
  debugPrint('createNotification ~ Creating notification: $title');
  var scheduleInterval = delayMinutes != null ? NotificationInterval(interval: delayMinutes * 60) : null;
  AwesomeNotifications().createNotification(
    content: NotificationContent(
      id: notificationId,
      channelKey: 'channel',
      actionType: ActionType.Default,
      title: title,
      body: body,
    ),
    schedule: scheduleInterval,
  );
}

clearNotification(int id) => AwesomeNotifications().cancel(id);
