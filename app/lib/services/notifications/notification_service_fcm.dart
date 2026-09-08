import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:ui';

import 'package:flutter/material.dart';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_timezone/flutter_timezone.dart';

import 'package:omi/backend/http/api/notifications.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/services/notifications/action_item_notification_handler.dart';
import 'package:omi/services/notifications/chat_answer_notification_handler.dart';
import 'package:omi/services/notifications/fcm_background_handler.dart';
import 'package:omi/services/notifications/important_conversation_notification_handler.dart';
import 'package:omi/services/notifications/merge_notification_handler.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/services/notifications/notification_interface.dart';
import 'package:omi/services/voice_playback/omi_voice_playback_service.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/logger.dart';

/// Firebase Cloud Messaging enabled notification service
/// Supports iOS, Android, macOS, web, and Linux with full FCM functionality
class _FCMNotificationService implements NotificationInterface {
  _FCMNotificationService._();

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
    await _firebaseMessaging.getAPNSToken();
    listenForMessages();
    // Re-register after main.dart's sync handler so chat answers get BigText in
    // background/terminated (#4375). Runs on the next event-loop turn, still
    // before runApp because main awaits more work after initialize().
    Future(() {
      FirebaseMessaging.onBackgroundMessage(omiFirebaseMessagingBackgroundHandler);
    });
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
        ),
      ],
      channelGroups: [
        NotificationChannelGroup(channelGroupKey: channel.channelKey!, channelGroupName: channel.channelName!),
      ],
      debug: false,
    );

    Logger.debug('initializeNotifications: $initialized');

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
    try {
      await _awesomeNotifications.createNotification(
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
    } catch (e) {
      Logger.debug('Failed to create notification (channel may be disabled): $e');
    }
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
  Future<void> register() async {}

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
    try {
      if (Platform.isIOS) {
        String? apnsToken;
        for (int i = 0; i < 10; i++) {
          apnsToken = await _firebaseMessaging.getAPNSToken();
          if (apnsToken != null) break;
          await Future.delayed(const Duration(seconds: 1));
        }

        if (apnsToken == null) {
          Logger.debug('APNS token not available yet, will retry on refresh');
          return;
        }
      }

      String? token = await _firebaseMessaging.getToken();
      await saveFcmToken(token);
    } catch (e) {
      Logger.debug('Failed to save notification token: $e');
    } finally {
      _firebaseMessaging.onTokenRefresh.listen(saveFcmToken);
    }
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
    Logger.debug('createNotification: $allowed');
    if (!allowed) return;
    Logger.debug('createNotification ~ Creating notification: $title');
    showNotification(id: notificationId, title: title, body: body, wakeUpScreen: true, payload: payload);
  }

  @override
  void clearNotification(int id) => _awesomeNotifications.cancel(id);

  bool _shouldShowForegroundNotificationOnFCMMessageReceived() {
    return Platform.isAndroid;
  }

  @override
  Future<void> listenForMessages() async {
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      final data = message.data;
      final noti = message.notification;

      if (data.isNotEmpty) {
        final Map<String, String> payload = <String, String>{};
        final navigateTo = data['navigate_to'];
        if (navigateTo != null && navigateTo.toString().isNotEmpty) {
          payload['navigate_to'] = navigateTo.toString();
        }

        final messageType = data['type'];
        if (messageType == 'apple_reminders_sync') {
          return;
        } else if (messageType == 'action_item_reminder') {
          ActionItemNotificationHandler.handleReminderMessage(data, channel.channelKey!);
          return;
        } else if (messageType == 'action_item_update') {
          ActionItemNotificationHandler.handleUpdateMessage(data, channel.channelKey!);
          return;
        } else if (messageType == 'action_item_delete') {
          ActionItemNotificationHandler.handleDeletionMessage(data);
          return;
        } else if (messageType == 'action_item_batch_delete') {
          ActionItemNotificationHandler.handleBatchDeletionMessage(data);
          return;
        } else if (messageType == 'merge_completed') {
          MergeNotificationHandler.handleMergeCompleted(data, channel.channelKey!, isAppInForeground: true);
          return;
        } else if (messageType == 'important_conversation') {
          ImportantConversationNotificationHandler.handleImportantConversation(
            data,
            channel.channelKey!,
            isAppInForeground: true,
          );
          return;
        }

        final notificationType = data['notification_type'];
        if (notificationType == 'plugin' || notificationType == 'daily_summary') {
          data['from_integration'] = data['from_integration'] == 'true';
          _serverMessageStreamController.add(ServerMessage.fromJson(data));
        }

        // Click-to-talk / chat answers: BigText + navigate_to payload (#4375).
        if (ChatAnswerNotificationHandler.isChatAnswerData(data)) {
          ChatAnswerNotificationHandler.handle(
            data,
            channel.channelKey!,
            isAppInForeground: true,
          );
          return;
        }

        if (noti != null && _shouldShowForegroundNotificationOnFCMMessageReceived()) {
          if (!OmiVoicePlaybackService.instance.isSpeaking) {
            final route = payload['navigate_to'] ?? '';
            final layout = route.startsWith('/chat/')
                ? NotificationLayout.BigText
                : NotificationLayout.Default;
            _showForegroundNotification(noti: noti, layout: layout, payload: payload);
          }
        }
        return;
      }

      if (noti != null && _shouldShowForegroundNotificationOnFCMMessageReceived()) {
        if (!OmiVoicePlaybackService.instance.isSpeaking) {
          _showForegroundNotification(noti: noti, layout: NotificationLayout.BigText);
        }
        return;
      }
    });

    void handleNotificationTap(RemoteMessage? message) {
      if (message == null) return;
      final navigateTo = message.data['navigate_to'];
      if (navigateTo is! String || navigateTo.isEmpty) return;
      WidgetsFlutterBinding.ensureInitialized();
      globalNavigatorKey.currentState?.pushReplacement(
        MaterialPageRoute(builder: (context) => HomePageWrapper(navigateToRoute: navigateTo)),
      );
    }

    FirebaseMessaging.onMessageOpenedApp.listen(handleNotificationTap);
    FirebaseMessaging.instance.getInitialMessage().then(handleNotificationTap);
  }

  final _serverMessageStreamController = StreamController<ServerMessage>.broadcast();

  @override
  Stream<ServerMessage> get listenForServerMessages => _serverMessageStreamController.stream;

  Future<void> _showForegroundNotification({
    required RemoteNotification noti,
    NotificationLayout layout = NotificationLayout.Default,
    Map<String, String?>? payload,
  }) async {
    if (noti.title == null || noti.body == null) return;
    final id = Random().nextInt(10000);
    showNotification(id: id, title: noti.title!, body: noti.body!, layout: layout, payload: payload);
  }
}

/// Factory function to create the FCM notification service
NotificationInterface createNotificationService() => _FCMNotificationService._();
