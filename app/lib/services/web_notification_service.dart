import 'dart:async';
import 'dart:math';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:friend_private/backend/http/api/notifications.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/main.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:intercom_flutter/intercom_flutter.dart';

/// Web-compatible notification service that doesn't use dart:isolate
class WebNotificationService {
  WebNotificationService._();

  static WebNotificationService instance = WebNotificationService._();
  static bool _initialized = false;
  final FirebaseMessaging _firebaseMessaging = FirebaseMessaging.instance;

  final channel = NotificationChannel(
    channelGroupKey: 'channel_group_key',
    channelKey: 'channel',
    channelName: 'Omi Notifications',
    channelDescription: 'Notification channel for Omi',
    defaultColor: const Color(0xFF9D50DD),
    ledColor: Colors.white,
  );

  final AwesomeNotifications _awesomeNotifications = AwesomeNotifications();

  Future<void> initialize() async {
    if (_initialized) return;
    
    try {
      await _initializeAwesomeNotifications();
      listenForMessages();
      _initialized = true;
      debugPrint('WebNotificationService initialized successfully');
    } catch (e) {
      debugPrint('Error initializing WebNotificationService: $e');
      // Continue without notifications on web
      _initialized = true;
    }
  }

  Future<void> _initializeAwesomeNotifications() async {
    bool initialized = await _awesomeNotifications.initialize(
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
    NotificationLayout layout = NotificationLayout.Default,
  }) {
    _awesomeNotifications.createNotification(
      content: NotificationContent(
        id: id,
        channelKey: channel.channelKey!,
        actionType: ActionType.Default,
        title: title,
        body: body,
        payload: payload,
        notificationLayout: layout,
      ),
    );
  }

  Future<bool> requestNotificationPermissions() async {
    bool isAllowed = await _awesomeNotifications.isNotificationAllowed();
    if (!isAllowed) {
      isAllowed = await _awesomeNotifications.requestPermissionToSendNotifications();
    }
    return isAllowed;
  }

  Future<String> getTimeZone() async {
    final String currentTimeZone = await FlutterTimezone.getLocalTimezone();
    return currentTimeZone;
  }

  Future<void> saveFcmToken(String? token) async {
    if (token == null) return;
    String timeZone = await getTimeZone();
    if (FirebaseAuth.instance.currentUser != null && token.isNotEmpty) {
      await Intercom.instance.sendTokenToIntercom(token);
      await saveFcmTokenServer(token: token, timeZone: timeZone);
    }
  }

  void saveNotificationToken() async {
    String? token = await _firebaseMessaging.getToken();
    await saveFcmToken(token);
    _firebaseMessaging.onTokenRefresh.listen(saveFcmToken);
  }

  Future<bool> hasNotificationPermissions() async {
    return await _awesomeNotifications.isNotificationAllowed();
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
      final noti = message.notification;

      // Plugin
      if (data.isNotEmpty) {
        late Map<String, String> payload = <String, String>{};
        payload.addAll({
          "navigate_to": data['navigate_to'] ?? "",
        });

        // plugin, daily summary
        final notificationType = data['notification_type'];
        if (notificationType == 'plugin' || notificationType == 'daily_summary') {
          data['from_integration'] = data['from_integration'] == 'true';
          _serverMessageStreamController.add(ServerMessage.fromJson(data));
        }
        if (noti != null) {
          _showForegroundNotification(noti: noti, payload: payload);
        }
        return;
      }

      // Announcement likes
      if (noti != null) {
        _showForegroundNotification(noti: noti, layout: NotificationLayout.BigText);
        return;
      }
    });
  }

  final _serverMessageStreamController = StreamController<ServerMessage>.broadcast();

  Stream<ServerMessage> get listenForServerMessages => _serverMessageStreamController.stream;

  Future<void> _showForegroundNotification(
      {required RemoteNotification noti,
      NotificationLayout layout = NotificationLayout.Default,
      Map<String, String?>? payload}) async {
    final id = Random().nextInt(10000);
    showNotification(id: id, title: noti.title!, body: noti.body!, layout: layout, payload: payload);
  }
}

/// Web-compatible notification utility that doesn't use dart:isolate
class WebNotificationUtil {
  static Future<void> initializeNotificationsEventListeners() async {
    // Only after at least the action method is set, the notification events are delivered
    AwesomeNotifications().setListeners(onActionReceivedMethod: WebNotificationUtil.onActionReceivedMethod);
    debugPrint('Web notification listeners initialized successfully');
  }

  // No isolate initialization needed for web

  /// Use this method to detect when the user taps on a notification or action button
  @pragma("vm:entry-point")
  static Future<void> onActionReceivedMethod(ReceivedAction receivedAction) async {
    debugPrint('Web notification action received: ${receivedAction.id}');
    await onActionReceivedMethodImpl(receivedAction);
  }

  static Future<void> onActionReceivedMethodImpl(ReceivedAction receivedAction) async {
    if (receivedAction.payload == null || receivedAction.payload!.isEmpty) {
      debugPrint('Web notification payload is empty');
      return;
    }
    debugPrint('Web notification payload: ${receivedAction.payload}');
    _handleAppLinkOrDeepLink(receivedAction.payload!);
  }

  static void _handleAppLinkOrDeepLink(Map<String, dynamic> payload) async {
    WidgetsFlutterBinding.ensureInitialized();

    String? navigateTo;
    if (payload.containsKey('navigate_to')) {
      navigateTo = payload['navigate_to'];
    }
    if (navigateTo == null) {
      debugPrint("Navigate To is null");
      return;
    }

    debugPrint('Web notification navigating to: $navigateTo');
    MyApp.navigatorKey.currentState
        ?.pushReplacement(MaterialPageRoute(builder: (context) => HomePageWrapper(navigateToRoute: navigateTo)));
  }
}
