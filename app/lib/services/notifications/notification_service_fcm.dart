import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:ui';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:omi/backend/http/api/notifications.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/services/notifications/notification_interface.dart';
import 'package:omi/services/notifications/action_item_notification_handler.dart';
import 'package:omi/services/notifications/important_conversation_notification_handler.dart';
import 'package:omi/services/notifications/merge_notification_handler.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// Firebase Cloud Messaging enabled notification service
/// Supports iOS, Android, macOS, web, and Linux with full FCM functionality
class _FCMNotificationService implements NotificationInterface {
  _FCMNotificationService._();

  MethodChannel platform = const MethodChannel('com.friend.ios/notifyOnKill');
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

  @override
  Future<void> initialize() async {
    await _initializeAwesomeNotifications();
    // Calling it here because the APNS token can sometimes arrive early or it might take some time (like a few seconds)
    // Reference: https://github.com/firebase/flutterfire/issues/12244#issuecomment-1969286794
    await _firebaseMessaging.getAPNSToken();
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
    
// Reset badge to clear existing badge count if any
    int badgeCount = await _awesomeNotifications.getGlobalBadgeCounter();
if (badgeCount > 0) await _awesomeNotifications.resetGlobalBadge();
  }

  @override
  Future<void> showNotification({
    required int id,
    required String title,
    required String body,
    Map<String, String?>? payload,
    bool wakeUpScreen = false,
    NotificationSchedule? schedule,
    NotificationLayout layout = NotificationLayout.Default,
  }) async {
    final allowed = await _awesomeNotifications.isNotificationAllowed();
    if (!allowed) {
      return;
    }
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

  @override
  Future<bool> requestNotificationPermissions() async {
    bool isAllowed = await _awesomeNotifications.isNotificationAllowed();
    if (!isAllowed) {
      isAllowed = await _awesomeNotifications.requestPermissionToSendNotifications();
      register();
    }
    return isAllowed;
  }

  @override
  Future<void> register() async {
    try {
      if (PlatformService.isDesktop) return;
      await platform.invokeMethod(
        'setNotificationOnKillService',
        {
          'title': "Your Omi Device Disconnected",
          'description': "Please keep your app opened to continue using your Omi.",
        },
      );
    } catch (e) {
      debugPrint('NotifOnKill error: $e');
    }
  }

  @override
  Future<String> getTimeZone() async {
    final String currentTimeZone = await FlutterTimezone.getLocalTimezone();
    return currentTimeZone;
  }

  @override
  Future<void> saveFcmToken(String? token) async {
    if (token == null) return;
    String timeZone = await getTimeZone();
    if (FirebaseAuth.instance.currentUser != null && token.isNotEmpty) {
      await saveFcmTokenServer(token: token, timeZone: timeZone);

      try {
        await IntercomManager.instance.sendTokenToIntercom(token);
      } catch (e) {
        print(e);
      }
    }
  }

  @override
  void saveNotificationToken() async {
    if (Platform.isIOS || Platform.isMacOS) {
      String? apnsToken;
      for (int i = 0; i < 10; i++) {
        apnsToken = await _firebaseMessaging.getAPNSToken();
        if (apnsToken != null) break;
        await Future.delayed(const Duration(seconds: 1));
      }

      if (apnsToken == null) {
        debugPrint('APNS token not available yet, will retry on refresh');
        _firebaseMessaging.onTokenRefresh.listen(saveFcmToken);
        return;
      }
    }

    String? token = await _firebaseMessaging.getToken();
    await saveFcmToken(token);
    _firebaseMessaging.onTokenRefresh.listen(saveFcmToken);
  }

  @override
  Future<bool> hasNotificationPermissions() async {
    return await _awesomeNotifications.isNotificationAllowed();
  }

  @override
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

  @override
  void clearNotification(int id) => _awesomeNotifications.cancel(id);

  // FIXME: Causes the different behavior on android and iOS
  bool _shouldShowForegroundNotificationOnFCMMessageReceived() {
    return Platform.isAndroid;
  }

  @override
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

        // Handle action item data messages
        final messageType = data['type'];
        if (messageType == 'action_item_reminder') {
          ActionItemNotificationHandler.handleReminderMessage(data, channel.channelKey!);
          return;
        } else if (messageType == 'action_item_update') {
          ActionItemNotificationHandler.handleUpdateMessage(data, channel.channelKey!);
          return;
        } else if (messageType == 'action_item_delete') {
          ActionItemNotificationHandler.handleDeletionMessage(data);
          return;
        } else if (messageType == 'merge_completed') {
          MergeNotificationHandler.handleMergeCompleted(
            data,
            channel.channelKey!,
            isAppInForeground: true,
          );
          return;
        } else if (messageType == 'important_conversation') {
          ImportantConversationNotificationHandler.handleImportantConversation(
            data,
            channel.channelKey!,
            isAppInForeground: true,
          );
          return;
        }

        // plugin, daily summary
        final notificationType = data['notification_type'];
        if (notificationType == 'plugin' || notificationType == 'daily_summary') {
          data['from_integration'] = data['from_integration'] == 'true';
          _serverMessageStreamController.add(ServerMessage.fromJson(data));
        }
        if (noti != null && _shouldShowForegroundNotificationOnFCMMessageReceived()) {
          _showForegroundNotification(noti: noti, payload: payload);
        }
        return;
      }

      // Announcement likes
      if (noti != null && _shouldShowForegroundNotificationOnFCMMessageReceived()) {
        _showForegroundNotification(noti: noti, layout: NotificationLayout.BigText);
        return;
      }
    });
  }

  final _serverMessageStreamController = StreamController<ServerMessage>.broadcast();

  @override
  Stream<ServerMessage> get listenForServerMessages => _serverMessageStreamController.stream;

  Future<void> _showForegroundNotification(
      {required RemoteNotification noti,
      NotificationLayout layout = NotificationLayout.Default,
      Map<String, String?>? payload}) async {
    final id = Random().nextInt(10000);
    showNotification(id: id, title: noti.title!, body: noti.body!, layout: layout, payload: payload);
  }
}

/// Factory function to create the FCM notification service
NotificationInterface createNotificationService() => _FCMNotificationService._();