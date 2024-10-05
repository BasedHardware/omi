import 'dart:isolate';
import 'dart:ui';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/main.dart';
import 'package:friend_private/pages/home/page.dart';

class NotifyOnKill {
  static const platform = MethodChannel('com.friend.ios/notifyOnKill');

  static Future<void> register() async {
    try {
      await platform.invokeMethod(
        'setNotificationOnKillService',
        {
          'title': "Omi Device Disconnected",
          'description': "Please keep your app opened to continue using your Omi.",
        },
      );
    } catch (e) {
      debugPrint('NotifOnKill error: $e');
    }
  }
}

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
  NotifyOnKill.register();
}

Future<void> requestNotificationPermissions() async {
  bool isAllowed = await AwesomeNotifications().isNotificationAllowed();
  if (!isAllowed) {
    // This is just a basic example. For real apps, you must show some
    // friendly dialog box before call the request method.
    // This is very important to not harm the user experience
    // print('shouldShowRationaleToRequest: ${await AwesomeNotifications()}');
    AwesomeNotifications().requestPermissionToSendNotifications();
  }
}

_retrieveNotificationInterval({
  bool isMorningNotification = false,
  bool isDailySummaryNotification = false,
}) async {
  NotificationCalendar? interval;
  // TODO: allow people to set a notification time in settings
  if (isMorningNotification) {
    var scheduled = await AwesomeNotifications().listScheduledNotifications();
    var hasMorningNotification = scheduled.any((element) => element.content?.id == 4);
    debugPrint('hasMorningNotification: $hasMorningNotification');
    if (hasMorningNotification) return;
    interval = NotificationCalendar(
      hour: 8,
      minute: 0,
      second: 0,
      repeats: true,
      preciseAlarm: false,
      allowWhileIdle: true,
    );
  } else if (isDailySummaryNotification) {
    var scheduled = await AwesomeNotifications().listScheduledNotifications();
    var hasDailySummaryNotification = scheduled.any((element) => element.content?.id == 5);
    debugPrint('hasDailySummaryNotification: $hasDailySummaryNotification');
    if (hasDailySummaryNotification) return;
    interval = NotificationCalendar(
      hour: 20,
      minute: 0,
      second: 0,
      repeats: true,
      preciseAlarm: false,
      allowWhileIdle: false,
    );
  }
  return interval;
}

void createNotification({
  String title = '',
  String body = '',
  int notificationId = 1,
  Map<String, String?>? payload,
  bool isMorningNotification = false,
  bool isDailySummaryNotification = false,
  bool personFell = false,
}) async {
  var allowed = await AwesomeNotifications().isNotificationAllowed();
  debugPrint('createNotification: $allowed');
  if (!allowed) return;
  debugPrint('createNotification ~ Creating notification: $title');
  NotificationCalendar? interval = await _retrieveNotificationInterval(
    isMorningNotification: isMorningNotification,
    isDailySummaryNotification: isDailySummaryNotification,
  );
  if (interval == null && (isMorningNotification || isDailySummaryNotification)) return;

  AwesomeNotifications().createNotification(
    content: NotificationContent(
      id: notificationId,
      channelKey: 'channel',
      actionType: ActionType.Default,
      title: title,
      body: body,
      wakeUpScreen: true,
      payload: payload,
    ),
    schedule: interval,
  );
}

clearNotification(int id) => AwesomeNotifications().cancel(id);

class NotificationUtil {
  static ReceivePort? receivePort;

  static Future<void> initializeNotificationsEventListeners() async {
    // Only after at least the action method is set, the notification events are delivered
    AwesomeNotifications().setListeners(onActionReceivedMethod: NotificationUtil.onActionReceivedMethod);
  }

  static Future<void> initializeIsolateReceivePort() async {
    receivePort = ReceivePort('Notification action port in main isolate');
    receivePort!.listen((serializedData) {
      final receivedAction = ReceivedAction().fromMap(serializedData);
      onActionReceivedMethodImpl(receivedAction);
    });

    // This initialization only happens on main isolate
    IsolateNameServer.registerPortWithName(receivePort!.sendPort, 'notification_action_port');
  }

  /// Use this method to detect when the user taps on a notification or action button
  @pragma("vm:entry-point")
  static Future<void> onActionReceivedMethod(ReceivedAction receivedAction) async {
    if (receivePort != null) {
      await onActionReceivedMethodImpl(receivedAction);
    } else {
      print(
          'onActionReceivedMethod was called inside a parallel dart isolate, where receivePort was never initialized.');
      SendPort? sendPort = IsolateNameServer.lookupPortByName('notification_action_port');

      if (sendPort != null) {
        print('Redirecting the execution to main isolate process in listening...');
        dynamic serializedData = receivedAction.toMap();
        sendPort.send(serializedData);
      }
    }
  }

  static Future<void> onActionReceivedMethodImpl(ReceivedAction receivedAction) async {
    final Map<String, int> screensWithRespectToPath = {
      '/chat': 2,
      '/capture': 1,
      '/memories': 0,
    };
    var message = 'Action ${receivedAction.actionType?.name} received on ${receivedAction.actionLifeCycle?.name}';
    debugPrint(message);
    debugPrint(receivedAction.toMap().toString());

    // Always ensure that all plugins was initialized
    WidgetsFlutterBinding.ensureInitialized();
    final payload = receivedAction.payload;
    if (payload?.containsKey('navigateTo') ?? false) {
      SharedPreferencesUtil().subPageToShowFromNotification = payload?['navigateTo'] ?? '';
    }
    SharedPreferencesUtil().pageToShowFromNotification = screensWithRespectToPath[payload?['path']] ?? 1;
    MyApp.navigatorKey.currentState?.pushReplacement(MaterialPageRoute(builder: (context) => const HomePageWrapper()));
  }
}