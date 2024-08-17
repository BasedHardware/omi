import 'dart:async';
import 'dart:isolate';
import 'dart:math';
import 'dart:ui';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:friend_private/backend/http/api/notifications.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/main.dart';
import 'package:friend_private/pages/home/page.dart';

class NotificationService {
  NotificationService._();

  static NotificationService instance = NotificationService._();
  MethodChannel platform = const MethodChannel('com.friend.ios/notifyOnKill');
  final FirebaseMessaging _firebaseMessaging = FirebaseMessaging.instance;

  final channel = NotificationChannel(
    channelGroupKey: 'channel_group_key',
    channelKey: 'channel',
    channelName: 'Friend Notifications',
    channelDescription: 'Notification channel for Friend',
    defaultColor: const Color(0xFF9D50DD),
    ledColor: Colors.white,
  );

// TODO: could not install the latest version due to podfile issues, so installed 0.8.3
// https://pub.dev/packages/awesome_notifications/versions/0.8.3
  final AwesomeNotifications _awesomeNotifications = AwesomeNotifications();

  Future<void> initialize() async {
    await _initializeAwesomeNotifications();
    unawaited(_register());
    listenForMessages();
  }

  Future<void> _initializeAwesomeNotifications() async {
    bool initialized = await _awesomeNotifications.initialize(
        // set the icon to null if you want to use the default app icon
        'resource://drawable/icon',
        [
          NotificationChannel(
            channelGroupKey: 'channel_group_key',
            channelKey: channel.channelKey,
            channelName: channel.channelName,
            channelDescription: channel.channelDescription,
            defaultColor: const Color(0xFF9D50DD),
            ledColor: Colors.white,
          )
        ],
        // Channel groups are only visual and are not required
        channelGroups: [
          NotificationChannelGroup(
            channelGroupKey: channel.channelKey!,
            channelGroupName: channel.channelName!,
          )
        ],
        debug: false);

    debugPrint('initializeNotifications: $initialized');
  }

  void showNotification({
    required int id,
    required String title,
    required String body,
    Map<String, String?>? payload,
    bool wakeUpScreen = false,
    NotificationSchedule? schedule,
  }) {
    _awesomeNotifications.createNotification(
      content: NotificationContent(
        id: id,
        channelKey: channel.channelKey!,
        actionType: ActionType.Default,
        title: title,
        body: body,
        payload: payload,
      ),
    );
  }

  Future<void> requestNotificationPermissions() async {
    bool isAllowed = await _awesomeNotifications.isNotificationAllowed();
    if (!isAllowed) {
      _awesomeNotifications.requestPermissionToSendNotifications();
    }
  }

  Future<void> _register() async {
    try {
      await platform.invokeMethod(
        'setNotificationOnKillService',
        {
          'title': "Friend Device Disconnected",
          'description': "Please keep your app opened to continue using your Friend.",
        },
      );
    } catch (e) {
      debugPrint('NotifOnKill error: $e');
    }
  }

  Future<String> getTimeZone() async {
    final String currentTimeZone = await FlutterTimezone.getLocalTimezone();
    return currentTimeZone;
  }

  Future<void> saveFcmToken(String? token) async {
    if (token == null) return;
    String timeZone = await getTimeZone();
    await saveFcmTokenServer(token: token, timeZone: timeZone);
  }

  void saveNotificationToken() async {
    String? token = await _firebaseMessaging.getToken();
    await saveFcmToken(token);
    _firebaseMessaging.onTokenRefresh.listen(saveFcmToken);
  }

  Future<void> createNotification({
    String title = '',
    String body = '',
    int notificationId = 1,
    Map<String, String?>? payload,
  }) async {
    var allowed = await _awesomeNotifications.isNotificationAllowed();
    debugPrint('createNotification: $allowed');
    if (!allowed) return;
    debugPrint('createNotification ~ Creating notification: $title');
    showNotification(id: notificationId, title: title, body: body, wakeUpScreen: true, payload: payload);
  }

  clearNotification(int id) => _awesomeNotifications.cancel(id);

  Future<void> listenForMessages() async {
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      final data = message.data;
      if (data.isEmpty) return;
      if (data['notification_type'] == 'plugin') {
        _showForegroundNotification(message.notification);
        data['from_integration'] = data['from_integration'] == 'true';
        _serverMessageStreamController.add(ServerMessage.fromJson(data));
      }
    });
  }

  final _serverMessageStreamController = StreamController<ServerMessage>.broadcast();

  Stream<ServerMessage> get listenForServerMessages => _serverMessageStreamController.stream;

  Future<void> _showForegroundNotification(RemoteNotification? notification) async {
    if (notification != null) {
      final id = Random().nextInt(10000);
      showNotification(id: id, title: notification.title!, body: notification.body!);
    }
  }
}

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
